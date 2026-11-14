// Same story, every language — computed in the browser straight from each Wikipedia's API
// (fast: no server round trips; CORS via origin=*). Mirrors api/languages.py exactly; the
// result is then stored in MariaDB (system-versioned) and translated by Gemma on the server.
import type { LangCompare, LangEdition, LangRename, LangSignal } from './types'

const PRIORITY = ['en', 'fi', 'sv', 'ru', 'uk', 'de', 'pl', 'be', 'et', 'fr', 'es', 'it', 'zh', 'ja', 'ar', 'he', 'tr']
const MAX_LANGS = 12
const MAX_NAME_CHECKS = 10
const REVERT_TAGS = new Set(['mw-reverted', 'mw-undo', 'mw-rollback', 'mw-manual-revert'])
const MAX_IN_FLIGHT = 12

// ---------- MediaWiki ----------

let inFlight = 0
const waiting: Array<() => void> = []
async function slot<T>(fn: () => Promise<T>): Promise<T> {
  if (inFlight >= MAX_IN_FLIGHT) await new Promise<void>((r) => waiting.push(r))
  inFlight++
  try {
    return await fn()
  } finally {
    inFlight--
    waiting.shift()?.()
  }
}

type Json = Record<string, any> // eslint-disable-line @typescript-eslint/no-explicit-any

async function wapi(lang: string, params: Record<string, string | number>): Promise<Json> {
  const q = new URLSearchParams({ format: 'json', formatversion: '2', origin: '*' })
  for (const [k, v] of Object.entries(params)) q.set(k, String(v))
  let last = 'no response'
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const res = await slot(() => fetch(`https://${lang}.wikipedia.org/w/api.php?${q}`))
      if (res.status === 429 || res.status === 503) {
        last = `HTTP ${res.status}`
        await sleep(1000 * (1 + attempt))
        continue
      }
      if (!res.ok) throw new Error(`HTTP ${res.status} from ${lang}.wikipedia.org`)
      const data = (await res.json()) as Json
      if (data.error) throw new Error(`${lang}.wikipedia.org: ${data.error.code}: ${data.error.info ?? ''}`)
      return data
    } catch (e) {
      last = e instanceof Error ? e.message : String(e)
      if (last.includes('wikipedia.org:')) throw e
      await sleep(500 * (1 + attempt))
    }
  }
  throw new Error(`${lang}.wikipedia.org: gave up (${last})`)
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

// Language names in English, and each language's name for itself (built into the browser).
const inEnglish = new Intl.DisplayNames(['en'], { type: 'language' })
function languageName(code: string): string {
  try {
    return inEnglish.of(code) ?? code
  } catch {
    return code
  }
}
function autonymOf(code: string): string | null {
  try {
    return new Intl.DisplayNames([code], { type: 'language' }).of(code) ?? null
  } catch {
    return null
  }
}

type EditionInfo = { title: string; name: string | null; autonym: string | null }

async function editions(lang: string, title: string): Promise<Record<string, EditionInfo>> {
  const data = await wapi(lang, {
    action: 'query', prop: 'langlinks', titles: title, redirects: 1,
    lllimit: 'max', llprop: 'langname|autonym', uselang: 'en',
  })
  const page = data.query?.pages?.[0]
  if (!page || page.missing) throw new Error(`No article called “${title}” on ${lang}.wikipedia.org`)
  const out: Record<string, EditionInfo> = { [lang]: { title: page.title, name: null, autonym: null } }
  for (const l of page.langlinks ?? []) out[l.lang] = { title: l.title, name: l.langname ?? null, autonym: l.autonym ?? null }
  return out
}

function pickLanguages(source: string, available: Record<string, EditionInfo>): string[] {
  const ordered = [source, ...PRIORITY.filter((l) => l in available && l !== source)]
  for (const l of Object.keys(available).sort()) if (!ordered.includes(l)) ordered.push(l)
  return ordered.slice(0, MAX_LANGS)
}

type RawEdition = Omit<LangEdition, 'language' | 'autonym' | 'signals'>

async function editionReport(lang: string, titleIn: string): Promise<RawEdition> {
  const moveLog = async (t: string) =>
    ((await wapi(lang, { action: 'query', list: 'logevents', letype: 'move', letitle: t, lelimit: 50 })).query
      ?.logevents ?? []) as Json[]

  const [base, prot, firstMoves] = await Promise.all([
    wapi(lang, {
      action: 'query', titles: titleIn, redirects: 1, prop: 'redirects|revisions|extracts|info', rdlimit: 'max',
      rvlimit: 500, rvprop: 'timestamp|tags', exintro: 1, explaintext: 1, exchars: 320,
    }),
    wapi(lang, { action: 'query', list: 'logevents', letype: 'protect', letitle: titleIn, lelimit: 100 }),
    moveLog(titleIn),
  ])
  const page = base.query.pages[0]
  const title: string = page.title
  const names: string[] = (page.redirects ?? []).map((r: Json) => r.title)
  const revs: Json[] = page.revisions ?? []
  const reverted = revs.filter((r) => (r.tags ?? []).some((t: string) => REVERT_TAGS.has(t))).length
  const protects: Json[] =
    title === titleIn
      ? prot.query.logevents
      : (await wapi(lang, { action: 'query', list: 'logevents', letype: 'protect', letitle: title, lelimit: 100 })).query
          .logevents

  // Renames: logged under the title moved *from*. Start with the current title and a few old
  // names (redirects), then follow the titles it was moved to. Bounded to MAX_NAME_CHECKS.
  const known = new Set([title, ...names])
  const renames: LangRename[] = []
  const seen = new Set<string>()
  const checked = new Set<string>()
  let queue = [title, ...names.slice(0, 4)]
  while (queue.length && checked.size < MAX_NAME_CHECKS) {
    const batch = [...new Set(queue)].filter((t) => !checked.has(t)).slice(0, MAX_NAME_CHECKS - checked.size)
    queue = []
    batch.forEach((t) => checked.add(t))
    const logs = await Promise.all(batch.map((t) => (t === titleIn ? Promise.resolve(firstMoves) : moveLog(t))))
    for (const events of logs) {
      for (const e of events) {
        const target: string | undefined = e.params?.target_title
        const key = `${e.timestamp}|${e.title}|${target}`
        if (target && known.has(target) && !seen.has(key)) {
          seen.add(key)
          renames.push({ ts: e.timestamp, from: e.title, to: target, reason: e.comment || null })
          if (!checked.has(target)) queue.push(target)
        }
      }
    }
  }
  renames.sort((a, b) => a.ts.localeCompare(b.ts))
  renames.forEach((m, i) => {
    if (m.reverses) return
    const back = renames.slice(i + 1).find((n) => n.from === m.to && n.to === m.from && !n.reverses)
    if (back) {
      back.reverses = true
      m.undone_after_hours = Math.round(((Date.parse(back.ts) - Date.parse(m.ts)) / 3_600_000) * 100) / 100
    }
  })

  return {
    lang,
    title,
    url: `https://${lang}.wikipedia.org/wiki/${encodeURIComponent(title.replace(/ /g, '_'))}`,
    first_sentence: (page.extract ?? '').trim() || null,
    names,
    renames,
    locks: protects.length,
    recent: { edits: revs.length, reverted, since: revs.length ? revs[revs.length - 1].timestamp : null },
  }
}

// ---------- conflict signals (same rules as the server) ----------

export function signals(rep: RawEdition): LangSignal[] {
  const out: LangSignal[] = []
  const undone = rep.renames.filter((m) => m.undone_after_hours !== undefined)
  if (undone.length) {
    const fastest = Math.min(...undone.map((m) => m.undone_after_hours as number))
    out.push({ kind: 'naming_fight', label: `${undone.length} rename(s) undone`,
      explain: `The title was changed and changed back; fastest reversal after ${hours(fastest)}.` })
  }
  const b = burst(rep.renames)
  if (b) out.push({ kind: 'rename_burst', label: `${b.count} renames in ${hours(b.hours)}`,
    explain: 'Several title changes in a short window.' })
  const npov = rep.renames.filter((m) => m.reason && /npov|neutral|pov\b|neutraal|нейтрал/i.test(m.reason))
  if (npov.length) out.push({ kind: 'neutrality_claim', label: 'renamed citing neutrality',
    explain: `${npov.length} rename reason(s) mention the neutral-point-of-view rule.` })
  if (rep.locks >= 2) out.push({ kind: 'locked', label: `locked ${rep.locks}×`,
    explain: 'Administrators restricted editing (protection log entries).' })
  const r = rep.recent
  if (r.edits >= 50 && r.reverted / r.edits >= 0.1) out.push({ kind: 'revert_heavy',
    label: `${Math.round((100 * r.reverted) / r.edits)}% of recent edits reverted`,
    explain: `${r.reverted} of the last ${r.edits} edits were undone or rolled back.` })
  if (rep.names.length >= 10) out.push({ kind: 'many_names', label: `${rep.names.length} other names`,
    explain: 'Many alternative titles redirect here.' })
  return out
}

function burst(renames: LangRename[], windowH = 48) {
  let best: { count: number; hours: number } | null = null
  for (let i = 0; i < renames.length; i++) {
    let j = i
    while (j + 1 < renames.length && Date.parse(renames[j + 1].ts) - Date.parse(renames[i].ts) <= windowH * 3_600_000) j++
    const n = j - i + 1
    if (n >= 3 && (!best || n > best.count)) {
      best = { count: n, hours: Math.round(((Date.parse(renames[j].ts) - Date.parse(renames[i].ts)) / 3_600_000) * 10) / 10 }
    }
  }
  return best
}

export function hours(h: number) {
  if (h < 1) return `${Math.max(1, Math.round(h * 60))} min`
  if (h < 48) return `${Math.round(h)} h`
  return `${Math.round(h / 24)} days`
}

// ---------- the whole comparison ----------

export async function compareInBrowser(
  title: string,
  lang: string,
  onProgress?: (done: string[], total: number) => void,
): Promise<LangCompare> {
  const started = performance.now()
  const available = await editions(lang, title.trim())
  const chosen = pickLanguages(lang, available)
  const done: string[] = []
  onProgress?.(done, chosen.length)

  const editionsOut: LangEdition[] = await Promise.all(
    chosen.map(async (l) => {
      const info = available[l]
      let e: LangEdition
      try {
        const raw = await editionReport(l, info.title)
        e = { ...raw, language: languageName(l), autonym: info.autonym ?? autonymOf(l), signals: signals(raw) }
      } catch (err) {
        e = {
          lang: l, title: info.title, language: languageName(l), autonym: info.autonym ?? autonymOf(l),
          error: err instanceof Error ? err.message : String(err),
          names: [], renames: [], locks: 0, recent: { edits: 0, reverted: 0, since: null },
        }
      }
      done.push(l)
      onProgress?.([...done], chosen.length)
      return e
    }),
  )

  const ok = editionsOut.filter((e) => !e.error)
  editionsOut.sort((a, b) => Number(a.lang !== lang) - Number(b.lang !== lang) || (b.signals?.length ?? 0) - (a.signals?.length ?? 0))
  return {
    query: { lang, title: available[lang].title },
    languages_available: Object.keys(available).length,
    editions: editionsOut,
    summary: {
      renames: ok.reduce((n, e) => n + e.renames.length, 0),
      renames_undone: ok.reduce((n, e) => n + e.renames.filter((m) => m.undone_after_hours !== undefined).length, 0),
      locks: ok.reduce((n, e) => n + e.locks, 0),
      names: ok.reduce((n, e) => n + e.names.length, 0),
      editions_with_signals: ok.filter((e) => e.signals?.length).length,
    },
    fetched_at: new Date().toISOString(),
    seconds: Math.round((performance.now() - started) / 100) / 10,
    translated_by: null,
    cached: false,
  }
}

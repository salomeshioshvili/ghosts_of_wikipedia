// Same story, every language — computed in the browser straight from each Wikipedia's API
// (fast: no server round trips; CORS via origin=*). Mirrors api/languages.py exactly; the
// result is then stored in MariaDB (system-versioned) and translated by Gemma on the server.
import type { LangCompare, LangEdition, LangRename, LangSignal } from './types'

const MAX_LANGS = 12
const MAX_NAME_CHECKS = 10
const REVERT_TAGS = new Set(['mw-reverted', 'mw-undo', 'mw-rollback', 'mw-manual-revert'])
const MAX_IN_FLIGHT = 6

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
  for (let attempt = 0; attempt < 6; attempt++) {
    try {
      const res = await slot(() => fetch(`https://${lang}.wikipedia.org/w/api.php?${q}`))
      if (res.status === 429 || res.status === 503) {
        // Wikipedia is rate-limiting us: wait as long as it asks (or back off exponentially), then try again.
        last = `HTTP ${res.status}`
        const asked = Number(res.headers.get('retry-after'))
        await sleep(asked > 0 ? asked * 1000 : 1500 * 2 ** attempt + Math.random() * 500)
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

// Countries/peoples named in the article's introduction -> the Wikipedias of the people involved.
// Order of first mention decides priority. Labels are shown as the reason a language was chosen.
const INVOLVED: Array<[RegExp, string[], string]> = [
  [/\bFinn(ish|s)?\b|\bFinland\b/i, ['fi', 'sv'], 'Finland'],
  [/\bSwed(en|ish|es)\b/i, ['sv'], 'Sweden'],
  [/\bRussia(n|ns)?\b|\bSoviet\b|\bUSSR\b/i, ['ru'], 'Russia / USSR'],
  [/\bUkrain(e|ian|ians)\b/i, ['uk'], 'Ukraine'],
  [/\bBelarus(ian)?\b/i, ['be'], 'Belarus'],
  [/\bEston(ia|ian|ians)\b/i, ['et'], 'Estonia'],
  [/\bLatvi(a|an|ans)\b/i, ['lv'], 'Latvia'],
  [/\bLithuani(a|an|ans)\b/i, ['lt'], 'Lithuania'],
  [/\bPol(and|ish|es)\b/i, ['pl'], 'Poland'],
  [/\bGerman(y|s)?\b|\bPrussia(n)?\b|\bNazi\b/i, ['de'], 'Germany'],
  [/\bAustria(n)?\b/i, ['de'], 'Austria'],
  [/\bNorw(ay|egian)\b/i, ['no', 'nb'], 'Norway'],
  [/\bDen(mark|ish)\b|\bDanes\b/i, ['da'], 'Denmark'],
  [/\bFrance\b|\bFrench\b/i, ['fr'], 'France'],
  [/\bSpain\b|\bSpanish\b/i, ['es'], 'Spain'],
  [/\bItal(y|ian|ians)\b/i, ['it'], 'Italy'],
  [/\bPortug(al|uese)\b|\bBrazil(ian)?\b/i, ['pt'], 'Portugal / Brazil'],
  [/\bNetherlands\b|\bDutch\b/i, ['nl'], 'Netherlands'],
  [/\bBritish\b|\bBritain\b|\bUnited Kingdom\b|\bEngland\b|\bUnited States\b|\bAmerican\b/i, ['en'], 'UK / US'],
  [/\bHungar(y|ian)\b/i, ['hu'], 'Hungary'],
  [/\bCzech\b/i, ['cs'], 'Czechia'],
  [/\bSlovak(ia)?\b/i, ['sk'], 'Slovakia'],
  [/\bRomania(n)?\b/i, ['ro'], 'Romania'],
  [/\bBulgaria(n)?\b/i, ['bg'], 'Bulgaria'],
  [/\bSerbia(n)?\b|\bYugoslav(ia)?\b/i, ['sr'], 'Serbia / Yugoslavia'],
  [/\bCroatia(n)?\b/i, ['hr'], 'Croatia'],
  [/\bBosnia(n)?\b/i, ['bs'], 'Bosnia'],
  [/\bKosov(o|ar)\b|\bAlbania(n)?\b/i, ['sq'], 'Kosovo / Albania'],
  [/\bGree(ce|k)\b/i, ['el'], 'Greece'],
  [/\bTurk(ey|ish|iye)\b|\bOttoman\b/i, ['tr'], 'Turkey'],
  [/\bArmenia(n)?\b/i, ['hy'], 'Armenia'],
  [/\bAzerbaijan(i)?\b/i, ['az'], 'Azerbaijan'],
  [/\bGeorgia(n)?\b/i, ['ka'], 'Georgia'],
  [/\bIsrael(i)?\b|\bJewish\b|\bHebrew\b/i, ['he'], 'Israel'],
  [/\bPalestin(e|ian)\b|\bGaza\b|\bArab(s|ic)?\b|\bSyria(n)?\b|\bEgypt(ian)?\b|\bIraq(i)?\b|\bLebanon\b|\bSaudi\b/i, ['ar'], 'Arab world'],
  [/\bIran(ian)?\b|\bPersia(n)?\b/i, ['fa'], 'Iran'],
  [/\bKurd(s|ish|istan)?\b/i, ['ku', 'ckb'], 'Kurds'],
  [/\bAfghan(istan)?\b/i, ['ps', 'fa'], 'Afghanistan'],
  [/\bPakistan(i)?\b/i, ['ur'], 'Pakistan'],
  [/\bIndia(n)?\b/i, ['hi'], 'India'],
  [/\bTamil(s)?\b/i, ['ta'], 'Tamils'],
  [/\bSri Lanka(n)?\b|\bSinhal(a|ese)\b/i, ['si', 'ta'], 'Sri Lanka'],
  [/\bChin(a|ese)\b|\bTaiwan(ese)?\b|\bHong Kong\b/i, ['zh'], 'China / Taiwan'],
  [/\bJapan(ese)?\b/i, ['ja'], 'Japan'],
  [/\bKorea(n)?\b/i, ['ko'], 'Korea'],
  [/\bVietnam(ese)?\b/i, ['vi'], 'Vietnam'],
  [/\bIndonesia(n)?\b|\bEast Timor\b/i, ['id'], 'Indonesia'],
  [/\bPhilippine(s)?\b|\bFilipino\b/i, ['tl'], 'Philippines'],
  [/\bMexic(o|an)\b|\bArgentin(a|e)\b|\bChile(an)?\b|\bColombia(n)?\b|\bVenezuela(n)?\b|\bCuba(n)?\b/i, ['es'], 'Latin America'],
  [/\bCatalan|Catalonia\b/i, ['ca'], 'Catalonia'],
  [/\bBasque\b/i, ['eu'], 'Basque Country'],
]
const MAJOR = ['de', 'fr', 'es', 'ru', 'ja', 'zh', 'it', 'pt', 'pl', 'ar', 'uk', 'sv']

// Housekeeping sections that say nothing about the topic (many languages).
const BORING_SECTIONS =
  /^(top|external links|references|notes|see also|bibliography|further reading|sources|lähteet|kirjallisuutta|aiheesta muualla|katso myös|viitteet|källor|externa länkar|se även|referenser|einzelnachweise|weblinks|literatur|siehe auch|liens externes|références|notes et références|voir aussi|bibliographie|enlaces externos|referencias|véase también|bibliografía|collegamenti esterni|note|bibliografia|voci correlate|ligações externas|referências|ver também|przypisy|bibliografia|linki zewnętrzne|ссылки|литература|примечания|см\. также|english|svenska|suomi)$/i

export type Pick = { lang: string; why: string }

function pickRelevant(source: string, available: Record<string, EditionInfo>, intro: string): Pick[] {
  const out: Pick[] = []
  const add = (l: string, why: string) => {
    if (l in available && !out.some((p) => p.lang === l) && out.length < MAX_LANGS) out.push({ lang: l, why })
  }
  add(source, 'the article you asked about')
  const hits = INVOLVED.map(([re, langs, label]) => ({ i: intro.search(re), langs, label }))
    .filter((h) => h.i >= 0)
    .sort((a, b) => a.i - b.i)
  for (const h of hits) for (const l of h.langs) add(l, `involved: ${h.label}`)
  add('en', 'global reference edition')
  for (const l of MAJOR) add(l, 'major Wikipedia')
  for (const l of Object.keys(available).sort()) add(l, 'other edition')
  return out
}

type RawEdition = Omit<LangEdition, 'language' | 'autonym' | 'signals'>

// Monthly readers (Wikimedia pageviews, people only, from July 2015). Missing months count as 0.
async function pageviews(lang: string, title: string): Promise<LangEdition['views']> {
  const now = new Date()
  const end = `${now.getUTCFullYear()}${String(now.getUTCMonth() + 1).padStart(2, '0')}0100`
  const url = `https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/${lang}.wikipedia/all-access/user/${encodeURIComponent(
    title.replace(/ /g, '_'),
  )}/monthly/2015070100/${end}`
  const res = await slot(() => fetch(url))
  if (!res.ok) return null
  const items: Json[] = ((await res.json()).items ?? []).filter((i: Json) => String(i.timestamp).slice(0, 6) !== end.slice(0, 6))
  if (!items.length) return null
  const idx = (ts: string) => Number(ts.slice(0, 4)) * 12 + Number(ts.slice(4, 6)) - 1
  const first = idx(String(items[0].timestamp))
  const monthly = new Array(idx(String(items[items.length - 1].timestamp)) - first + 1).fill(0)
  for (const i of items) monthly[idx(String(i.timestamp)) - first] = Number(i.views) || 0
  return { start: `${String(items[0].timestamp).slice(0, 4)}-${String(items[0].timestamp).slice(4, 6)}`, monthly }
}

async function editionReport(lang: string, titleIn: string): Promise<RawEdition> {
  const moveLog = async (t: string) =>
    ((await wapi(lang, { action: 'query', list: 'logevents', letype: 'move', letitle: t, lelimit: 50 })).query
      ?.logevents ?? []) as Json[]

  const [base, prot, firstMoves, talkData, firstRev, articleSections, views] = await Promise.all([
    wapi(lang, {
      action: 'query', titles: titleIn, redirects: 1, prop: 'redirects|revisions|extracts|info', rdlimit: 'max',
      rvlimit: 500, rvprop: 'timestamp|tags|comment|user', exintro: 1, explaintext: 1, exchars: 1200,
    }),
    wapi(lang, { action: 'query', list: 'logevents', letype: 'protect', letitle: titleIn, lelimit: 100 }),
    moveLog(titleIn),
    wapi(lang, { action: 'parse', page: `Talk:${titleIn}`, prop: 'sections', redirects: 1 }).catch(() => null),
    wapi(lang, { action: 'query', titles: titleIn, redirects: 1, prop: 'revisions', rvdir: 'newer', rvlimit: 1, rvprop: 'timestamp' }).catch(
      () => null,
    ),
    wapi(lang, { action: 'parse', page: titleIn, prop: 'sections', redirects: 1 }).catch(() => null),
    pageviews(lang, titleIn).catch(() => null),
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

  // Sections where this edition's edits were most often reverted ("/* Section */" in edit summaries).
  const fought = new Map<string, number>()
  for (const r of revs) {
    if (!(r.tags ?? []).some((t: string) => REVERT_TAGS.has(t))) continue
    const m = /\/\*\s*(.+?)\s*\*\//.exec(String(r.comment ?? ''))
    const sec = m ? m[1].replace(/\s+/g, ' ').trim() : ''
    if (!sec || sec.includes('|') || sec.includes(':') || /^[\w-]+-summary/.test(sec) || BORING_SECTIONS.test(sec)) continue
    fought.set(sec, (fought.get(sec) ?? 0) + 1)
  }
  const lead = (page.extract ?? '').trim()
  // Who edits: counted, never stored or shown (no usernames leave this function).
  const users = new Set(revs.map((r) => String(r.user ?? '')).filter(Boolean))
  const unregistered = revs.filter((r) => r.anon || r.temp || /^~\d/.test(String(r.user ?? ''))).length
  const headings: string[] = ((articleSections?.parse?.sections ?? []) as Json[])
    .filter((x) => Number(x.toclevel) === 1)
    .map((x) => String(x.line ?? '').replace(/<[^>]+>/g, '').trim())
    .filter((x) => x && !BORING_SECTIONS.test(x))
  return {
    lang,
    title,
    url: `https://${lang}.wikipedia.org/wiki/${encodeURIComponent(title.replace(/ /g, '_'))}`,
    first_sentence: lead ? (lead.length > 320 ? `${lead.slice(0, 320).replace(/\s+\S*$/, '')}…` : lead) : null,
    lead: lead || null,
    fought_sections: [...fought.entries()].sort((a, b) => b[1] - a[1]).slice(0, 4).map(([section, reverted]) => ({ section, reverted })),
    names,
    renames,
    locks: protects.length,
    recent: { edits: revs.length, reverted, since: revs.length ? revs[revs.length - 1].timestamp : null },
    talk: talkOf(lang, talkData),
    first_edit: firstRev?.query?.pages?.[0]?.revisions?.[0]?.timestamp ?? null,
    size: { bytes: Number(page.length) || 0, sections: headings.slice(0, 30) },
    editors: revs.length ? { distinct: users.size, unregistered_pct: Math.round((100 * unregistered) / revs.length) } : null,
    views,
  }
}

// Talk-page sections about the name: where editors argued about the title (any language).
const NAMING = /\bname|\btitle|naming|rename|\bmove|npov|neutral|nimi|nimeä|nimitys|nime[nä]|\bnamn|benämning|artikelns namn|titel|lemma|bezeichnung|benennung|название|наименован|переименов|назв|перейменув|\bnom\b|titre|dénomination|nombre|título|titolo|denominazione|nazwa|tytuł|pealkiri|nimetus|név|címe|název|naam|isim|başlık|nome\b/i

function talkOf(lang: string, data: Json | null): LangEdition['talk'] {
  const parsed = data?.parse
  if (!parsed) return null
  const lines: string[] = (parsed.sections ?? []).map((x: Json) => String(x.line ?? '').replace(/<[^>]+>/g, ''))
  return {
    url: `https://${lang}.wikipedia.org/wiki/${encodeURIComponent(String(parsed.title).replace(/ /g, '_'))}`,
    sections: lines.length,
    naming: [...new Set(lines.filter((l) => NAMING.test(l)))].slice(0, 8),
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
  const introLang = 'en' in available ? 'en' : lang
  const intro = await wapi(introLang, {
    action: 'query', prop: 'extracts', titles: available[introLang].title, redirects: 1,
    exintro: 1, explaintext: 1, exchars: 2500,
  })
    .then((d) => String(d.query?.pages?.[0]?.extract ?? ''))
    .catch(() => '')
  const picks = pickRelevant(lang, available, intro)
  const chosen = picks.map((x) => x.lang)
  const done: string[] = []
  onProgress?.(done, chosen.length)

  const editionsOut: LangEdition[] = await Promise.all(
    chosen.map(async (l) => {
      const info = available[l]
      let e: LangEdition
      try {
        const raw = await editionReport(l, info.title)
        e = { ...raw, language: languageName(l), autonym: info.autonym ?? autonymOf(l), signals: signals(raw),
              why: picks.find((x) => x.lang === l)?.why }
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
    others: Object.keys(available)
      .filter((l) => !chosen.includes(l))
      .map((l) => ({ lang: l, title: available[l].title, language: languageName(l) }))
      .sort((a, b) => a.language.localeCompare(b.language)),
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

/** Add one more language edition to a comparison (the "add a language" chips). */
export async function addLanguage(report: LangCompare, lang: string): Promise<LangCompare> {
  const other = report.others?.find((o) => o.lang === lang)
  if (!other) return report
  let e: LangEdition
  try {
    const raw = await editionReport(lang, other.title)
    e = { ...raw, language: languageName(lang), autonym: autonymOf(lang), signals: signals(raw), why: 'added by you' }
  } catch (err) {
    e = { lang, title: other.title, language: languageName(lang), autonym: autonymOf(lang), why: 'added by you',
          error: err instanceof Error ? err.message : String(err), names: [], renames: [], locks: 0,
          recent: { edits: 0, reverted: 0, since: null } }
  }
  const editions = [...report.editions, e]
  const ok = editions.filter((x) => !x.error)
  return {
    ...report,
    editions,
    others: (report.others ?? []).filter((o) => o.lang !== lang),
    summary: {
      renames: ok.reduce((n, x) => n + x.renames.length, 0),
      renames_undone: ok.reduce((n, x) => n + x.renames.filter((m) => m.undone_after_hours !== undefined).length, 0),
      locks: ok.reduce((n, x) => n + x.locks, 0),
      names: ok.reduce((n, x) => n + x.names.length, 0),
      editions_with_signals: ok.filter((x) => x.signals?.length).length,
    },
    translated_by: null,
  }
}

import { useState } from 'react'
import { comparePerspectives, formatDate, interpretComparison } from '../lib/api'
import type { LangCompare, LangEdition, LangInsight, LangPerspectives } from '../lib/types'
import { hours } from '../lib/wikilang'

// How a title frames the event, read from its English meaning. Order matters: specific first.
const FRAMES: Array<[string, RegExp]> = [
  ['special operation', /special (military )?operation|military operation/i],
  ['war of liberation', /liberation|freedom|independence war|war of independence/i],
  ['class war', /class war/i],
  ['civil war', /civil war|internal war|fratricid|brothers'? war/i],
  ['revolution / uprising', /revolution|rebellion|uprising|revolt|insurrection/i],
  ['invasion', /invasion|invade|intrusion|incursion/i],
  ['attack / assault', /attack|assault|aggression|raid|onslaught/i],
  ['war', /\bwar\b/i],
  ['conflict / crisis', /conflict|crisis/i],
  ['events', /events|happenings|incident/i],
]

function frameOf(e: LangEdition): string | null {
  const text = e.lang === 'en' ? e.title : e.title_en
  if (!text) return null
  for (const [label, re] of FRAMES) if (re.test(text)) return label
  return 'other'
}

function heat(e: LangEdition) {
  const undone = e.renames.filter((m) => m.undone_after_hours !== undefined).length
  const revertPct = e.recent.edits ? e.recent.reverted / e.recent.edits : 0
  return undone * 3 + e.renames.length + e.locks * 1.5 + revertPct * 20
}

function name(e: LangEdition) {
  return e.language || e.lang.toUpperCase()
}

type Props = { data: LangCompare; onAdd?: (lang: string) => Promise<void> }

export function AtAGlance({ data, onAdd }: Props) {
  const [insight, setInsight] = useState<LangInsight | null>(null)
  const [thinking, setThinking] = useState(false)
  const [insightError, setInsightError] = useState<string | null>(null)
  const [adding, setAdding] = useState<string | null>(null)
  const [showAll, setShowAll] = useState(false)
  const [persp, setPersp] = useState<LangPerspectives | null>(null)
  const [perspBusy, setPerspBusy] = useState(false)
  const [perspError, setPerspError] = useState<string | null>(null)
  const eds = data.editions.filter((e) => !e.error)
  if (eds.length < 2) return null

  // 1. framing groups
  const framed = eds.map((e) => ({ e, frame: frameOf(e) }))
  const known = framed.filter((x) => x.frame && x.frame !== 'other')
  const groups = new Map<string, LangEdition[]>()
  for (const { e, frame } of known) groups.set(frame!, [...(groups.get(frame!) ?? []), e])
  const ranked = [...groups.entries()].sort((a, b) => b[1].length - a[1].length)
  const translated = !!data.translated_by
  const waitingForMeanings = !translated && framed.some((x) => x.frame === null)
  const gap = translated ? '—' : '…'

  // 2. most / least contested
  const byHeat = [...eds].sort((a, b) => heat(b) - heat(a))
  const hot = byHeat[0]
  const calm = byHeat[byHeat.length - 1]

  // 3. biggest naming fight and most recent rename
  const allRenames = eds.flatMap((e) => e.renames.filter((m) => !m.reverses).map((m) => ({ e, m })))
  const fights = eds
    .map((e) => ({ e, sig: e.signals?.find((s) => s.kind === 'rename_burst') }))
    .filter((x) => x.sig)
  const fastestUndo = eds
    .flatMap((e) => e.renames.filter((m) => m.undone_after_hours !== undefined).map((m) => ({ e, m })))
    .sort((a, b) => (a.m.undone_after_hours ?? 0) - (b.m.undone_after_hours ?? 0))[0]
  const latest = [...allRenames].sort((a, b) => b.m.ts.localeCompare(a.m.ts))[0]
  const stable = eds.filter((e) => e.renames.length === 0)

  const insights: string[] = []
  if (ranked.length > 1) {
    insights.push(
      `The editions don't agree on what it was: ${ranked
        .slice(0, 4)
        .map(([f, es]) => `${es.length} call it ${f === 'war' ? 'a war' : f === 'events' ? '“the events”' : `${/^[aeiou]/.test(f) ? 'an' : 'a'} ${f}`}`)
        .join(', ')}.`,
    )
  } else if (ranked.length === 1 && known.length === eds.length) {
    insights.push(`All ${eds.length} editions frame it the same way: ${ranked[0][0]}.`)
  }
  if (hot && heat(hot) > 0) {
    const bits = [
      hot.renames.length ? `${hot.renames.length} renames` : '',
      hot.locks ? `locked ${hot.locks}×` : '',
      hot.recent.edits ? `${Math.round((100 * hot.recent.reverted) / hot.recent.edits)}% of recent edits reverted` : '',
    ].filter(Boolean)
    insights.push(`Most fought-over: ${name(hot)} (${bits.join(', ')}).`)
  }
  for (const { e, sig } of fights.slice(0, 2)) insights.push(`Naming fight in ${name(e)}: ${sig!.label}.`)
  if (fastestUndo)
    insights.push(
      `Fastest reversal: ${name(fastestUndo.e)} renamed it “${fastestUndo.m.to}” on ${formatDate(fastestUndo.m.ts)}, undone after ${hours(fastestUndo.m.undone_after_hours!)}.`,
    )
  if (latest) insights.push(`Most recent rename: ${name(latest.e)}, ${formatDate(latest.m.ts)} (“${latest.m.from}” → “${latest.m.to}”).`)
  if (calm && calm !== hot) insights.push(`Calmest: ${name(calm)}${calm.renames.length === 0 ? ', never renamed' : ''}.`)
  if (stable.length && stable.length < eds.length)
    insights.push(`${stable.length} of ${eds.length} editions have never changed their title.`)
  const clusters: Array<Array<{ e: LangEdition; m: (typeof allRenames)[number]['m'] }>> = []
  {
    const sorted = [...allRenames].sort((a, b) => a.m.ts.localeCompare(b.m.ts))
    let cur: typeof clusters[number] = []
    for (const r of sorted) {
      if (cur.length && Date.parse(r.m.ts) - Date.parse(cur[0].m.ts) > 48 * 3_600_000) {
        if (new Set(cur.map((x) => x.e.lang)).size >= 2) clusters.push(cur)
        cur = []
      }
      cur.push(r)
    }
    if (new Set(cur.map((x) => x.e.lang)).size >= 2) clusters.push(cur)
  }
  clusters.sort((a, b) => new Set(b.map((x) => x.e.lang)).size - new Set(a.map((x) => x.e.lang)).size)
  for (const c of clusters.slice(0, 2)) {
    const langs = [...new Set(c.map((x) => name(x.e)))]
    const undoneAll = c.every((x) => x.m.undone_after_hours !== undefined)
    insights.push(
      `Renamed in several languages at once: ${formatDate(c[0].m.ts)}, ${langs.join(', ')} within 48 h (${c
        .slice(0, 3)
        .map((x) => `“${x.m.to}”`)
        .join(', ')}${c.length > 3 ? '…' : ''})${undoneAll ? '; all undone' : ''}.`,
    )
  }

  const debated = eds.filter((e) => e.talk?.naming?.length)
  if (debated.length)
    insights.push(
      `Naming debated on the talk page in ${debated.map((e) => name(e)).join(', ')} (${debated
        .map((e) => `“${e.talk!.naming[0]}”`)
        .slice(0, 3)
        .join(', ')}${debated.length > 3 ? '…' : ''}).`,
    )

  // ---------- beyond the name: who wrote it, who reads it, how it is edited ----------
  const community: string[] = []
  const written = eds.filter((e) => e.first_edit).sort((a, b) => a.first_edit!.localeCompare(b.first_edit!))
  if (written.length >= 3) {
    const a0 = written[0]
    const z = written[written.length - 1]
    const gap = (Date.parse(z.first_edit!) - Date.parse(a0.first_edit!)) / (365.25 * 864e5)
    community.push(
      `First written in ${name(a0)} (${monthLabel(a0.first_edit!)}), then ${written
        .slice(1, 3)
        .map((e) => `${name(e)} (${monthLabel(e.first_edit!)})`)
        .join(', ')}. Last of these: ${name(z)} (${monthLabel(z.first_edit!)}), ${
        gap >= 1 ? `${gap.toFixed(0)} years` : `${Math.max(1, Math.round(gap * 365.25))} days`
      } after the first.`,
    )
  }
  const sized = eds.filter((e) => e.size?.bytes).sort((a, b) => b.size!.bytes - a.size!.bytes)
  if (sized.length >= 3) {
    const big = sized[0]
    const small = sized[sized.length - 1]
    community.push(
      `Most detailed: ${name(big)} (${kb(big.size!.bytes)}, ${big.size!.sections.length} sections). Shortest: ${name(small)} (${kb(
        small.size!.bytes,
      )}), ${Math.round(big.size!.bytes / small.size!.bytes)}× shorter.`,
    )
  }
  const viewed = eds.map((e) => ({ e, v: viewStats(e) })).filter((x) => x.v) as Array<{ e: LangEdition; v: ViewStats }>
  if (viewed.length >= 2) {
    const byReaders = [...viewed].sort((a, b) => b.v.avg12 - a.v.avg12)
    community.push(
      `Most read in the last year: ${byReaders
        .slice(0, 3)
        .map((x) => `${name(x.e)} (${x.v.avg12.toLocaleString('en')} a month)`)
        .join(', ')}.`,
    )
    const spike = [...viewed].sort((a, b) => b.v.ratio - a.v.ratio)[0]
    community.push(
      `Biggest attention spike: ${name(spike.e)} readers in ${monthLabel(spike.v.peakMonth)}, ${spike.v.ratio.toFixed(0)}× their usual month (${spike.v.peak.toLocaleString('en')} views).`,
    )
    const byPeak = new Map<string, string[]>()
    for (const x of viewed) byPeak.set(x.v.peakMonth, [...(byPeak.get(x.v.peakMonth) ?? []), name(x.e)])
    const shared = [...byPeak.entries()].sort((a, b) => b[1].length - a[1].length)[0]
    if (shared && shared[1].length >= 2)
      community.push(`${shared[1].length} editions had their busiest month ever in ${monthLabel(shared[0])}: ${shared[1].join(', ')}.`)
  }
  const edited = eds.filter((e) => e.editors && e.recent.edits >= 20)
  if (edited.length >= 2) {
    const open = [...edited].sort((a, b) => b.editors!.unregistered_pct - a.editors!.unregistered_pct)
    const lo = open[open.length - 1]
    community.push(
      `Most edited by unregistered users: ${name(open[0])} (${open[0].editors!.unregistered_pct}% of recent edits). Least: ${name(lo)} (${lo.editors!.unregistered_pct}%${
        lo.locks ? `, locked ${lo.locks}×` : ''
      }).`,
    )
    const pace = edited
      .filter((e) => e.recent.since)
      .map((e) => ({ e, perYear: perYear(e) }))
      .sort((a, b) => b.perYear - a.perYear)
    if (pace.length >= 2)
      community.push(
        `Busiest editing now: ${name(pace[0].e)} (about ${pace[0].perYear.toLocaleString('en')} edits a year). Quietest: ${name(
          pace[pace.length - 1].e,
        )} (about ${pace[pace.length - 1].perYear.toLocaleString('en')}).`,
      )
  }
  const foughtAt = eds.filter((e) => e.fought_sections?.length)
  if (foughtAt.length)
    community.push(
      `Where editors fight (most-reverted sections): ${foughtAt
        .slice(0, 4)
        .map((e) => `${name(e)}: “${e.fought_sections![0].section}”`)
        .join('; ')}.`,
    )

  function evidence() {
    return {
      topic: data.query.title,
      renamed_in_several_languages_within_48h: clusters.slice(0, 3).map((c) => ({
        date: c[0].m.ts.slice(0, 10),
        renames: c.map((x) => ({ lang: x.e.lang, to: x.m.to, undone: x.m.undone_after_hours !== undefined })),
      })),
      editions: framed.map(({ e, frame }) => ({
        lang: e.lang,
        language: name(e),
        why_included: e.why ?? null,
        current_title: e.title,
        title_meaning: e.lang === 'en' ? e.title : (e.title_en ?? null),
        framing: frame,
        first_sentence: (e.first_sentence_en ?? (e.lang === 'en' ? e.first_sentence : null))?.slice(0, 260) ?? null,
        renames: e.renames
          .filter((m) => !m.reverses)
          .slice(-10)
          .map((m) => ({
            date: m.ts.slice(0, 10),
            from: m.from,
            to: m.to,
            reason: m.reason_en ?? m.reason,
            outcome: m.undone_after_hours !== undefined ? `undone (moved back after ${hours(m.undone_after_hours)})` : 'kept',
          })),
        locks: e.locks,
        recent_edits_reverted_pct: e.recent.edits ? Math.round((100 * e.recent.reverted) / e.recent.edits) : null,
        talk_page_naming_sections: e.talk?.naming ?? [],
        first_written: e.first_edit?.slice(0, 10) ?? null,
        size_kb: e.size ? Math.round(e.size.bytes / 1000) : null,
        top_level_sections: e.size?.sections.slice(0, 20) ?? [],
        readers_per_month_last_year: viewStats(e)?.avg12 ?? null,
        busiest_reading_month: viewStats(e) ? `${viewStats(e)!.peakMonth} (${viewStats(e)!.ratio.toFixed(1)}x usual)` : null,
        unregistered_edit_pct: e.editors?.unregistered_pct ?? null,
        distinct_editors_in_recent_edits: e.editors?.distinct ?? null,
        edits_per_year_recently: e.recent.since ? perYear(e) : null,
        most_reverted_sections: (e.fought_sections ?? []).map((f) => f.section),
      })),
    }
  }

  function interpret(refresh = false) {
    setThinking(true)
    setInsightError(null)
    interpretComparison(data.query.title, data.query.lang, evidence(), refresh)
      .then(setInsight)
      .catch((err: unknown) => setInsightError(err instanceof Error ? err.message : String(err)))
      .finally(() => setThinking(false))
  }

  function perspectives(refresh = false) {
    setPerspBusy(true)
    setPerspError(null)
    const payload = eds.map((e) => ({
      lang: e.lang,
      language: name(e),
      lead: e.lead ?? null,
      fought_sections: (e.fought_sections ?? []).map((f) => `${f.section} (${f.reverted} reverted edits)`),
      sections: e.size?.sections ?? [],
    }))
    comparePerspectives(data.query.title, data.query.lang, payload, refresh)
      .then(setPersp)
      .catch((err: unknown) => setPerspError(err instanceof Error ? err.message : String(err)))
      .finally(() => setPerspBusy(false))
  }

  const others = data.others ?? []
  const shownOthers = showAll ? others : others.slice(0, 18)

  const timeline = allRenames.sort((a, b) => a.m.ts.localeCompare(b.m.ts))

  return (
    <section className="glance">
      <h2 className="glance__title">at a glance: how the languages differ</h2>

      <div className="glance__actions">
        <button type="button" className="glance__ask" onClick={() => interpret(false)} disabled={thinking}>
          {thinking ? 'Gemma is reading the evidence…' : 'What could this mean?'}
        </button>
        <button type="button" className="glance__ask is-alt" onClick={() => perspectives(false)} disabled={perspBusy}>
          {perspBusy ? 'Gemma is comparing the openings…' : 'Compare what each edition says'}
        </button>
        <span className="glance__hint">patterns and explanations · or a point-by-point table of how each edition tells it</span>
      </div>
      {perspError && <p className="glance__muted">Couldn't compare: {perspError}</p>}
      {persp && (
        <div className="persp">
          <p className="insight__headline">{persp.summary}</p>
          <div className="glance__tablewrap">
            <table className="persp__table">
              <thead>
                <tr>
                  <th>point</th>
                  {eds.map((e) => (
                    <th key={e.lang} title={name(e)}>
                      {e.lang.toUpperCase()}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {persp.points.map((p) => (
                  <tr key={p.point}>
                    <th>{p.point}</th>
                    {eds.map((e) => {
                      const v = p.by_language[e.lang]
                      return (
                        <td key={e.lang} className={v ? '' : 'is-missing'}>
                          {v ?? 'not mentioned'}
                        </td>
                      )
                    })}
                  </tr>
                ))}
                {Object.keys(persp.own_sections ?? {}).length > 0 && (
                  <tr className="persp__fought">
                    <th>has its own section on (few others do)</th>
                    {eds.map((e) => (
                      <td key={e.lang}>{(persp.own_sections?.[e.lang] ?? []).join(' · ') || '—'}</td>
                    ))}
                  </tr>
                )}
                {Object.keys(persp.fought_over).length > 0 && (
                  <tr className="persp__fought">
                    <th>where its editors fight (most-reverted sections)</th>
                    {eds.map((e) => (
                      <td key={e.lang}>{(persp.fought_over[e.lang] ?? []).join(' · ') || '—'}</td>
                    ))}
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <p className="glance__muted">
            Compared by Gemma from each edition's opening section only. {persp.caveats.map((c) => c.trim().replace(/^\d+[.)]\s*/, '').replace(/^./, (x) => x.toUpperCase()).replace(/[.]?$/, '.')).join(' ')} ·{' '}
            {persp.cached ? 'saved' : 'new'} {formatDate(persp.created_at)} ·{' '}
            <button type="button" className="glance__link" onClick={() => perspectives(true)} disabled={perspBusy}>
              compare again
            </button>
          </p>
        </div>
      )}
      {insightError && <p className="glance__muted">Couldn't interpret: {insightError}</p>}
      {insight && (
        <div className="insight">
          <p className="insight__headline">{insight.headline}</p>
          <div className="insight__cols">
            <div>
              <h4>patterns</h4>
              <ul>{insight.patterns.map((t) => <li key={t}>{t}</li>)}</ul>
            </div>
            <div>
              <h4>what it could mean</h4>
              <ul>{insight.possible_explanations.map((t) => <li key={t}>{t}</li>)}</ul>
            </div>
            <div>
              <h4>what this can't show</h4>
              <ul>{insight.caveats.map((t) => <li key={t}>{t}</li>)}</ul>
            </div>
            <div>
              <h4>questions to investigate</h4>
              <ul>{insight.questions.map((t) => <li key={t}>{t}</li>)}</ul>
            </div>
          </div>
          <p className="glance__muted">
            Written by Gemma from the evidence on this page only; possibilities, not conclusions ·{' '}
            {insight.cached ? 'saved' : 'new'} {formatDate(insight.created_at)} ·{' '}
            <button type="button" className="glance__link" onClick={() => interpret(true)} disabled={thinking}>
              ask again
            </button>
          </p>
        </div>
      )}

      <ul className="glance__insights">
        {insights.map((t) => (
          <li key={t}>{t}</li>
        ))}
        {waitingForMeanings && <li className="glance__muted">Gemma is still translating some titles; framing fills in when it's done.</li>}
      </ul>

      {community.length > 0 && (
        <>
          <h3 className="glance__sub">beyond the name: who wrote it, who reads it, how it is edited</h3>
          <ul className="glance__insights">
            {community.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        </>
      )}

      {viewed.length > 0 && <Attention rows={viewed} name={name} />}

      <div className="glance__tablewrap">
        <table className="glance__table">
          <thead>
            <tr>
              <th>language</th>
              <th>why here</th>
              <th>what it's called</th>
              <th>meaning</th>
              <th>framing</th>
              <th>fights</th>
              <th>first written</th>
              <th>size</th>
              <th>readers / month</th>
              <th>editing</th>
            </tr>
          </thead>
          <tbody>
            {framed.map(({ e, frame }) => {
              const undone = e.renames.filter((m) => m.undone_after_hours !== undefined).length
              return (
                <tr key={e.lang} className={e === hot ? 'is-hot' : ''}>
                  <td>
                    <strong>{e.lang.toUpperCase()}</strong> {name(e)}
                  </td>
                  <td className="glance__why">{e.why ?? ''}</td>
                  <td className="glance__orig">{e.title}</td>
                  <td>{e.lang === 'en' ? '—' : (e.title_en ?? gap)}</td>
                  <td>{frame ? <span className={`glance__frame f-${frame.replace(/[^a-z]+/g, '-')}`}>{frame}</span> : gap}</td>
                  <td className="glance__nums">
                    {e.renames.length} rename{e.renames.length === 1 ? '' : 's'}{undone ? ` (${undone} undone)` : ''} · {e.locks} lock{e.locks === 1 ? '' : 's'}
                    {e.talk?.naming?.length ? (
                      <a className="glance__talk" href={e.talk.url} target="_blank" rel="noreferrer" title={e.talk.naming.join(' · ')}>
                        talk: {e.talk.naming.length} naming debate{e.talk.naming.length === 1 ? '' : 's'}
                      </a>
                    ) : null}
                  </td>
                  <td className="glance__nums">{e.first_edit ? monthLabel(e.first_edit) : '…'}</td>
                  <td className="glance__nums">{e.size?.bytes ? `${kb(e.size.bytes)} · ${e.size.sections.length} sections` : '…'}</td>
                  <td className="glance__nums">{viewStats(e) ? `${viewStats(e)!.avg12.toLocaleString('en')} · peak ${monthLabel(viewStats(e)!.peakMonth)}` : '…'}</td>
                  <td className="glance__nums">
                    {e.editors ? `${perYear(e).toLocaleString('en')} edits/yr · ${e.editors.unregistered_pct}% unregistered` : '…'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {onAdd && others.length > 0 && (
        <div className="glance__add">
          <span>add a language ({others.length} more):</span>
          {shownOthers.map((o) => (
            <button
              key={o.lang}
              type="button"
              disabled={!!adding}
              onClick={() => {
                setAdding(o.lang)
                void onAdd(o.lang).finally(() => setAdding(null))
              }}
              title={o.title}
            >
              {adding === o.lang ? 'adding…' : o.language}
            </button>
          ))}
          {others.length > 18 && (
            <button type="button" className="glance__link" onClick={() => setShowAll((v) => !v)}>
              {showAll ? 'fewer' : 'all'}
            </button>
          )}
        </div>
      )}

      {timeline.length > 0 && (
        <>
          <h3 className="glance__sub">every rename, all languages</h3>
          <ol className="glance__timeline">
            {timeline.map(({ e, m }) => (
              <li key={`${e.lang}-${m.ts}-${m.to}`}>
                <span className="glance__date">{formatDate(m.ts)}</span>
                <span className="glance__lang">{e.lang.toUpperCase()}</span>
                <span>
                  {m.from} → <strong>{m.to}</strong>
                  {m.undone_after_hours !== undefined && <em> undone after {hours(m.undone_after_hours)}</em>}
                </span>
              </li>
            ))}
          </ol>
        </>
      )}
    </section>
  )
}

// ---------- helpers for the community signals ----------
type ViewStats = { avg12: number; peak: number; peakMonth: string; ratio: number }

function monthAt(start: string, i: number) {
  const [y, m] = start.split('-').map(Number)
  const t = y * 12 + (m - 1) + i
  return `${Math.floor(t / 12)}-${String((t % 12) + 1).padStart(2, '0')}`
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
function monthLabel(iso: string) {
  return `${MONTHS[Number(iso.slice(5, 7)) - 1]} ${iso.slice(0, 4)}`
}

function kb(bytes: number) {
  return `${Math.round(bytes / 1000)} kB`
}

function perYear(e: LangEdition) {
  const years = Math.max((Date.now() - Date.parse(e.recent.since ?? '')) / (365.25 * 864e5), 1 / 12)
  return Math.round(e.recent.edits / years)
}

function viewStats(e: LangEdition): ViewStats | null {
  const v = e.views
  if (!v || v.monthly.length < 12) return null
  const m = v.monthly
  // Months with almost no readers usually mean the article had another title then (views are counted per title),
  // so they are left out of "usual month"; too few real months means no spike claim at all.
  const top = Math.max(...m, 1)
  const real = m.filter((n) => n >= top * 0.02)
  if (real.length < 6) return null
  const sorted = [...real].sort((a, b) => a - b)
  const median = Math.max(sorted[Math.floor(sorted.length / 2)], 1)
  let pi = 0
  m.forEach((x, i) => {
    if (x > m[pi]) pi = i
  })
  const last = m.slice(-12)
  return { avg12: Math.round(last.reduce((a, b) => a + b, 0) / last.length), peak: m[pi], peakMonth: monthAt(v.start, pi), ratio: m[pi] / median }
}

/** Who was reading, when: one line per edition, each scaled to its own busiest month. */
function Attention({ rows, name }: { rows: Array<{ e: LangEdition; v: ViewStats }>; name: (e: LangEdition) => string }) {
  const W = 640
  const H = 26
  const idx = (iso: string) => Number(iso.slice(0, 4)) * 12 + Number(iso.slice(5, 7)) - 1
  const series = rows.map(({ e, v }) => ({ e, v, start: idx(e.views!.start), m: e.views!.monthly }))
  const t0 = Math.min(...series.map((s) => s.start))
  const t1 = Math.max(...series.map((s) => s.start + s.m.length - 1))
  const x = (t: number) => ((t - t0) / Math.max(t1 - t0, 1)) * W
  const years: number[] = []
  for (let y = Math.ceil(t0 / 12); y * 12 <= t1; y++) years.push(y)
  return (
    <div className="attn">
      <h3 className="glance__sub">who was reading, when (monthly readers, each language scaled to its own busiest month)</h3>
      {series.map(({ e, v, start, m }) => {
        const max = Math.max(...m, 1)
        const pts = m.map((n, i) => `${x(start + i).toFixed(1)},${(H - 2 - (n / max) * (H - 4)).toFixed(1)}`).join(' ')
        const pk = idx(v.peakMonth)
        return (
          <div className="attn__row" key={e.lang}>
            <span className="attn__lang" title={name(e)}>
              {e.lang.toUpperCase()}
            </span>
            <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="attn__svg">
              {years.map((y) => (
                <line key={y} x1={x(y * 12)} x2={x(y * 12)} y1={0} y2={H} className="attn__grid" />
              ))}
              <polyline points={pts} className="attn__line" />
              <line x1={x(pk)} x2={x(pk)} y1={0} y2={H} className="attn__peak" />
            </svg>
            <span className="attn__note">
              peak {monthLabel(v.peakMonth)} · {v.ratio.toFixed(0)}×
            </span>
          </div>
        )
      })}
      <div className="attn__row attn__axis">
        <span className="attn__lang" />
        <div className="attn__years">
          {years
            .filter((y) => y % 2 === 0)
            .map((y) => (
              <span key={y} style={{ left: `${(x(y * 12) / W) * 100}%` }}>
                {y}
              </span>
            ))}
        </div>
        <span className="attn__note" />
      </div>
    </div>
  )
}

import { useEffect, useMemo, useState } from 'react'
import { getWordShift, trackWord } from '../lib/api'
import type { WordShift, WordStat } from '../lib/types'

const COLORS = ['#d4b52a', '#e5484d', '#2f9e44', '#1c7ed6', '#9c36b5', '#121820']

/** Words over time: what this article stopped saying, what it kept saying, and each word's use by year. */
export function WordsPanel({ pageId, onClose }: { pageId: number; onClose: () => void }) {
  const [data, setData] = useState<WordShift | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [picked, setPicked] = useState<string[]>([])
  const [extra, setExtra] = useState<Record<string, { label: string; series: number[] }>>({})
  const [query, setQuery] = useState('')

  useEffect(() => {
    setData(null)
    setError(null)
    getWordShift(pageId)
      .then((d) => {
        setData(d)
        setPicked([...d.stopped_saying.slice(0, 2), ...d.kept_saying.slice(0, 2)].map((w) => w.stem))
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }, [pageId])

  const label = useMemo(() => {
    const m: Record<string, WordStat> = {}
    for (const w of [...(data?.stopped_saying ?? []), ...(data?.kept_saying ?? [])]) m[w.stem] = w
    return m
  }, [data])

  function toggle(stem: string) {
    setPicked((p) => (p.includes(stem) ? p.filter((x) => x !== stem) : [...p, stem].slice(-6)))
  }

  function addWord() {
    const q = query.trim()
    if (!q) return
    trackWord(pageId, q)
      .then((t) => {
        setExtra((x) => ({ ...x, [t.stem]: { label: q, series: t.series } }))
        setPicked((p) => (p.includes(t.stem) ? p : [...p, t.stem].slice(-6)))
        setQuery('')
      })
      .catch(() => undefined)
  }

  return (
    <section className="words">
      <header className="words__head">
        <span className="words__title">words over time</span>
        <span className="words__meta">how this article's vocabulary changed, 2003–2026</span>
        <button type="button" className="words__close" onClick={onClose}>
          close
        </button>
      </header>
      {!data && !error && <p className="words__status">Reading every sentence this article ever had…</p>}
      {error && <p className="words__status">Couldn't compare: {error}</p>}
      {data && (
        <>
          <p className="words__lede">
            Compared {data.deleted_sentences.toLocaleString()} deleted sentences with{' '}
            {data.surviving_sentences.toLocaleString()} surviving ones. Click words to chart them.
          </p>
          <div className="words__cols">
            <WordList title="wikipedia stopped saying" words={data.stopped_saying} picked={picked} onPick={toggle} kind="died" />
            <WordList title="wikipedia kept saying" words={data.kept_saying} picked={picked} onPick={toggle} kind="kept" />
          </div>

          <Chart
            years={data.years}
            lines={picked
              .map((stem, i) => {
                const series = data.series[stem] ?? extra[stem]?.series
                if (!series) return null
                const w = label[stem]
                return {
                  stem,
                  name: w ? `${w.word}${w.word_en ? ` (${w.word_en})` : ''}` : (extra[stem]?.label ?? stem),
                  color: COLORS[i % COLORS.length],
                  series,
                }
              })
              .filter((x): x is { stem: string; name: string; color: string; series: number[] } => !!x)}
          />

          <form
            className="words__track"
            onSubmit={(e) => {
              e.preventDefault()
              addWord()
            }}
          >
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="track any word, e.g. ruotsinkieliset" />
            <button type="submit">chart it</button>
          </form>
          <p className="words__foot">
            Method: {data.method}. Shares are per 100 sentences alive at the end of each year (MariaDB FOR SYSTEM_TIME).
            {data.translated_by ? ' English meanings by Gemma.' : ''}
          </p>
        </>
      )}
    </section>
  )
}

function WordList({
  title,
  words,
  picked,
  onPick,
  kind,
}: {
  title: string
  words: WordStat[]
  picked: string[]
  onPick: (s: string) => void
  kind: 'died' | 'kept'
}) {
  return (
    <div className={`words__list is-${kind}`}>
      <h4>{title}</h4>
      <ol>
        {words.map((w) => (
          <li key={w.stem}>
            <button type="button" className={picked.includes(w.stem) ? 'is-on' : ''} onClick={() => onPick(w.stem)}>
              <strong>{w.word}</strong>
              {w.word_en && <span className="words__en"> {w.word_en}</span>}
              <span className="words__nums">
                {kind === 'died' ? `${w.in_deleted} deleted · ${w.in_surviving} surviving` : `${w.in_surviving} surviving · ${w.in_deleted} deleted`}
                {w.first_year ? ` · ${w.first_year}–${w.last_year === 2026 ? 'now' : w.last_year}` : ''}
              </span>
            </button>
            {kind === 'died' && w.example_deleted && <p className="words__example">“{w.example_deleted}”</p>}
          </li>
        ))}
      </ol>
    </div>
  )
}

function Chart({ years, lines }: { years: number[]; lines: Array<{ stem: string; name: string; color: string; series: number[] }> }) {
  const W = 760
  const H = 240
  const P = { l: 40, r: 12, t: 12, b: 26 }
  const max = Math.max(1, ...lines.flatMap((l) => l.series))
  const x = (i: number) => P.l + (i * (W - P.l - P.r)) / Math.max(years.length - 1, 1)
  const y = (v: number) => H - P.b - (v / max) * (H - P.t - P.b)
  if (!lines.length) return <p className="words__status">Pick words above to chart them.</p>
  return (
    <figure className="words__chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Word use per year">
        {[0, 0.5, 1].map((f) => (
          <g key={f}>
            <line x1={P.l} x2={W - P.r} y1={y(max * f)} y2={y(max * f)} stroke="#d9d3c6" />
            <text x={P.l - 6} y={y(max * f) + 4} textAnchor="end" fontSize="10" fill="#555">
              {(max * f).toFixed(max < 5 ? 1 : 0)}
            </text>
          </g>
        ))}
        {years.map((yr, i) =>
          i % 3 === 0 || i === years.length - 1 ? (
            <text key={yr} x={x(i)} y={H - 8} textAnchor="middle" fontSize="10" fill="#555">
              {yr}
            </text>
          ) : null,
        )}
        {lines.map((l) => (
          <polyline
            key={l.stem}
            fill="none"
            stroke={l.color}
            strokeWidth="3"
            strokeLinejoin="round"
            points={l.series.map((v, i) => `${x(i)},${y(v)}`).join(' ')}
          />
        ))}
      </svg>
      <figcaption className="words__legend">
        {lines.map((l) => (
          <span key={l.stem}>
            <i style={{ background: l.color }} />
            {l.name}
          </span>
        ))}
        <span className="words__unit">sentences using the word, per 100 alive that year</span>
      </figcaption>
    </figure>
  )
}

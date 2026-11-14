import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { formatDate, languageMeanings, saveComparison, savedComparison } from '../lib/api'
import { compareInBrowser, hours } from '../lib/wikilang'
import type { LangCompare, LangEdition } from '../lib/types'
import '../styles/languages.css'

// One computation per topic at a time (React dev mode runs effects twice).
const inflight = new Map<string, Promise<LangCompare>>()

async function getComparison(title: string, lang: string, refresh: boolean, onProgress: (done: string[], total: number) => void) {
  if (!refresh) {
    const saved = await savedComparison(title, lang).catch(() => null)
    if (saved) return saved
  }
  const key = `${lang}:${title}`
  let p = inflight.get(key)
  if (!p) {
    p = compareInBrowser(title, lang, onProgress).then(async (report) => {
      await saveComparison(title, lang, report).catch(() => undefined) // still works without the database
      return report
    })
    inflight.set(key, p)
    void p.finally(() => inflight.delete(key)).catch(() => undefined)
  }
  return p
}

const EXAMPLES = [
  { label: 'Finnish Civil War (1918)', lang: 'fi', title: 'Suomen sisällissota' },
  { label: 'Russian invasion of Ukraine', lang: 'en', title: 'Russian invasion of Ukraine' },
  { label: 'Winter War', lang: 'fi', title: 'Talvisota' },
]

/** Same story, every language: how each Wikipedia names a topic, and where it fought about it. */
export function Languages() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const title = params.get('title') ?? ''
  const lang = params.get('lang') ?? 'fi'
  const [draftTitle, setDraftTitle] = useState(title)
  const [draftLang, setDraftLang] = useState(lang)
  const [data, setData] = useState<LangCompare | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [translating, setTranslating] = useState(false)
  const [progress, setProgress] = useState<{ done: string[]; total: number } | null>(null)

  function load(refresh = false) {
    if (!title) return
    setLoading(true)
    setError(null)
    if (!refresh) setData(null)
    setProgress(null)
    getComparison(title, lang, refresh, (done, total) => setProgress({ done, total }))
      .then((d) => {
        setData(d)
        // English meanings come from Gemma in a second, slower step.
        if (!d.translated_by && d.editions.some((e) => e.lang !== 'en')) {
          setTranslating(true)
          languageMeanings(title, lang)
            .then((m) => {
              if (m.translated_by) setData(m)
            })
            .catch(() => undefined)
            .finally(() => setTranslating(false))
        }
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    setDraftTitle(title)
    setDraftLang(lang)
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [title, lang])

  function go(t: string, l: string) {
    if (t.trim()) navigate(`/languages?lang=${encodeURIComponent(l)}&title=${encodeURIComponent(t.trim())}`)
  }

  return (
    <main className="langs">
      <Link className="langs__back" to="/">
        ← Ghosts of Wikipedia
      </Link>
      <h1 className="langs__title">same story, every language</h1>
      <p className="langs__lede">
        Every Wikipedia names things its own way. See what each language calls a topic, every time the title was
        renamed or renamed back, and how hard each edition fought over it.
      </p>

      <form
        className="langs__form"
        onSubmit={(e) => {
          e.preventDefault()
          go(draftTitle, draftLang)
        }}
      >
        <select value={draftLang} onChange={(e) => setDraftLang(e.target.value)} aria-label="Wikipedia language">
          {['fi', 'en', 'sv', 'ru', 'uk', 'de', 'pl', 'fr', 'et'].map((l) => (
            <option key={l} value={l}>
              {l}.wikipedia
            </option>
          ))}
        </select>
        <input
          value={draftTitle}
          onChange={(e) => setDraftTitle(e.target.value)}
          placeholder="exact article title, e.g. Suomen sisällissota"
          aria-label="Article title"
        />
        <button type="submit">compare</button>
      </form>
      <p className="langs__examples">
        try:{' '}
        {EXAMPLES.map((x) => (
          <button key={x.title} type="button" onClick={() => go(x.title, x.lang)}>
            {x.label}
          </button>
        ))}
      </p>

      {loading && !data && (
        <p className="langs__status">
          {progress
            ? `Reading ${progress.total} Wikipedias… ${progress.done.length}/${progress.total} ${progress.done.map((l) => l.toUpperCase()).join(' ✓ ')}${progress.done.length ? ' ✓' : ''}`
            : 'Finding every language edition…'}
        </p>
      )}
      {error && <p className="langs__status">Couldn’t compare: {error}</p>}

      {data && (
        <>
          <section className="langs__summary">
            <p className="langs__headline">
              <strong>{data.query.title}</strong> exists in {data.languages_available} languages. Across the{' '}
              {data.editions.length} shown: {data.summary.renames} title changes ({data.summary.renames_undone} undone),{' '}
              {data.summary.locks} locks, {data.summary.names} other names.
            </p>
            <p className="langs__meta">
              Live from Wikipedia · {data.cached ? 'saved snapshot' : 'fetched'} {formatDate(data.fetched_at)}
              {data.translated_by
                ? ` · English meanings by ${data.translated_by}`
                : translating
                  ? ' · Gemma is translating…'
                  : ''}{' '}
              ·{' '}
              <button type="button" onClick={() => load(true)} disabled={loading}>
                {loading ? 'refreshing…' : 'refresh'}
              </button>
            </p>
          </section>

          <div className="langs__grid">
            {data.editions.map((e) => (
              <EditionCard key={e.lang} e={e} />
            ))}
          </div>

          <p className="langs__note">
            Signals measure editing behaviour (renames, reversals, locks, reverts). They never say which name is right.
            Every refresh is kept in MariaDB with system versioning, so you can see how the names change over time.
          </p>
        </>
      )}
    </main>
  )
}

function EditionCard({ e }: { e: LangEdition }) {
  const [allNames, setAllNames] = useState(false)
  const names = allNames ? e.names : e.names.slice(0, 10)
  const pct = e.recent.edits ? Math.round((100 * e.recent.reverted) / e.recent.edits) : 0

  return (
    <article className={`edition ${e.signals?.length ? 'has-signals' : ''}`}>
      <header className="edition__head">
        <span className="edition__lang">{e.lang}</span>
        <span className="edition__language">
          {e.language}
          {e.autonym && e.autonym !== e.language ? ` · ${e.autonym}` : ''}
        </span>
      </header>

      <h2 className="edition__title">
        {e.url ? (
          <a href={e.url} target="_blank" rel="noreferrer">
            {e.title}
          </a>
        ) : (
          e.title
        )}
      </h2>
      {e.title_en && <p className="edition__en">“{e.title_en}”</p>}

      {e.error ? (
        <p className="edition__muted">Couldn’t read this edition: {e.error}</p>
      ) : (
        <>
          {e.first_sentence && (
            <blockquote className="edition__lead">
              {e.first_sentence}
              {e.first_sentence_en && <span className="edition__en">{e.first_sentence_en}</span>}
            </blockquote>
          )}

          {!!e.signals?.length && (
            <ul className="edition__signals">
              {e.signals.map((s) => (
                <li key={s.kind} title={s.explain}>
                  <strong>{s.label}</strong>
                  <span>{s.explain}</span>
                </li>
              ))}
            </ul>
          )}

          {e.renames.length > 0 && (
            <>
              <h3 className="edition__sub">title history</h3>
              <ol className="edition__renames">
                {e.renames.map((m) => (
                  <li key={`${m.ts}-${m.to}`} className={m.reverses ? 'is-reversal' : ''}>
                    <span className="edition__date">{formatDate(m.ts)}</span>
                    <span>
                      {m.from} → <strong>{m.to}</strong>
                      {m.undone_after_hours !== undefined && (
                        <em className="edition__undone"> undone after {hours(m.undone_after_hours)}</em>
                      )}
                      {m.reason && (
                        <span className="edition__reason">
                          “{m.reason}”{m.reason_en && m.reason_en !== m.reason ? ` (${m.reason_en})` : ''}
                        </span>
                      )}
                    </span>
                  </li>
                ))}
              </ol>
            </>
          )}

          {e.names.length > 0 && (
            <>
              <h3 className="edition__sub">also called ({e.names.length})</h3>
              <p className="edition__names">
                {names.map((n) => (
                  <span key={n}>{n}</span>
                ))}
                {e.names.length > 10 && (
                  <button type="button" onClick={() => setAllNames((v) => !v)}>
                    {allNames ? 'fewer' : `+${e.names.length - 10} more`}
                  </button>
                )}
              </p>
            </>
          )}

          <p className="edition__muted">
            {e.recent.reverted} of the last {e.recent.edits} edits reverted ({pct}%)
            {e.recent.since ? ` · since ${formatDate(e.recent.since)}` : ''} · locked {e.locks}×
          </p>
        </>
      )}
    </article>
  )
}

import { useEffect, useState } from 'react'
import { formatDate, getLiveNow } from '../lib/api'
import type { LangMode, LiveNow } from '../lib/types'

type Props = { pageId: number; lang: LangMode; onClose: () => void }

/** Live now: today's Wikipedia (read through Context.dev) vs the end of our history. */
export function LivePanel({ pageId, lang, onClose }: Props) {
  const [data, setData] = useState<LiveNow | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(true)
  const [open, setOpen] = useState<'gone' | 'rewritten' | 'new' | null>('gone')

  function load(refresh = false) {
    setBusy(true)
    setError(null)
    getLiveNow(pageId, refresh)
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setBusy(false))
  }

  useEffect(() => {
    setData(null)
    load(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pageId])

  const text = (fi: string, en?: string | null) => (lang === 'en' && en ? en : fi)

  return (
    <section className="live">
      <header className="live__head">
        <span className="live__title">live now</span>
        <span className="live__meta">today's Wikipedia, read through Context.dev</span>
        <button type="button" className="live__close" onClick={onClose}>
          close
        </button>
      </header>

      {busy && !data && <p className="live__status">Reading today's article on fi.wikipedia.org…</p>}
      {error && <p className="live__status">Couldn't go live: {error}</p>}

      {data && (
        <>
          <p className="live__summary">
            Our history ends <strong>{data.snapshot ? formatDate(data.snapshot) : 'at the dataset'}</strong>. Since
            then: <strong>{data.counts.gone}</strong> sentences gone, <strong>{data.counts.rewritten}</strong>{' '}
            rewritten, <strong>{data.counts.new}</strong> new. {data.counts.unchanged} unchanged.
          </p>
          {data.match_quality < 0.5 && (
            <p className="live__warn">
              Today's page is laid out very differently from the snapshot, so treat these counts as rough.
            </p>
          )}

          <div className="live__tabs">
            {(['gone', 'rewritten', 'new'] as const).map((k) => (
              <button
                key={k}
                type="button"
                className={open === k ? 'is-on' : ''}
                onClick={() => setOpen(open === k ? null : k)}
              >
                {k === 'gone' ? 'died since' : k === 'new' ? 'born since' : 'rewritten'} ({data.counts[k]})
              </button>
            ))}
          </div>

          {open === 'gone' && (
            <ul className="live__list">
              {data.gone.length === 0 && <li className="live__empty">Nothing has died since our snapshot.</li>}
              {data.gone.map((g) => (
                <li key={g.hash} className="live__ghost">
                  {text(g.text_fi, g.text_en)}
                </li>
              ))}
            </ul>
          )}
          {open === 'rewritten' && (
            <ul className="live__list">
              {data.rewritten.length === 0 && <li className="live__empty">No rewrites since our snapshot.</li>}
              {data.rewritten.map((r) => (
                <li key={r.hash}>
                  <span className="live__before">{text(r.before, r.before_en)}</span>
                  <span className="live__after">→ {r.after}</span>
                </li>
              ))}
            </ul>
          )}
          {open === 'new' && (
            <ul className="live__list">
              {data.new.length === 0 && <li className="live__empty">No new sentences since our snapshot.</li>}
              {data.new.map((n, i) => (
                <li key={i} className="live__new">
                  {n.text_fi}
                </li>
              ))}
            </ul>
          )}

          <p className="live__foot">
            <a href={data.url} target="_blank" rel="noreferrer">
              live article
            </a>{' '}
            · {data.cached ? 'checked' : 'read'} {formatDate(data.fetched_at)} · every check is kept in MariaDB ·{' '}
            <button type="button" onClick={() => load(true)} disabled={busy}>
              {busy ? 'reading…' : 'check again'}
            </button>
          </p>
        </>
      )}
    </section>
  )
}

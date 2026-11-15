import { useEffect, useState } from 'react'
import type { GhostCertificate, LangMode, WebEcho } from '../lib/types'
import { formatDate, formatYear, getWebEcho } from '../lib/api'

type Props = {
  data: GhostCertificate | null
  open: boolean
  lang?: LangMode
  onClose: () => void
  onShowWhen: (iso: string) => void
  onTombstone: () => void
}

export function Certificate({ data, open, lang = 'fi', onClose, onShowWhen, onTombstone }: Props) {
  const last = data?.lives[data.lives.length - 1]
  const who =
    last?.removed_by.anonymous || !last?.removed_by.user ? 'anonymous' : last.removed_by.user
  const quote =
    lang === 'en'
      ? (data?.text_en ?? data?.text_fi)
      : lang === 'both' && data?.text_en
        ? `${data.text_fi}\n\n${data.text_en}`
        : data?.text_fi

  return (
    <aside className={`certificate-drawer ${open && data ? 'is-open' : ''}`} aria-hidden={!open}>
      {data && last && (
        <>
          <div className="certificate-drawer__top">
            <p className="certificate-drawer__tag">caught</p>
            <button type="button" className="certificate-drawer__close" onClick={onClose}>
              close
            </button>
          </div>

          <p className="certificate-drawer__quote">{quote}</p>

          <div className="certificate-meta">
            <p>
              <strong>
                {formatYear(data.lives[0].born)}–{last.died ? formatYear(last.died) : 'now'}
              </strong>
              <span>{data.lives.length} lives</span>
            </p>
            <p>
              removed by <strong>{who}</strong>
            </p>
            <p className="certificate-meta__summary">“{last.edit_summary || 'no reason given'}”</p>
          </div>

          {data.reincarnated_as && (
            <p className="certificate-reincarnated">
              came back as:{' '}
              {lang === 'en'
                ? (data.reincarnated_as.text_en ?? data.reincarnated_as.text_fi)
                : data.reincarnated_as.text_fi}
            </p>
          )}

          {(data.coordination?.evidence?.length ?? 0) > 0 && (
            <div className="certificate-score">
              <p className="score">{data.coordination?.score ?? '–'}/100</p>
              <div className="evidence-chips">
                {(data.coordination?.evidence ?? []).map((chip) => (
                  <span className="evidence-chip" key={chip.label} title={chip.explain}>
                    {chip.value}
                  </span>
                ))}
              </div>
            </div>
          )}

          <WebEchoPanel pageId={data.page_id} hash={data.hash} />

          <div className="certificate-actions">
            <button type="button" className="primary" onClick={() => onShowWhen(last.died ?? data.lives[0].born)}>
              jump to that day
            </button>
            <button type="button" onClick={onTombstone}>
              make a tombstone
            </button>
          </div>
        </>
      )}
    </aside>
  )
}

/** Context.dev: does the live web still say what Wikipedia deleted? */
function WebEchoPanel({ pageId, hash }: { pageId: number; hash: string }) {
  const [echo, setEcho] = useState<WebEcho | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setEcho(null)
    setError(null)
  }, [pageId, hash])

  function run(refresh = false) {
    setBusy(true)
    setError(null)
    getWebEcho(pageId, hash, refresh)
      .then(setEcho)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setBusy(false))
  }

  const results = echo ? [...echo.exact, ...echo.related] : []
  return (
    <section className="web-echo">
      <p className="web-echo__title">still on the web?</p>
      {!echo && (
        <button type="button" className="web-echo__go" onClick={() => run(false)} disabled={busy}>
          {busy ? 'searching the live web…' : 'search the live web'}
        </button>
      )}
      {error && <p className="web-echo__muted">{error}</p>}
      {echo && (
        <>
          <p className={`web-echo__verdict is-${echo.status}`}>{echo.verdict}</p>
          {results.length > 0 && (
            <ul className="web-echo__list">
              {results.slice(0, 6).map((r) => (
                <li key={r.url}>
                  <a href={r.url} target="_blank" rel="noreferrer">
                    <span className="web-echo__domain">
                      {r.domain}
                      {r.wikipedia_copy ? ' · Wikipedia copy' : ''}
                      {echo.related.some((x) => x.url === r.url) ? ' · related' : ' · same wording'}
                    </span>
                    <span className="web-echo__page">{r.title}</span>
                  </a>
                </li>
              ))}
            </ul>
          )}
          <p className="web-echo__muted">
            Live search by Context.dev · {echo.cached ? 'saved' : 'checked'} {formatDate(echo.fetched_at)} ·{' '}
            <button type="button" className="web-echo__again" onClick={() => run(true)} disabled={busy}>
              {busy ? 'searching…' : 'check again'}
            </button>
          </p>
        </>
      )}
    </section>
  )
}

import type { GhostCertificate, LangMode } from '../lib/types'
import { formatYear } from '../lib/api'

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

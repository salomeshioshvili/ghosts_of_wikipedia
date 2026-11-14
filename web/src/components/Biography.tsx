import type { Biography as BiographyData, LangMode } from '../lib/types'
import { formatDate } from '../lib/api'

type Props = {
  data: BiographyData
  lang: LangMode
  /** Timestamp of the frame the time slider is on; the chapter we're "in" lights up. */
  currentTs: string | undefined
  onJump: (iso: string) => void
}

/** The article's life story (written by Gemma from its edit history). Click a chapter to travel there. */
export function Biography({ data, lang, currentTs, onJump }: Props) {
  const now = currentTs ? new Date(currentTs).getTime() : Infinity
  let active = -1
  data.chapters.forEach((c, i) => {
    if (new Date(c.ts).getTime() <= now) active = i
  })

  const title =
    lang === 'en' ? 'life story' : lang === 'fi' ? 'elämäntarina' : 'elämäntarina / life story'
  const meta =
    lang === 'en'
      ? `${data.chapters.length} chapters · written by Gemma from the edit history`
      : lang === 'fi'
        ? `${data.chapters.length} lukua · Gemma kirjoitti editointihistoriasta`
        : `${data.chapters.length} lukua · Gemma`

  return (
    <details className="bio" open>
      <summary className="bio__summary">
        <span className="bio__title">{title}</span>
        <span className="bio__meta">{meta}</span>
      </summary>
      <ol className="bio__list">
        {data.chapters.map((c, i) => {
          const fi = c.caption_fi ?? c.caption_en
          const en = c.caption_en
          return (
            <li key={c.ts} className={`bio__chapter ${i === active ? 'is-now' : ''}`}>
              <button type="button" onClick={() => onJump(c.ts)} title="Travel to this moment">
                <span className="bio__date">{formatDate(c.ts)}</span>
                <span className="bio__body">
                  {lang === 'en' ? (
                    <span className="bio__caption">{en}</span>
                  ) : lang === 'fi' ? (
                    <span className="bio__caption">{fi}</span>
                  ) : (
                    <>
                      <span className="bio__caption">{fi}</span>
                      <span className="bio__caption bio__caption--en">{en}</span>
                    </>
                  )}
                </span>
              </button>
            </li>
          )
        })}
      </ol>
    </details>
  )
}

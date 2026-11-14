import type { Biography as BiographyData } from '../lib/types'
import { formatDate } from '../lib/api'

type Props = {
  data: BiographyData
  /** Timestamp of the frame the time slider is on; the chapter we're "in" lights up. */
  currentTs: string | undefined
  onJump: (iso: string) => void
}

/** The article's life story (written by Gemma from its edit history). Click a chapter to travel there. */
export function Biography({ data, currentTs, onJump }: Props) {
  const now = currentTs ? new Date(currentTs).getTime() : Infinity
  let active = -1
  data.chapters.forEach((c, i) => {
    if (new Date(c.ts).getTime() <= now) active = i
  })

  return (
    <details className="bio" open>
      <summary className="bio__summary">
        <span className="bio__title">life story</span>
        <span className="bio__meta">{data.chapters.length} chapters · written by Gemma from the edit history</span>
      </summary>
      <ol className="bio__list">
        {data.chapters.map((c, i) => (
          <li key={c.ts} className={`bio__chapter ${i === active ? 'is-now' : ''}`}>
            <button type="button" onClick={() => onJump(c.ts)} title="Travel to this moment">
              <span className="bio__date">{formatDate(c.ts)}</span>
              <span className="bio__caption">{c.caption_en}</span>
            </button>
          </li>
        ))}
      </ol>
    </details>
  )
}

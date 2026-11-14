import type { GhostSummary, LangMode } from '../lib/types'

type Props = {
  ghosts: GhostSummary[]
  lang: LangMode
  caught: Set<string>
  focusHash: string | null
  onCatch: (hash: string) => void
}

export function GhostLayer({ ghosts, lang, caught, focusHash, onCatch }: Props) {
  if (ghosts.length === 0) return null

  return (
    <div className="ghost-layer" aria-label="Deleted sentences">
      {ghosts.map((g) => {
        const isCaught = caught.has(g.hash)
        return (
          <button
            key={g.hash}
            type="button"
            className={[
              'ghost-line',
              g.rarity === 'rare' ? 'is-rare' : '',
              isCaught ? 'is-caught' : '',
              focusHash === g.hash ? 'is-focus' : '',
            ]
              .filter(Boolean)
              .join(' ')}
            onClick={() => onCatch(g.hash)}
          >
            {lang === 'en' ? (
              <span>{g.text_en ?? g.text_fi}</span>
            ) : (
              <>
                <span>{g.text_fi}</span>
                {lang === 'both' && g.text_en && <span className="ghost-line__en">{g.text_en}</span>}
              </>
            )}
          </button>
        )
      })}
    </div>
  )
}

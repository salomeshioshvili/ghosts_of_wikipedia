import { useMemo } from 'react'
import type { TimelineFrame } from '../lib/types'

type Props = {
  frames: TimelineFrame[]
  index: number
  playing: boolean
  onIndexChange: (index: number) => void
  onTogglePlay: () => void
}

function yearOf(iso: string) {
  return new Date(iso).getUTCFullYear()
}

export function TimeSlider({ frames, index, playing, onIndexChange, onTogglePlay }: Props) {
  const current = frames[index]
  const year = current ? yearOf(current.ts) : '—'
  const startYear = frames[0] ? yearOf(frames[0].ts) : 2002
  const endYear = frames.length ? yearOf(frames[frames.length - 1].ts) : 2026

  const bars = useMemo(() => {
    if (!frames.length) return []
    const max = Math.max(...frames.map((f) => Math.max(f.edits, f.deaths, 1)))
    return frames.map((f) => ({
      edits: Math.max(12, (f.edits / max) * 100),
      deaths: f.deaths > 0 ? Math.max(18, (f.deaths / max) * 100) : 0,
      deathsCount: f.deaths,
    }))
  }, [frames])

  return (
    <div className="timeline-bar" role="region" aria-label="Scrub article through time">
      <button
        type="button"
        className="timeline-bar__play"
        onClick={onTogglePlay}
        aria-label={playing ? 'Pause' : 'Play time-lapse'}
      >
        {playing ? 'Pause' : 'Play'}
      </button>

      <div className="timeline-bar__track">
        <div className="timeline-bar__top">
          <span className="timeline-bar__hint">when</span>
          <span className="timeline-bar__year">{year}</span>
        </div>

        <div className="timeline-bar__bars" aria-hidden>
          {bars.map((b, i) => (
            <button
              key={frames[i].ts}
              type="button"
              className={`timeline-bar__col ${i === index ? 'is-now' : ''}`}
              onClick={() => onIndexChange(i)}
              title={`${yearOf(frames[i].ts)} · ${frames[i].deaths} deaths`}
            >
              <span className="timeline-bar__edit" style={{ height: `${b.edits}%` }} />
              {b.deaths > 0 && (
                <span className="timeline-bar__death" style={{ height: `${b.deaths}%` }} />
              )}
            </button>
          ))}
        </div>

        <input
          className="timeline-bar__range"
          type="range"
          min={0}
          max={Math.max(frames.length - 1, 0)}
          value={index}
          onChange={(e) => onIndexChange(Number(e.target.value))}
          aria-valuetext={String(year)}
        />

        <div className="timeline-bar__ends">
          <span>{startYear}</span>
          <span className="timeline-bar__legend">
            <i className="is-edit" /> edits <i className="is-death" /> deletions
          </span>
          <span>{endYear}</span>
        </div>
      </div>
    </div>
  )
}

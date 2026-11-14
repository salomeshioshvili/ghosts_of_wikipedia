type Face = {
  x: number
  y: number
  scale?: number
  fill: string
  blush?: boolean
  smile?: 'happy' | 'ooo' | 'smirk'
  pupil: [number, number]
}

const ghosts: Face[] = [
  { x: 28, y: 14, fill: '#f3efe6', blush: true, smile: 'happy', pupil: [1.2, 0.8] },
  { x: 108, y: 6, scale: 1.08, fill: 'var(--yellow)', smile: 'ooo', pupil: [-1.4, 1] },
  { x: 192, y: 12, fill: '#f3efe6', blush: true, smile: 'smirk', pupil: [1.6, -0.4] },
  { x: 272, y: 8, scale: 0.95, fill: '#f3efe6', smile: 'happy', pupil: [-0.8, 1.2] },
]

function GhostBody({
  x,
  y,
  scale = 1,
  fill,
  blush,
  smile = 'happy',
  pupil,
}: Face) {
  const mouth =
    smile === 'ooo' ? (
      <ellipse cx="30" cy="48" rx="4" ry="5" fill="#121820" />
    ) : smile === 'smirk' ? (
      <path
        d="M22 46c4 5 12 6 18 1"
        stroke="#121820"
        strokeWidth="2.6"
        strokeLinecap="round"
        fill="none"
      />
    ) : (
      <path
        d="M21 45c5 7 13 7 18 0"
        stroke="#121820"
        strokeWidth="2.6"
        strokeLinecap="round"
        fill="none"
      />
    )

  return (
    <g transform={`translate(${x} ${y})`}>
      <g className="blob-ghost">
        <g transform={`scale(${scale})`}>
          <ellipse cx="30" cy="78" rx="16" ry="3.5" fill="#121820" opacity="0.18" />
          <path
            d="M30 4c-16 0-28 13-28 34v28c0 2.2 1.6 3.2 3.2 2.2l5.2-2.6c1.4-.7 2.8.1 3.4 1.4l2.8 5.4c.7 1.4 2.8 1.4 3.5 0l3.2-6.2c.6-1.2 2.5-1.2 3.1 0l3.2 6.2c.7 1.4 2.8 1.4 3.5 0l2.8-5.4c.6-1.3 2-2.1 3.4-1.4l5.2 2.6c1.6 1 3.2 0 3.2-2.2V38C58 17 46 4 30 4z"
            fill={fill}
            stroke="#121820"
            strokeWidth="3"
            strokeLinejoin="round"
          />
          <circle cx="20" cy="34" r="7.2" fill="#fff" stroke="#121820" strokeWidth="2" />
          <circle cx="40" cy="34" r="7.2" fill="#fff" stroke="#121820" strokeWidth="2" />
          <circle cx={20 + pupil[0]} cy={34 + pupil[1]} r="3.1" fill="#121820" />
          <circle cx={40 + pupil[0]} cy={34 + pupil[1]} r="3.1" fill="#121820" />
          <circle cx={21.4 + pupil[0]} cy={32.6 + pupil[1]} r="1.1" fill="#fff" />
          <circle cx={41.4 + pupil[0]} cy={32.6 + pupil[1]} r="1.1" fill="#fff" />
          {blush && (
            <>
              <ellipse cx="12" cy="42" rx="4" ry="2.2" fill="#f0a35e" opacity="0.45" />
              <ellipse cx="48" cy="42" rx="4" ry="2.2" fill="#f0a35e" opacity="0.45" />
            </>
          )}
          {mouth}
        </g>
      </g>
    </g>
  )
}

/** Cute sheet-ghosts for the home poster */
export function BlobGhosts() {
  return (
    <svg className="blob-ghosts" viewBox="0 0 360 100" aria-hidden>
      {ghosts.map((g, i) => (
        <GhostBody key={i} {...g} />
      ))}
    </svg>
  )
}

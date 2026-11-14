type Props = {
  className?: string
  size?: number
}

/** Soft sheet-ghost with a tiny hat */
export function GhostMascot({ className = '', size = 160 }: Props) {
  return (
    <svg
      className={`ghost-mascot ${className}`}
      width={size}
      height={size}
      viewBox="0 0 120 140"
      fill="none"
      aria-hidden
    >
      <ellipse cx="60" cy="128" rx="26" ry="5" fill="#7ee0d2" opacity="0.22" />
      <path
        d="M60 18c-24 0-42 18-42 48v46c0 3 2 4 4 3l8-4c2-1 4 0 5 2l5 8c1 2 4 2 5 0l6-9c1-2 4-2 5 0l6 9c1 2 4 2 5 0l5-8c1-2 3-3 5-2l8 4c2 1 4 0 4-3V66C102 36 84 18 60 18z"
        fill="url(#ghostFill)"
      />
      <ellipse cx="46" cy="62" rx="7" ry="9" fill="#171c2b" />
      <ellipse cx="74" cy="62" rx="7" ry="9" fill="#171c2b" />
      <circle cx="48.5" cy="59.5" r="2.2" fill="#ebe6da" opacity="0.95" />
      <circle cx="76.5" cy="59.5" r="2.2" fill="#ebe6da" opacity="0.95" />
      <path d="M54 78c3.2 5.5 9.2 5.5 12.4 0" stroke="#171c2b" strokeWidth="3" strokeLinecap="round" />
      <path
        d="M50 24c1-9 9-15 18-13 6 1.2 10 6.2 9.5 12.2-.3 4-2.4 7-5.5 8.8"
        fill="#171c2b"
      />
      <circle cx="68" cy="14" r="5.2" fill="#171c2b" />
      <path d="M68 14c8 2 13.5 7.5 12 15" stroke="#f0a35e" strokeWidth="2.4" strokeLinecap="round" />
      <defs>
        <linearGradient id="ghostFill" x1="30" y1="20" x2="90" y2="120" gradientUnits="userSpaceOnUse">
          <stop stopColor="#f7f3ea" />
          <stop offset="1" stopColor="#cfeff0" />
        </linearGradient>
      </defs>
    </svg>
  )
}

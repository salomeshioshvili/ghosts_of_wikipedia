import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { formatYear, getGhost } from '../lib/api'
import type { GhostCertificate } from '../lib/types'
import '../styles/tombstone.css'

export function Tombstone() {
  const { pageId = '1150', hash = 'cd34' } = useParams()
  const [data, setData] = useState<GhostCertificate | null>(null)

  useEffect(() => {
    void getGhost(Number(pageId), hash).then(setData)
  }, [pageId, hash])

  if (!data) {
    return (
      <main className="tomb-page">
        <p className="tomb-page__note">carving…</p>
      </main>
    )
  }

  const first = data.lives[0]
  const last = data.lives[data.lives.length - 1]
  const born = first ? formatYear(first.born) : '??'
  const died = last ? formatYear(last.died) : '??'
  const epitaph = last?.edit_summary?.trim() || 'nobody wrote why'

  return (
    <main className="tomb-page">
      <Link className="tomb-page__back" to={`/article/${pageId}`}>
        ← back
      </Link>

      <div className="tomb-stack">
        <article className="tombstone">
          <p className="tombstone__rip">R.I.P.</p>

          <svg className="tombstone__ghost" viewBox="0 0 64 72" aria-hidden>
            <path
              d="M32 8c-14 0-24 11-24 28v22c0 2 1.5 3 3 2l6-3c1.5-.7 3 0 3.5 1.5l3 6c.8 1.5 3 1.5 3.8 0l4-7c.7-1.3 2.8-1.3 3.5 0l4 7c.8 1.5 3 1.5 3.8 0l3-6c.5-1.5 2-2.2 3.5-1.5l6 3c1.5 1 3 0 3-2V36C56 19 46 8 32 8z"
              fill="var(--yellow)"
              stroke="var(--ink)"
              strokeWidth="3"
            />
            <circle cx="24" cy="34" r="4" fill="var(--ink)" />
            <circle cx="40" cy="34" r="4" fill="var(--ink)" />
            <path
              d="M27 44c2.5 4 7.5 4 10 0"
              stroke="var(--ink)"
              strokeWidth="2.5"
              strokeLinecap="round"
              fill="none"
            />
          </svg>

          <h1 className="tombstone__name">{data.text_en ?? data.text_fi}</h1>
          <p className="tombstone__dates">
            {born}–{died}
          </p>
          <p className="tombstone__epitaph">“{epitaph}”</p>
        </article>
        <div className="tombstone__base" aria-hidden />
      </div>
    </main>
  )
}

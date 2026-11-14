import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { formatDate, searchGhosts } from '../lib/api'
import type { SearchHit } from '../lib/types'

export function Search() {
  const [params] = useSearchParams()
  const q = params.get('q') ?? ''
  const [hits, setHits] = useState<SearchHit[]>([])

  useEffect(() => {
    void searchGhosts(q).then(setHits)
  }, [q])

  return (
    <main
      style={{
        width: 'min(100%, 42rem)',
        margin: '0 auto',
        padding: '2rem 1.25rem 3rem',
      }}
    >
      <Link to="/" style={{ color: 'var(--cream)', fontSize: '0.9rem', fontWeight: 700 }}>
        ← home
      </Link>
      <h1
        style={{
          fontFamily: 'var(--font-poster)',
          fontSize: '2.4rem',
          margin: '0.85rem 0 0.35rem',
          letterSpacing: '0.02em',
        }}
      >
        search results
      </h1>
      <p style={{ color: 'var(--cream)', marginBottom: '1.25rem', fontWeight: 700 }}>
        for “{q || 'everything weird'}”
      </p>
      <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'grid', gap: '0.65rem' }}>
        {hits.map((h) => (
          <li key={`${h.page_id}-${h.hash}`}>
            <Link
              to={`/article/${h.page_id}?ghost=${h.hash}`}
              style={{
                display: 'block',
                background: 'var(--cream)',
                color: 'var(--ink)',
                border: '3px solid var(--ink)',
                padding: '0.9rem 1rem',
              }}
            >
              <p style={{ margin: 0, fontSize: '0.75rem', fontWeight: 700 }}>
                {h.title_en} · died {formatDate(h.died)}
              </p>
              <p
                style={{
                  margin: '0.45rem 0 0',
                  fontFamily: 'var(--font-read)',
                  fontSize: '1.05rem',
                  fontStyle: 'italic',
                  lineHeight: 1.4,
                }}
              >
                {h.text_en ?? h.text_fi}
              </p>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  )
}

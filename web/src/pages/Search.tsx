import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { formatDate, searchArticles, searchGhosts } from '../lib/api'
import type { FeaturedArticle, SearchHit } from '../lib/types'

const card = {
  display: 'block',
  background: 'var(--cream)',
  color: 'var(--ink)',
  border: '3px solid var(--ink)',
  padding: '0.9rem 1rem',
} as const

const heading = {
  fontFamily: 'var(--font-poster)',
  fontSize: '1.5rem',
  margin: '1.75rem 0 0.6rem',
  letterSpacing: '0.02em',
} as const

const list = { listStyle: 'none', padding: 0, margin: 0, display: 'grid', gap: '0.65rem' } as const

export function Search() {
  const [params] = useSearchParams()
  const q = params.get('q') ?? ''
  const [articles, setArticles] = useState<FeaturedArticle[]>([])
  const [hits, setHits] = useState<SearchHit[]>([])
  const [ghostNote, setGhostNote] = useState<string | null>(null)

  useEffect(() => {
    setArticles([])
    setHits([])
    setGhostNote(null)
    if (!q.trim()) return
    // 1. Articles by title: works for all 19,742 articles.
    void searchArticles(q).then(setArticles).catch(() => setArticles([]))
    // 2. Deleted sentences by meaning: needs the EmbeddingGemma vectors.
    void searchGhosts(q)
      .then(setHits)
      .catch(() => setGhostNote('Searching deleted text by meaning is not switched on yet.'))
  }, [q])

  return (
    <main style={{ width: 'min(100%, 42rem)', margin: '0 auto', padding: '2rem 1.25rem 3rem' }}>
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
      <p style={{ color: 'var(--cream)', marginBottom: '0.5rem', fontWeight: 700 }}>for “{q}”</p>

      <h2 style={heading}>articles</h2>
      {articles.length === 0 ? (
        <p style={{ color: 'var(--cream)' }}>No article titles match.</p>
      ) : (
        <ul style={list}>
          {articles.map((a) => (
            <li key={a.page_id}>
              <Link to={`/article/${a.page_id}`} style={card}>
                <p style={{ margin: 0, fontFamily: 'var(--font-read)', fontSize: '1.15rem', fontWeight: 700 }}>
                  {a.title_fi}
                </p>
                <p style={{ margin: '0.35rem 0 0', fontSize: '0.8rem', fontWeight: 700 }}>
                  {a.title_en ? `${a.title_en} · ` : ''}
                  {a.versions.toLocaleString()} versions ·{' '}
                  {a.loaded ? `${a.ghost_count} ghosts` : 'ghosts not summoned yet: open to summon them'}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}

      <h2 style={heading}>things wikipedia once said</h2>
      {ghostNote ? (
        <p style={{ color: 'var(--cream)' }}>{ghostNote}</p>
      ) : hits.length === 0 ? (
        <p style={{ color: 'var(--cream)' }}>No deleted sentences close to that.</p>
      ) : (
        <ul style={list}>
          {hits.map((h) => (
            <li key={`${h.page_id}-${h.hash}`}>
              <Link to={`/article/${h.page_id}?ghost=${h.hash}`} style={card}>
                <p style={{ margin: 0, fontSize: '0.75rem', fontWeight: 700 }}>
                  {h.title_en ?? h.title_fi} · died {formatDate(h.died)}
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
      )}
    </main>
  )
}

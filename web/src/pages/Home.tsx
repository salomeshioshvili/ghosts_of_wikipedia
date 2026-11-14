import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { BlobGhosts } from '../components/BlobGhosts'
import { getFeaturedArticles, getStats } from '../lib/api'
import type { FeaturedArticle, Stats } from '../lib/types'
import '../styles/home.css'

export function Home() {
  const navigate = useNavigate()
  const [articles, setArticles] = useState<FeaturedArticle[]>([])
  const [stats, setStats] = useState<Stats | null>(null)
  const [q, setQ] = useState('')

  useEffect(() => {
    void Promise.all([getFeaturedArticles(), getStats()]).then(([a, s]) => {
      setArticles(a)
      setStats(s)
    })
  }, [])

  const hero = articles.find((a) => a.page_id === 1150) ?? articles[0]

  function onHunt() {
    const query = q.trim()
    if (!query) return
    navigate(`/search?q=${encodeURIComponent(query)}`)
  }

  return (
    <main className="home">
      <header className="home__poster">
        <h1 className="home__title">
          Ghosts of <span className="home__title-accent">Wikipedia</span>
        </h1>
        <p className="home__point">Wikipedia only shows you the survivors. We show you the ghosts.</p>
        <BlobGhosts />
      </header>

      <section className="home__hero">
        <figure className="home__art-wrap">
          <img
            className="home__art"
            src="/art/human-stories.jpg"
            alt="Two ghosts reading a yellow book called Human Stories"
          />
        </figure>

        <div className="home__side">
          {hero && (
            <Link className="home__primary" to={`/article/${hero.page_id}`}>
              What did Wikipedia forget?
              <span>Finnish Civil War</span>
            </Link>
          )}

          <div className="home__search">
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') onHunt()
              }}
              placeholder="an article, or something Wikipedia once said..."
              aria-label="Search articles by title, or deleted text by meaning"
            />
            <button type="button" onClick={onHunt}>
              go
            </button>
          </div>

          <Link className="home__languages" to="/languages?lang=fi&title=Suomen%20sisällissota">
            Same story, every language →
            <span>what each Wikipedia calls a war, and where it fought about the name</span>
          </Link>
        </div>
      </section>

      <section className="home__haunted" aria-label="More articles">
        <h2 className="home__haunted-label">other hauntings</h2>
        <div className="home__cards">
          {articles.map((a) => (
            <Link className="haunt-card" key={a.page_id} to={`/article/${a.page_id}`}>
              <h3 className="haunt-card__fi">{a.title_en ?? a.title_fi}</h3>
              <p className="haunt-card__count">{a.ghost_count} ghosts</p>
            </Link>
          ))}
        </div>
      </section>

      {stats && (
        <p className="home__stats">
          {stats.articles.toLocaleString()} pages · {stats.ghosts.toLocaleString()} ghosts
        </p>
      )}
    </main>
  )
}

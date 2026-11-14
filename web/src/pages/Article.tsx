import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Biography } from '../components/Biography'
import { Certificate } from '../components/Certificate'
import { GhostLayer } from '../components/GhostLayer'
import { TimeSlider } from '../components/TimeSlider'
import {
  formatDate,
  getArticle,
  getBiography,
  getGhost,
  getTimeline,
} from '../lib/api'
import type {
  ArticlePayload,
  Biography as BiographyData,
  GhostCertificate,
  GhostSummary,
  LangMode,
  LivingSentence,
  TimelinePayload,
} from '../lib/types'
import '../styles/article.css'

type Block =
  | { type: 'living'; sentence: LivingSentence }
  | { type: 'ghosts'; afterHash: string; ghosts: GhostSummary[] }

export function Article() {
  const { pageId = '1150' } = useParams()
  const [params] = useSearchParams()
  const navigate = useNavigate()

  const [article, setArticle] = useState<ArticlePayload | null>(null)
  const [timeline, setTimeline] = useState<TimelinePayload | null>(null)
  const [lang, setLang] = useState<LangMode>('fi')
  const [showGhosts, setShowGhosts] = useState(true)
  const [caught, setCaught] = useState<Set<string>>(new Set())
  const [focusHash, setFocusHash] = useState<string | null>(params.get('ghost'))
  const [certificate, setCertificate] = useState<GhostCertificate | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [frameIndex, setFrameIndex] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [bio, setBio] = useState<BiographyData | null>(null)

  useEffect(() => {
    setArticle(null)
    setTimeline(null)
    setLoadError(null)
    setBio(null)
    void getBiography(Number(pageId)).then(setBio)
    // The first visit to an article processes its whole edit history on the server, so this can take a while.
    void getArticle(Number(pageId))
      .then((a) => Promise.all([a, getTimeline(Number(pageId))]))
      .then(([a, t]) => {
        setArticle(a)
        setTimeline(t)
        setFrameIndex(Math.max(t.frames.length - 1, 0))
      })
      .catch((e: unknown) => setLoadError(e instanceof Error ? e.message : String(e)))
  }, [pageId])

  useEffect(() => {
    const hash = params.get('ghost')
    if (!hash || !article) return
    setFocusHash(hash)
    void openGhost(hash)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params, article])

  useEffect(() => {
    if (!playing || !timeline) return
    const id = window.setInterval(() => {
      setFrameIndex((i) => {
        if (i >= timeline.frames.length - 1) {
          setPlaying(false)
          return i
        }
        return i + 1
      })
    }, 900)
    return () => window.clearInterval(id)
  }, [playing, timeline])

  const visible = useMemo(() => {
    if (!article || !timeline) {
      return { sentences: article?.sentences ?? [], ghosts: article?.ghosts ?? [] }
    }
    const frame = timeline.frames[frameIndex]
    if (!frame) return { sentences: article.sentences, ghosts: article.ghosts }

    const living = frame.hashes
      .map((hash, pos) => {
        const s = timeline.sentences[hash]
        if (!s || s.died) return null
        return {
          hash,
          text_fi: s.text_fi,
          text_en: s.text_en,
          section: article.sentences.find((x) => x.hash === hash)?.section ?? '',
          pos,
          born: s.born,
        } satisfies LivingSentence
      })
      .filter((x): x is LivingSentence => x !== null)

    // If frame only has living hashes, keep article ghosts that have died by this frame
    const frameTs = new Date(frame.ts).getTime()
    const ghosts = article.ghosts.filter((g) => new Date(g.died).getTime() <= frameTs)

    // Prefer article sentences when on latest frame for stable sections
    if (frameIndex === timeline.frames.length - 1) {
      return { sentences: article.sentences, ghosts: article.ghosts }
    }

    return { sentences: living.length ? living : article.sentences, ghosts }
  }, [article, timeline, frameIndex])

  const blocks = useMemo(() => {
    const byAfter = new Map<string, GhostSummary[]>()
    if (showGhosts) {
      for (const g of visible.ghosts) {
        const key = g.after_hash ?? ''
        const list = byAfter.get(key) ?? []
        list.push(g)
        byAfter.set(key, list)
      }
    }

    const out: Block[] = []
    const top = byAfter.get('')            // ghosts that stood before the first living sentence
    if (top?.length) out.push({ type: 'ghosts', afterHash: '', ghosts: top })
    for (const sentence of visible.sentences) {
      out.push({ type: 'living', sentence })
      const ghosts = byAfter.get(sentence.hash)
      if (ghosts?.length) out.push({ type: 'ghosts', afterHash: sentence.hash, ghosts })
    }
    return out
  }, [visible, showGhosts])

  const sections = useMemo(() => {
    const seen = new Set<string>()
    return visible.sentences
      .map((s) => s.section)
      .filter((section) => {
        if (!section || seen.has(section)) return false
        seen.add(section)
        return true
      })
  }, [visible.sentences])

  async function openGhost(hash: string) {
    const cert = await getGhost(Number(pageId), hash)
    setCertificate(cert)
    setDrawerOpen(true)
    setCaught((prev) => new Set(prev).add(hash))
    setFocusHash(hash)
  }

  /** Biography chapters: land on the first snapshot that already contains the change. */
  function jumpAfterIso(iso: string) {
    if (!timeline) return
    const t = new Date(iso).getTime()
    const i = timeline.frames.findIndex((f) => new Date(f.ts).getTime() >= t)
    setFrameIndex(i < 0 ? timeline.frames.length - 1 : i)
    setPlaying(false)
  }

  function jumpToIso(iso: string) {
    if (!timeline) return
    const t = new Date(iso).getTime()
    let best = 0
    timeline.frames.forEach((f, i) => {
      if (new Date(f.ts).getTime() <= t) best = i
    })
    setFrameIndex(best)
    setPlaying(false)
  }

  if (loadError) {
    return (
      <main style={{ padding: '3rem' }}>
        <p>The ghosts wouldn't come: {loadError}</p>
        <Link to="/">← home</Link>
      </main>
    )
  }
  if (!article || !timeline) {
    return (
      <main style={{ padding: '3rem' }}>
        <p>Summoning ghosts…</p>
        <p style={{ opacity: 0.7, fontSize: '0.9rem' }}>
          The first visit reads this article's whole edit history. Big articles take a minute; after that it's instant.
        </p>
      </main>
    )
  }

  return (
    <>
      <div className="article">
        <div className="article__nav">
          <Link className="article__back" to="/">
            ← Ghosts of Wikipedia
          </Link>
          <div className="article__toolbar">
            <span className="article__counter">
              {article.ghost_count} ghosts · {caught.size} caught
            </span>
            <button
              type="button"
              className={`chip ${showGhosts ? 'is-on' : ''}`}
              onClick={() => setShowGhosts((v) => !v)}
            >
              {showGhosts ? 'Ghosts on' : 'Ghosts off'}
            </button>
            <Link
              className="chip"
              to={`/languages?lang=fi&title=${encodeURIComponent(article.title_fi)}`}
              title="What other Wikipedias call this, and where they fought about it"
            >
              Other languages
            </Link>
            {(['en', 'fi', 'both'] as LangMode[]).map((mode) => (
              <button
                key={mode}
                type="button"
                className={`toggle ${lang === mode ? 'is-on' : ''}`}
                onClick={() => setLang(mode)}
              >
                {mode === 'both' ? 'Both' : mode.toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        <article className="article__main">
          <p className="article__howto">the dashed bits got deleted. click one. or smash Play.</p>
          {lang !== 'fi' &&
            article.sentences.length > 0 &&
            article.sentences.filter((s) => s.text_en).length < article.sentences.length * 0.5 && (
              <p className="article__en-hint">
                English is still being filled in — missing lines stay Finnish until the translate job catches up.
                Refresh in a few minutes.
              </p>
            )}
          <h1 className="article__title">
            {lang === 'en' && article.title_en ? article.title_en : article.title_fi}
          </h1>
          {lang === 'both' && article.title_en && (
            <p className="article__title-en">{article.title_en}</p>
          )}
          <p className="article__asof">{formatDate(timeline.frames[frameIndex]?.ts ?? article.as_of)}</p>
          {bio && bio.chapters.length > 0 && (
            <Biography
              data={bio}
              lang={lang}
              currentTs={timeline.frames[frameIndex]?.ts}
              onJump={jumpAfterIso}
            />
          )}

          {sections.map((section) => (
            <div key={section}>
              <h2 className="article__section">{section}</h2>
              {blocks
                .filter((b) =>
                  b.type === 'living'
                    ? b.sentence.section === section
                    : b.ghosts[0]?.section === section,
                )
                .map((b) =>
                  b.type === 'living' ? (
                    <div
                      key={b.sentence.hash}
                      className={`sentence-block ${
                        timeline.sentences[b.sentence.hash]?.contested ? 'is-contested' : ''
                      }`}
                      id={`s-${b.sentence.hash}`}
                    >
                      {lang === 'en' ? (
                        <p className="sentence-block__fi">{b.sentence.text_en ?? b.sentence.text_fi}</p>
                      ) : (
                        <p className="sentence-block__fi">{b.sentence.text_fi}</p>
                      )}
                      {lang === 'both' && b.sentence.text_en && (
                        <p className="sentence-block__en">{b.sentence.text_en}</p>
                      )}
                    </div>
                  ) : (
                    <GhostLayer
                      key={`g-${b.afterHash}`}
                      ghosts={b.ghosts}
                      lang={lang}
                      caught={caught}
                      focusHash={focusHash}
                      onCatch={(hash) => void openGhost(hash)}
                    />
                  ),
                )}
            </div>
          ))}
        </article>

        <div className="ghost-rail" aria-hidden>
          {visible.ghosts.map((g, i) => (
            <button
              key={g.hash}
              type="button"
              className={`ghost-rail__mark ${g.rarity === 'rare' ? 'is-rare' : ''} ${caught.has(g.hash) ? 'is-caught' : ''}`}
              style={{ top: `${8 + i * (80 / Math.max(visible.ghosts.length, 1))}%` }}
              onClick={() => void openGhost(g.hash)}
              title={g.text_en ?? g.text_fi}
            />
          ))}
        </div>
      </div>

      <TimeSlider
        frames={timeline.frames}
        index={frameIndex}
        playing={playing}
        onIndexChange={setFrameIndex}
        onTogglePlay={() => {
          if (!playing && frameIndex >= timeline.frames.length - 1) setFrameIndex(0)
          setPlaying((p) => !p)
        }}
      />

      <Certificate
        data={certificate}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        onShowWhen={jumpToIso}
        onTombstone={() => {
          if (certificate) navigate(`/tombstone/${pageId}/${certificate.hash}`)
        }}
      />
    </>
  )
}

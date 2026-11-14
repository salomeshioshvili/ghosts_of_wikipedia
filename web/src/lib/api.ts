import type {
  ArticlePayload,
  FeaturedArticle,
  GhostCertificate,
  SearchHit,
  Stats,
  TimelinePayload,
  Biography,
  LangCompare,
} from './types'

import articlesFeatured from '../../../mock/articles_featured.json'
import article1150 from '../../../mock/article_1150.json'
import timeline1150 from '../../../mock/timeline_1150.json'
import ghostCd34 from '../../../mock/ghost_cd34.json'
import searchHits from '../../../mock/search.json'
import stats from '../../../mock/stats.json'
import biography1150 from '../../../mock/biography_1150.json'

// Real API by default; run `VITE_USE_MOCK=1 npm run dev` for the mock files.
const USE_MOCK = import.meta.env.VITE_USE_MOCK === '1'

async function fromApi<T>(path: string): Promise<T> {
  const res = await fetch(path)
  if (!res.ok) throw new Error(`API ${path} failed: ${res.status}`)
  return res.json() as Promise<T>
}

export async function getFeaturedArticles(): Promise<FeaturedArticle[]> {
  if (USE_MOCK) return articlesFeatured as FeaturedArticle[]
  return fromApi('/api/articles?featured=1')
}

/** Search all 19,742 articles by title. `loaded: false` = its ghosts are summoned on first open. */
export async function searchArticles(q: string): Promise<FeaturedArticle[]> {
  if (USE_MOCK) {
    const needle = q.trim().toLowerCase()
    return (articlesFeatured as FeaturedArticle[]).filter(
      (a) => a.title_fi.toLowerCase().includes(needle) || a.title_en?.toLowerCase().includes(needle),
    )
  }
  return fromApi(`/api/articles?q=${encodeURIComponent(q)}&limit=20`)
}

export async function getStats(): Promise<Stats> {
  if (USE_MOCK) return stats as Stats
  return fromApi('/api/stats')
}

export async function getArticle(pageId: number, asOf?: string): Promise<ArticlePayload> {
  if (USE_MOCK) {
    if (pageId !== 1150) {
      return { ...(article1150 as ArticlePayload), page_id: pageId }
    }
    return article1150 as ArticlePayload
  }
  const q = asOf ? `?as_of=${encodeURIComponent(asOf)}` : ''
  return fromApi(`/api/articles/${pageId}${q}`)
}

export async function getTimeline(pageId: number): Promise<TimelinePayload> {
  if (USE_MOCK) return timeline1150 as TimelinePayload
  return fromApi(`/api/articles/${pageId}/timeline`)
}

export async function getGhost(pageId: number, hash: string): Promise<GhostCertificate> {
  if (USE_MOCK) {
    if (hash === 'cd34') return ghostCd34 as GhostCertificate
    const article = await getArticle(pageId)
    const g = article.ghosts.find((x) => x.hash === hash)
    return {
      hash,
      page_id: pageId,
      text_fi: g?.text_fi ?? '',
      text_en: g?.text_en ?? null,
      kind: g?.kind ?? 'erased',
      rarity: g?.rarity ?? 'common',
      event_tag: g?.event_tag,
      lives: [
        {
          born: g?.born ?? '',
          born_rev: 1,
          died: g?.died ?? '',
          died_rev: 2,
          removed_by: { user: null, anonymous: true },
          edit_summary: 'removed',
          revert: false,
        },
      ],
      reincarnated_as: null,
      coordination: { score: g?.coordination_score ?? 0, evidence: [] },
      links: { born: '#', died: '#' },
    }
  }
  return fromApi(`/api/ghosts/${pageId}/${hash}`)
}

export async function searchGhosts(q: string): Promise<SearchHit[]> {
  if (USE_MOCK) {
    const needle = q.trim().toLowerCase()
    if (!needle) return searchHits as SearchHit[]
    return (searchHits as SearchHit[]).filter(
      (h) =>
        h.text_en?.toLowerCase().includes(needle) ||
        h.text_fi.toLowerCase().includes(needle) ||
        (h.title_en ?? '').toLowerCase().includes(needle),
    )
  }
  return fromApi(`/api/search?q=${encodeURIComponent(q)}`)
}

/** The article's life story, or null when Gemma hasn't written one for it yet. */
export async function getBiography(pageId: number): Promise<Biography | null> {
  if (USE_MOCK) return pageId === 1150 ? (biography1150 as Biography) : null
  try {
    return await fromApi<Biography>(`/api/articles/${pageId}/biography`)
  } catch {
    return null
  }
}

export function formatYear(iso: string): string {
  return new Date(iso).getUTCFullYear().toString()
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-GB', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  })
}

/** Same story, every language: live comparison of one article across Wikipedia editions. */
export async function compareLanguages(title: string, lang = 'fi', refresh = false): Promise<LangCompare> {
  const q = new URLSearchParams({ title, lang })
  if (refresh) q.set('refresh', '1')
  return fromApi(`/api/languages?${q}`)
}

/** Second step: Gemma's English meanings for the titles, first sentences and rename reasons. */
export async function languageMeanings(title: string, lang = 'fi'): Promise<LangCompare> {
  return fromApi(`/api/languages/meanings?${new URLSearchParams({ title, lang })}`)
}

/** The latest comparison stored in MariaDB (null if none in the last 24 h). */
export async function savedComparison(title: string, lang = 'fi'): Promise<LangCompare | null> {
  const res = await fetch(`/api/languages/saved?${new URLSearchParams({ title, lang })}`)
  return res.ok ? ((await res.json()) as LangCompare) : null
}

/** Store a comparison computed in the browser (a new system-versioned row in MariaDB). */
export async function saveComparison(title: string, lang: string, report: LangCompare): Promise<void> {
  const res = await fetch('/api/languages/save', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, lang, report }),
  })
  if (!res.ok) throw new Error(`save failed: ${res.status}`)
}

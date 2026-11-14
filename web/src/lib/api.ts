import type {
  ArticlePayload,
  FeaturedArticle,
  GhostCertificate,
  SearchHit,
  Stats,
  TimelinePayload,
} from './types'

import articlesFeatured from '../../../mock/articles_featured.json'
import article1150 from '../../../mock/article_1150.json'
import timeline1150 from '../../../mock/timeline_1150.json'
import ghostCd34 from '../../../mock/ghost_cd34.json'
import searchHits from '../../../mock/search.json'
import stats from '../../../mock/stats.json'
import biography1150 from '../../../mock/biography_1150.json'

const USE_MOCK = true

async function fromApi<T>(path: string): Promise<T> {
  const res = await fetch(path)
  if (!res.ok) throw new Error(`API ${path} failed: ${res.status}`)
  return res.json() as Promise<T>
}

export async function getFeaturedArticles(): Promise<FeaturedArticle[]> {
  if (USE_MOCK) return articlesFeatured as FeaturedArticle[]
  return fromApi('/api/articles?featured=1')
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
        h.title_en.toLowerCase().includes(needle),
    )
  }
  return fromApi(`/api/search?q=${encodeURIComponent(q)}`)
}

export async function getBiography(pageId: number) {
  if (USE_MOCK) return biography1150
  return fromApi(`/api/articles/${pageId}/biography`)
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

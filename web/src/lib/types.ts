export type FeaturedArticle = {
  page_id: number
  title_fi: string
  title_en: string
  ghost_count: number
  versions: number
  first_edit: string
  last_edit: string
}

export type LivingSentence = {
  hash: string
  text_fi: string
  text_en: string | null
  section: string
  pos: number
  born: string
}

export type GhostSummary = {
  hash: string
  text_fi: string
  text_en: string | null
  section: string
  after_hash: string
  born: string
  died: string
  kind: 'erased' | 'rewritten' | 'typo' | 'reverted'
  lives: number
  rarity: 'common' | 'rare'
  coordination_score: number
  event_tag?: string
}

export type ArticlePayload = {
  page_id: number
  title_fi: string
  title_en: string
  as_of: string
  ghost_count: number
  sentences: LivingSentence[]
  ghosts: GhostSummary[]
}

export type TimelineFrame = {
  ts: string
  rev_id: number
  hashes: string[]
  edits: number
  deaths: number
}

export type TimelineSentence = {
  text_fi: string
  text_en: string | null
  born: string
  died: string | null
  contested: boolean
}

export type TimelinePayload = {
  page_id: number
  frames: TimelineFrame[]
  sentences: Record<string, TimelineSentence>
}

export type GhostCertificate = {
  hash: string
  page_id: number
  text_fi: string
  text_en: string | null
  kind: string
  rarity: string
  event_tag?: string
  lives: Array<{
    born: string
    born_rev: number
    died: string
    died_rev: number
    removed_by: { user: string | null; anonymous: boolean }
    edit_summary: string
    revert: boolean
  }>
  reincarnated_as: {
    hash: string
    text_fi: string
    text_en: string | null
    similarity: number
  } | null
  coordination: {
    score: number
    evidence: Array<{ label: string; value: string; explain: string }>
  }
  links: { born: string; died: string }
}

export type SearchHit = {
  page_id: number
  title_en: string
  hash: string
  text_fi: string
  text_en: string | null
  died: string
  similarity: number
}

export type Stats = {
  articles: number
  versions: number
  sentences: number
  ghosts: number
  half_life_years: number
  pct_deleted: number
  timings_ms: { as_of: number; ghosts: number; search: number }
}

export type LangMode = 'both' | 'fi' | 'en'

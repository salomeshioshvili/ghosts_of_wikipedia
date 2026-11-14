export type FeaturedArticle = {
  page_id: number
  title_fi: string
  title_en: string | null
  loaded?: boolean
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
  after_hash: string | null
  born: string
  died: string
  kind: 'erased' | 'rewritten' | 'typo' | 'reverted' | 'moved'
  moved_to?: { page_id: number; title_fi: string } | null
  lives: number
  rarity: 'common' | 'rare'
  coordination_score: number | null
  event_tag?: string | null
}

export type ArticlePayload = {
  page_id: number
  title_fi: string
  title_en: string | null
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
  event_tag?: string | null
  lives: Array<{
    born: string
    born_rev: number
    died: string | null
    died_rev: number | null
    removed_by: { user: string | null; anonymous: boolean }
    edit_summary: string | null
    revert: boolean
    moved_to?: { page_id: number; title_fi: string } | null
  }>
  reincarnated_as: {
    hash: string
    text_fi: string
    text_en: string | null
    similarity: number
  } | null
  coordination: {
    score: number | null
    evidence: Array<{ label: string; value: string; explain: string }>
  }
  links: { born: string; died: string | null }
}

export type SearchHit = {
  page_id: number
  title_fi?: string
  title_en: string | null
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
  half_life_years: number | null
  pct_deleted: number
  timings_ms: Record<string, number | null>
}

export type LangMode = 'both' | 'fi' | 'en'

export type Biography = {
  page_id: number
  chapters: Array<{ ts: string; caption_en: string; caption_fi?: string | null; rev_ids: number[] }>
  audio_url?: string | null
}

export type LangSignal = { kind: string; label: string; explain: string }

export type LangRename = {
  ts: string
  from: string
  to: string
  reason: string | null
  reason_en?: string | null
  undone_after_hours?: number
  reverses?: boolean
}

export type LangEdition = {
  lang: string
  language: string
  autonym?: string | null
  title: string
  title_en?: string | null
  url?: string
  first_sentence?: string | null
  first_sentence_en?: string | null
  names: string[]
  renames: LangRename[]
  locks: number
  recent: { edits: number; reverted: number; since: string | null }
  signals?: LangSignal[]
  error?: string
}

export type LangCompare = {
  query: { lang: string; title: string }
  languages_available: number
  editions: LangEdition[]
  summary: { renames: number; renames_undone: number; locks: number; names: number; editions_with_signals: number }
  fetched_at: string
  seconds: number
  translated_by: string | null
  cached: boolean
}

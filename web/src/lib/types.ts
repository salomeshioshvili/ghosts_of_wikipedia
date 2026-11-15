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
  why?: string
  talk?: { url: string; sections: number; naming: string[] } | null
  lead?: string | null
  fought_sections?: Array<{ section: string; reverted: number }>
  first_edit?: string | null
  size?: { bytes: number; sections: string[] }
  editors?: { distinct: number; unregistered_pct: number } | null
  views?: { start: string; monthly: number[] } | null
}

export type LangCompare = {
  query: { lang: string; title: string }
  others?: Array<{ lang: string; title: string; language: string }>
  languages_available: number
  editions: LangEdition[]
  summary: { renames: number; renames_undone: number; locks: number; names: number; editions_with_signals: number }
  fetched_at: string
  seconds: number
  translated_by: string | null
  cached: boolean
}

export type WebEchoResult = {
  url: string
  domain: string
  title: string
  description: string
  relevance: string
  wikipedia_copy: boolean
}

export type WebEcho = {
  page_id: number
  hash: string
  queries: { exact_phrase: string; related: string | null }
  exact: WebEchoResult[]
  related: WebEchoResult[]
  status: 'still_said' | 'only_copies' | 'only_related' | 'gone'
  verdict: string
  source: string
  fetched_at: string
  cached: boolean
}

export type LiveNow = {
  page_id: number
  title: string
  url: string
  snapshot: string | null
  fetched_at: string
  counts: { in_snapshot: number; live_now: number; unchanged: number; rewritten: number; gone: number; new: number }
  match_quality: number
  gone: Array<{ hash: string; text_fi: string; text_en: string | null; section: string | null }>
  rewritten: Array<{
    hash: string
    before: string
    before_en: string | null
    after: string
    similarity: number
    section: string | null
  }>
  new: Array<{ text_fi: string; section: string }>
  source: string
  cached: boolean
}

export type LangInsight = {
  headline: string
  patterns: string[]
  possible_explanations: string[]
  caveats: string[]
  questions: string[]
  model: string
  created_at: string
  cached: boolean
}

export type WordStat = {
  stem: string
  word: string
  word_en?: string | null
  in_deleted: number
  in_surviving: number
  z: number
  first_year: number | null
  last_year: number | null
  example_deleted?: string | null
}

export type WordShift = {
  page_id: number
  title: string | null
  stopped_saying: WordStat[]
  kept_saying: WordStat[]
  years: number[]
  sentences_alive: number[]
  series: Record<string, number[]>
  deleted_sentences: number
  surviving_sentences: number
  method: string
  translated_by: string | null
  computed_at: string
  cached?: boolean
}

export type LangPerspectives = {
  summary: string
  points: Array<{ point: string; by_language: Record<string, string | null> }>
  fought_over: Record<string, string[]>
  own_sections?: Record<string, string[]>
  caveats: string[]
  model: string
  created_at: string
  cached: boolean
}

export interface MinistrySummary {
  id: number
  name: string
  slug: string
}

export interface MinistryListItem extends MinistrySummary {
  article_count: number
}

export interface TopicListItem {
  name: string
  slug: string
  article_count: number
}

export interface PrelimsQuestion {
  question: string
  options: string[]
  correct_option_index: number
  explanation: string
}

export interface MainsQuestion {
  question: string
  gs_paper: string
}

export type Importance = 'IMPORTANT' | 'WORTH_A_LOOK'

export type StudyClassification = 'PRELIMS' | 'MAINS' | 'BOTH' | 'LOW_PRIORITY'

export interface PrelimsPoint {
  point: string
  importance: Importance
  syllabus: string
  why_important: string
}

export interface MainsPoint {
  point: string
  importance: Importance
  gs_paper: string
  theme: string
  analytical_use: string
}

export interface BothPoint {
  concept: string
  prelims_angle: string
  mains_angle: string
  importance: Importance
}

export interface LowPriorityPoint {
  point: string
  reason: string
}

export interface StudyNotes {
  classification: StudyClassification
  reason: string
  prelims: PrelimsPoint[]
  mains: MainsPoint[]
  both: BothPoint[]
  low_priority: LowPriorityPoint[]
}

export interface Enrichment {
  summary: string
  context: string
  upsc_relevant: boolean
  upsc_relevance: number | null
  syllabus_topics: string[]
  prelims_questions: PrelimsQuestion[]
  mains_questions: MainsQuestion[]
  /** Null below the study gate, and for anything enriched before the pass existed. */
  study_notes: StudyNotes | null
  model: string
}

export interface PastQuestion {
  year: number
  paper: string
  question: string
  syllabus_area: string | null
}

export interface RelatedArticle {
  id: number
  title: string
  ministry: MinistrySummary
  release_datetime: string | null
  relationship: string
}

export interface ArticleListItem {
  id: number
  prid: number
  title: string
  ministry: MinistrySummary
  release_datetime: string | null
  source_url: string
  summary: string | null
  upsc_relevant: boolean | null
  upsc_relevance: number | null
  /** Carried on the list item so the static build can filter by topic
   *  in the browser, with no server to ask. */
  syllabus_topics: string[]
  study_classification: StudyClassification | null
}

export interface PaginatedArticles {
  items: ArticleListItem[]
  total: number
  limit: number
  offset: number
}

export interface ArticleDetail {
  id: number
  prid: number
  title: string
  subtitle: string | null
  body_text: string
  ministry: MinistrySummary
  pib_office: string | null
  release_datetime: string | null
  source_url: string
  scraped_at: string
  enrichment: Enrichment | null
  related_articles: RelatedArticle[]
  // Empty until a real corpus is imported; nothing here is ever generated.
  past_questions?: PastQuestion[]
}

export interface ArticleListParams {
  ministry?: string
  topic?: string
  upsc_relevant?: boolean
  search?: string
  date_from?: string
  date_to?: string
  sort?: 'newest' | 'relevance'
  limit?: number
  offset?: number
}

export interface AuthProvider {
  name: string
  label: string
  configured: boolean
}

export interface CurrentUser {
  id: number
  display_name: string | null
  email: string | null
  avatar_url: string | null
  providers: string[]
}

export interface MinistryRef {
  id: number
  name: string
  slug: string
}

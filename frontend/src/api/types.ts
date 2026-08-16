export interface MinistrySummary {
  id: number
  name: string
  slug: string
}

export interface MinistryListItem extends MinistrySummary {
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

export interface Enrichment {
  summary: string
  context: string
  upsc_relevant: boolean
  upsc_relevance: number | null
  syllabus_topics: string[]
  prelims_questions: PrelimsQuestion[]
  mains_questions: MainsQuestion[]
  model: string
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
}

export interface ArticleListParams {
  ministry?: string
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

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MinistrySummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str


class MinistryListItem(MinistrySummary):
    article_count: int


class PrelimsQuestionOut(BaseModel):
    question: str
    options: list[str]
    correct_option_index: int
    explanation: str


class MainsQuestionOut(BaseModel):
    question: str
    gs_paper: str


class EnrichmentOut(BaseModel):
    summary: str
    context: str
    upsc_relevant: bool
    upsc_relevance: int | None
    syllabus_topics: list[str]
    prelims_questions: list[PrelimsQuestionOut]
    mains_questions: list[MainsQuestionOut]
    model: str


class RelatedArticleOut(BaseModel):
    id: int
    title: str
    ministry: MinistrySummary
    release_datetime: datetime | None
    relationship: str


class ArticleListItem(BaseModel):
    id: int
    prid: int
    title: str
    ministry: MinistrySummary
    release_datetime: datetime | None
    source_url: str
    summary: str | None
    upsc_relevant: bool | None
    upsc_relevance: int | None


class PaginatedArticles(BaseModel):
    items: list[ArticleListItem]
    total: int
    limit: int
    offset: int


class StageResultOut(BaseModel):
    name: str
    status: str
    summary: str | None
    error: str | None


class PipelineRunOut(BaseModel):
    id: int
    trigger: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    stages: list[StageResultOut]
    error: str | None


class PaginatedPipelineRuns(BaseModel):
    items: list[PipelineRunOut]
    total: int
    limit: int
    offset: int


class ArticleDetail(BaseModel):
    id: int
    prid: int
    title: str
    subtitle: str | None
    body_text: str
    ministry: MinistrySummary
    pib_office: str | None
    release_datetime: datetime | None
    source_url: str
    scraped_at: datetime
    enrichment: EnrichmentOut | None
    related_articles: list[RelatedArticleOut]


class AuthProviderInfo(BaseModel):
    name: str
    label: str
    configured: bool


class SignInRequest(BaseModel):
    id_token: str


class CurrentUser(BaseModel):
    id: int
    display_name: str | None
    email: str | None
    avatar_url: str | None
    providers: list[str]


class MinistryRefOut(BaseModel):
    id: int
    name: str
    slug: str


class SubscriptionsUpdate(BaseModel):
    ministry_ids: list[int]

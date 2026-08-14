from pib_agent.api.schemas import (
    ArticleDetail,
    ArticleListItem,
    EnrichmentOut,
    MainsQuestionOut,
    MinistrySummary,
    PipelineRunOut,
    PrelimsQuestionOut,
    RelatedArticleOut,
    StageResultOut,
)
from pib_agent.db.models import Article, ArticleLink, Enrichment, Ministry, PipelineRun


def to_ministry_summary(ministry: Ministry) -> MinistrySummary:
    return MinistrySummary.model_validate(ministry)


def to_enrichment_out(enrichment: Enrichment) -> EnrichmentOut:
    return EnrichmentOut(
        summary=enrichment.summary,
        context=enrichment.context,
        upsc_relevant=enrichment.upsc_relevant,
        syllabus_topics=enrichment.syllabus_topics,
        prelims_questions=[PrelimsQuestionOut(**q) for q in enrichment.prelims_questions],
        mains_questions=[MainsQuestionOut(**q) for q in enrichment.mains_questions],
        model=enrichment.model,
    )


def to_article_list_item(article: Article) -> ArticleListItem:
    enrichment = article.enrichment
    return ArticleListItem(
        id=article.id,
        prid=article.prid,
        title=article.title,
        ministry=to_ministry_summary(article.ministry),
        release_datetime=article.release_datetime,
        source_url=article.source_url,
        summary=enrichment.summary if enrichment else None,
        upsc_relevant=enrichment.upsc_relevant if enrichment else None,
    )


def to_pipeline_run_out(run: PipelineRun) -> PipelineRunOut:
    return PipelineRunOut(
        id=run.id,
        trigger=run.trigger,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        stages=[StageResultOut(**stage) for stage in run.stages],
        error=run.error,
    )


def to_article_detail(article: Article, links: list[ArticleLink]) -> ArticleDetail:
    return ArticleDetail(
        id=article.id,
        prid=article.prid,
        title=article.title,
        subtitle=article.subtitle,
        body_text=article.body_text,
        ministry=to_ministry_summary(article.ministry),
        pib_office=article.pib_office,
        release_datetime=article.release_datetime,
        source_url=article.source_url,
        scraped_at=article.scraped_at,
        enrichment=to_enrichment_out(article.enrichment) if article.enrichment else None,
        related_articles=[
            RelatedArticleOut(
                id=link.related_article.id,
                title=link.related_article.title,
                ministry=to_ministry_summary(link.related_article.ministry),
                release_datetime=link.related_article.release_datetime,
                relationship=link.relationship_note,
            )
            for link in links
        ],
    )

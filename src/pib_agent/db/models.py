from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pib_agent.db.base import Base


class Ministry(Base):
    __tablename__ = "ministries"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    articles: Mapped[list["Article"]] = relationship(
        back_populates="ministry", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"Ministry(id={self.id!r}, name={self.name!r})"


class Article(Base):
    __tablename__ = "articles"
    __table_args__ = (
        UniqueConstraint("prid", name="uq_articles_prid"),
        Index("ix_articles_ministry_release", "ministry_id", "release_datetime"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    prid: Mapped[int] = mapped_column(nullable=False, index=True)
    ministry_id: Mapped[int] = mapped_column(ForeignKey("ministries.id"), nullable=False)

    title: Mapped[str] = mapped_column(Text, nullable=False)
    subtitle: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    body_html: Mapped[str] = mapped_column(Text, nullable=False)

    pib_office: Mapped[str | None] = mapped_column(String(100), nullable=True)
    release_datetime: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True, index=True
    )
    source_url: Mapped[str] = mapped_column(String(512), nullable=False)

    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    ministry: Mapped["Ministry"] = relationship(back_populates="articles")
    enrichment: Mapped["Enrichment | None"] = relationship(
        back_populates="article", cascade="all, delete-orphan", uselist=False
    )
    embedding: Mapped["Embedding | None"] = relationship(
        back_populates="article", cascade="all, delete-orphan", uselist=False
    )

    def __repr__(self) -> str:
        return f"Article(id={self.id!r}, prid={self.prid!r}, title={self.title[:40]!r})"


class Enrichment(Base):
    __tablename__ = "enrichments"

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id"), nullable=False, unique=True
    )

    summary: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[str] = mapped_column(Text, nullable=False)
    # Claude's 1-5 rating of how much study time this release deserves.
    # Nullable because rows enriched before the score existed only ever had
    # the boolean below; those keep whatever `upsc_relevant` they were given.
    upsc_relevance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Derived from upsc_relevance via settings.upsc_relevance_threshold at
    # enrichment time, so the API and notify filters stay a plain boolean read.
    upsc_relevant: Mapped[bool] = mapped_column(Boolean, nullable=False)
    syllabus_topics: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    prelims_questions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    mains_questions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )

    # Point-level UPSC extraction, added by the separate `study` pass. Nullable
    # because that pass only runs for articles clearing
    # settings.study_notes_min_relevance — most releases never get one, and
    # every row predating the feature has none.
    study_notes: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # Denormalised out of study_notes so the API can filter on it without
    # unpacking JSON in SQL.
    study_classification: Mapped[str | None] = mapped_column(String(16), nullable=True)

    model: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Set once a Telegram notification dispatch has been attempted for this
    # article, whether or not any subscribers existed — mirrors
    # Embedding.linked_at so a "nobody to notify" pass is never repeated.
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    article: Mapped["Article"] = relationship(back_populates="enrichment")

    def __repr__(self) -> str:
        return f"Enrichment(id={self.id!r}, article_id={self.article_id!r})"


class Embedding(Base):
    __tablename__ = "embeddings"

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id"), nullable=False, unique=True
    )

    vector: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    dim: Mapped[int] = mapped_column(Integer, nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Set once the similarity-linking pass has run for this article, whether
    # or not it produced any links — lets the pipeline skip already-checked
    # articles without a separate marker table.
    linked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    linked_model: Mapped[str | None] = mapped_column(String(64), nullable=True)

    article: Mapped["Article"] = relationship(back_populates="embedding")

    def __repr__(self) -> str:
        return f"Embedding(id={self.id!r}, article_id={self.article_id!r}, dim={self.dim!r})"


class ArticleLink(Base):
    __tablename__ = "article_links"
    __table_args__ = (
        UniqueConstraint("article_id", "related_article_id", name="uq_article_links_pair"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), nullable=False, index=True)
    related_article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), nullable=False)

    relationship_note: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    article: Mapped["Article"] = relationship(foreign_keys=[article_id])
    related_article: Mapped["Article"] = relationship(foreign_keys=[related_article_id])

    def __repr__(self) -> str:
        return (
            f"ArticleLink(article_id={self.article_id!r}, "
            f"related_article_id={self.related_article_id!r})"
        )


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    # "scheduled" | "manual" | "cli" | "startup"
    trigger: Mapped[str] = mapped_column(String(20), nullable=False)
    # "running" | "success" | "partial_failure" | "failed"
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # One entry per stage: {"name", "status", "summary", "error"}.
    stages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    # Set only if the run crashed outside of a single stage's isolation (should be rare).
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"PipelineRun(id={self.id!r}, trigger={self.trigger!r}, status={self.status!r})"


class User(Base):
    """A person, independent of how they signed in.

    Deliberately holds no credentials — every way of proving who you are is an
    AuthIdentity row, so a user can hold several (Telegram *and* Google) and
    still be one account.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Only some providers supply an email (Telegram doesn't), and it's never
    # the identity key — providers' `sub` is. Kept for display and contact.
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    identities: Mapped[list["AuthIdentity"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    subscriptions: Mapped[list["Subscription"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"User(id={self.id!r}, display_name={self.display_name!r})"


class AuthIdentity(Base):
    """One way a User can sign in: (provider, provider's subject) -> user."""

    __tablename__ = "auth_identities"
    __table_args__ = (
        UniqueConstraint("provider", "subject", name="uq_auth_identities_provider_subject"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    # "telegram" | "google"
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    # The provider's stable subject claim. For Telegram this is the Telegram
    # user id — the same number that used to live on Subscription.chat_id,
    # which is what lets notifications keep working across the migration.
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="identities")

    def __repr__(self) -> str:
        return f"AuthIdentity(provider={self.provider!r}, subject={self.subject!r})"


class UserSession(Base):
    """A signed-in browser session.

    Server-side rather than a stateless JWT cookie so sessions can actually be
    revoked — which matters as soon as anything is paid for. Only the hash of
    the token is stored, so a database leak doesn't hand over live sessions.
    """

    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship()

    def __repr__(self) -> str:
        return f"UserSession(id={self.id!r}, user_id={self.user_id!r})"


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        UniqueConstraint("user_id", "ministry_id", name="uq_subscriptions_user_ministry"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    ministry_id: Mapped[int] = mapped_column(ForeignKey("ministries.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    ministry: Mapped["Ministry"] = relationship()
    user: Mapped["User"] = relationship(back_populates="subscriptions")

    def __repr__(self) -> str:
        return f"Subscription(user_id={self.user_id!r}, ministry_id={self.ministry_id!r})"

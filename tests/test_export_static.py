import json
from datetime import datetime

import pytest

from pib_agent.api.mapping import to_article_detail, to_article_list_item
from pib_agent.db.models import (
    Article,
    ArticleLink,
    AuthIdentity,
    Enrichment,
    Ministry,
    Subscription,
    User,
    UserSession,
)
from pib_agent.export_static import export_static


def _make_article(
    prid: int,
    ministry: Ministry,
    title: str = "Title",
    release_datetime: datetime | None = datetime(2026, 8, 9, 12, 0),
) -> Article:
    return Article(
        prid=prid,
        ministry=ministry,
        title=title,
        subtitle=None,
        body_text="Body text.",
        body_html="<p>Body text.</p>",
        pib_office="PIB Delhi",
        release_datetime=release_datetime,
        source_url=f"https://pib.gov.in/PressReleasePage.aspx?PRID={prid}",
    )


def _make_enrichment(article: Article, upsc_relevance: int | None = 4) -> Enrichment:
    return Enrichment(
        article=article,
        summary="Summary.",
        context="Context.",
        upsc_relevant=True,
        upsc_relevance=upsc_relevance,
        syllabus_topics=["GS Paper 3 - Economy"],
        prelims_questions=[],
        mains_questions=[],
        model="claude-sonnet-5",
    )


@pytest.fixture()
def ministry(db_session) -> Ministry:
    m = Ministry(name="Ministry of Finance", slug="ministry-of-finance")
    db_session.add(m)
    db_session.flush()
    return m


def _read(out, *parts):
    path = out.joinpath(*parts)
    return json.loads(path.read_text(encoding="utf-8"))


def test_export_writes_index_detail_ministries_and_meta(tmp_path, db_session, ministry):
    article = _make_article(1, ministry, title="Only Article")
    db_session.add(_make_enrichment(article))
    db_session.flush()

    result = export_static(tmp_path / "data", db_session, days=30)

    out = tmp_path / "data"
    assert result.article_count == 1
    assert _read(out, "index.json")[0]["title"] == "Only Article"
    assert _read(out, "articles", f"{article.id}.json")["title"] == "Only Article"
    assert _read(out, "ministries.json")[0]["slug"] == "ministry-of-finance"
    assert _read(out, "meta.json")["article_count"] == 1


def test_index_entries_match_the_api_payload_exactly(tmp_path, db_session, ministry):
    """The bundle is what the frontend reads instead of calling the API, so a
    drift between the two shapes is a bug the frontend would only hit once
    deployed."""
    article = _make_article(1, ministry)
    db_session.add(_make_enrichment(article))
    db_session.flush()

    export_static(tmp_path / "data", db_session, days=30)

    exported = _read(tmp_path / "data", "index.json")[0]
    expected = json.loads(to_article_list_item(article).model_dump_json())
    assert exported == expected


def test_detail_files_match_the_api_payload_exactly(tmp_path, db_session, ministry):
    first = _make_article(1, ministry, title="First")
    second = _make_article(2, ministry, title="Second")
    db_session.add_all([first, second])
    db_session.flush()
    link = ArticleLink(
        article_id=first.id,
        related_article_id=second.id,
        relationship_note="Follows on from the earlier announcement.",
    )
    db_session.add(link)
    db_session.flush()

    export_static(tmp_path / "data", db_session, days=30)

    exported = _read(tmp_path / "data", "articles", f"{first.id}.json")
    expected = json.loads(to_article_detail(first, [link]).model_dump_json())
    assert exported == expected
    assert len(exported["related_articles"]) == 1


def test_window_excludes_articles_older_than_the_cutoff(tmp_path, db_session, ministry):
    recent = _make_article(
        1, ministry, title="Recent", release_datetime=datetime(2026, 8, 17, 9, 0)
    )
    edge = _make_article(2, ministry, title="Edge", release_datetime=datetime(2026, 8, 15, 9, 0))
    stale = _make_article(3, ministry, title="Stale", release_datetime=datetime(2026, 8, 14, 23, 0))
    db_session.add_all([recent, edge, stale])
    db_session.flush()

    # A 3-day window anchored on the newest release covers the 15th to 17th.
    result = export_static(tmp_path / "data", db_session, days=3)

    titles = {item["title"] for item in _read(tmp_path / "data", "index.json")}
    assert titles == {"Recent", "Edge"}
    assert result.article_count == 2
    assert not (tmp_path / "data" / "articles" / f"{stale.id}.json").exists()


def test_window_anchors_on_the_newest_release_not_today(tmp_path, db_session, ministry):
    """Anchoring on `now` would publish an empty bundle whenever the scraper
    has been down longer than the window — a silent failure that looks like a
    successful export."""
    old = _make_article(1, ministry, release_datetime=datetime(2020, 1, 2, 9, 0))
    db_session.add(old)
    db_session.flush()

    result = export_static(tmp_path / "data", db_session, days=30)

    assert result.article_count == 1
    assert result.latest_date == "2020-01-02"


def test_ministry_counts_are_scoped_to_the_window(tmp_path, db_session):
    inside = Ministry(name="Inside", slug="inside")
    outside = Ministry(name="Outside", slug="outside")
    db_session.add_all([inside, outside])
    db_session.flush()
    db_session.add(_make_article(1, inside, release_datetime=datetime(2026, 8, 17, 9, 0)))
    db_session.add(_make_article(2, outside, release_datetime=datetime(2026, 1, 1, 9, 0)))
    db_session.flush()

    export_static(tmp_path / "data", db_session, days=7)

    ministries = _read(tmp_path / "data", "ministries.json")
    # A ministry with nothing in the window would otherwise advertise releases
    # the bundle cannot serve.
    assert [m["slug"] for m in ministries] == ["inside"]
    assert ministries[0]["article_count"] == 1


def test_meta_reports_the_latest_release_date(tmp_path, db_session, ministry):
    db_session.add(_make_article(1, ministry, release_datetime=datetime(2026, 8, 16, 9, 0)))
    db_session.add(_make_article(2, ministry, release_datetime=datetime(2026, 8, 17, 18, 0)))
    db_session.flush()

    export_static(tmp_path / "data", db_session, days=30)

    # The digest keys its day off this rather than the visitor's clock.
    assert _read(tmp_path / "data", "meta.json")["latest_date"] == "2026-08-17"


def test_rerunning_the_export_drops_articles_that_left_the_window(
    tmp_path, db_session, ministry
):
    old = _make_article(1, ministry, release_datetime=datetime(2026, 8, 10, 9, 0))
    db_session.add(old)
    db_session.flush()
    export_static(tmp_path / "data", db_session, days=30)
    assert (tmp_path / "data" / "articles" / f"{old.id}.json").exists()

    db_session.add(_make_article(2, ministry, release_datetime=datetime(2026, 9, 30, 9, 0)))
    db_session.flush()
    export_static(tmp_path / "data", db_session, days=7)

    # Stale detail files would otherwise be served forever.
    assert not (tmp_path / "data" / "articles" / f"{old.id}.json").exists()


def test_export_rejects_a_nonsense_window(tmp_path, db_session):
    with pytest.raises(ValueError):
        export_static(tmp_path / "data", db_session, days=0)


def test_bundle_never_contains_user_or_session_data(tmp_path, db_session, ministry):
    """The bundle is committed to a public repository.

    The database holds real email addresses, provider subject ids and session
    token hashes; none of it may reach the export. This asserts on the actual
    bytes written rather than on which tables the query touched, so it still
    fails if a future join quietly pulls a user field into a payload.
    """
    user = User(display_name="Real Person", email="real.person@example.com")
    db_session.add(user)
    db_session.flush()
    db_session.add(AuthIdentity(user_id=user.id, provider="google", subject="google-subject-1234"))
    db_session.add(
        UserSession(
            user_id=user.id,
            token_hash="secret-token-hash-abcdef",
            expires_at=datetime(2030, 1, 1, 0, 0),
        )
    )
    db_session.add(Subscription(user_id=user.id, ministry_id=ministry.id))
    article = _make_article(1, ministry)
    db_session.add(_make_enrichment(article))
    db_session.flush()

    out = tmp_path / "data"
    export_static(out, db_session, days=30)

    blob = "\n".join(p.read_text(encoding="utf-8") for p in out.rglob("*.json"))
    # Guards the assertions below from passing vacuously on an empty read.
    assert "Summary." in blob

    for secret in (
        "real.person@example.com",
        "Real Person",
        "google-subject-1234",
        "secret-token-hash-abcdef",
    ):
        assert secret not in blob, f"{secret!r} leaked into the static bundle"

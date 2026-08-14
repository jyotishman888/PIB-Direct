from datetime import datetime

from pib_agent.db.models import Article, ArticleLink, Enrichment, Ministry


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


def _make_enrichment(
    article: Article,
    summary: str = "Summary.",
    upsc_relevant: bool = True,
    prelims_questions: list | None = None,
    mains_questions: list | None = None,
) -> Enrichment:
    return Enrichment(
        article=article,
        summary=summary,
        context="Context.",
        upsc_relevant=upsc_relevant,
        syllabus_topics=["GS Paper 3 - Economy"] if upsc_relevant else [],
        prelims_questions=prelims_questions or [],
        mains_questions=mains_questions or [],
        model="claude-sonnet-5",
    )


def test_list_articles_returns_summary_and_upsc_relevant_from_enrichment(api_client):
    client, session_scope_factory = api_client

    with session_scope_factory() as session:
        ministry = Ministry(name="Ministry of Finance", slug="ministry-of-finance")
        enriched = _make_article(1, ministry, title="Enriched Article")
        session.add(_make_enrichment(enriched, summary="A concise summary."))
        session.add(_make_article(2, ministry, title="Not Yet Enriched"))

    response = client.get("/api/articles")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    by_title = {item["title"]: item for item in body["items"]}
    assert by_title["Enriched Article"]["summary"] == "A concise summary."
    assert by_title["Enriched Article"]["upsc_relevant"] is True
    assert by_title["Not Yet Enriched"]["summary"] is None
    assert by_title["Not Yet Enriched"]["upsc_relevant"] is None


def test_list_articles_orders_newest_first_with_nulls_last(api_client):
    client, session_scope_factory = api_client

    with session_scope_factory() as session:
        ministry = Ministry(name="Ministry of Finance", slug="ministry-of-finance")
        session.add(
            _make_article(1, ministry, title="Oldest", release_datetime=datetime(2026, 8, 1))
        )
        session.add(
            _make_article(2, ministry, title="Newest", release_datetime=datetime(2026, 8, 9))
        )
        session.add(_make_article(3, ministry, title="No Date", release_datetime=None))

    response = client.get("/api/articles")

    titles = [item["title"] for item in response.json()["items"]]
    assert titles == ["Newest", "Oldest", "No Date"]


def test_list_articles_filters_by_ministry_slug(api_client):
    client, session_scope_factory = api_client

    with session_scope_factory() as session:
        finance = Ministry(name="Ministry of Finance", slug="ministry-of-finance")
        defence = Ministry(name="Ministry of Defence", slug="ministry-of-defence")
        session.add(_make_article(1, finance, title="Finance Release"))
        session.add(_make_article(2, defence, title="Defence Release"))

    response = client.get("/api/articles", params={"ministry": "ministry-of-finance"})

    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Finance Release"


def test_list_articles_filters_by_upsc_relevant(api_client):
    client, session_scope_factory = api_client

    with session_scope_factory() as session:
        ministry = Ministry(name="Ministry of Finance", slug="ministry-of-finance")
        relevant = _make_article(1, ministry, title="Relevant")
        session.add(_make_enrichment(relevant, upsc_relevant=True))
        irrelevant = _make_article(2, ministry, title="Irrelevant")
        session.add(_make_enrichment(irrelevant, upsc_relevant=False))
        session.add(_make_article(3, ministry, title="Unenriched"))

    response = client.get("/api/articles", params={"upsc_relevant": "true"})

    titles = {item["title"] for item in response.json()["items"]}
    assert titles == {"Relevant"}


def test_list_articles_search_matches_title_or_summary(api_client):
    client, session_scope_factory = api_client

    with session_scope_factory() as session:
        ministry = Ministry(name="Ministry of Finance", slug="ministry-of-finance")
        title_match = _make_article(1, ministry, title="Renewable Energy Milestone")
        session.add(_make_enrichment(title_match, summary="Unrelated summary text."))
        summary_match = _make_article(2, ministry, title="Unrelated Title")
        session.add(_make_enrichment(summary_match, summary="Discusses renewable energy targets."))
        session.add(_make_article(3, ministry, title="Completely Different"))

    response = client.get("/api/articles", params={"search": "renewable"})

    titles = {item["title"] for item in response.json()["items"]}
    assert titles == {"Renewable Energy Milestone", "Unrelated Title"}


def test_list_articles_filters_by_date_range(api_client):
    client, session_scope_factory = api_client

    with session_scope_factory() as session:
        ministry = Ministry(name="Ministry of Finance", slug="ministry-of-finance")
        session.add(
            _make_article(1, ministry, title="Aug 1", release_datetime=datetime(2026, 8, 1))
        )
        session.add(
            _make_article(2, ministry, title="Aug 5", release_datetime=datetime(2026, 8, 5))
        )
        session.add(
            _make_article(3, ministry, title="Aug 9", release_datetime=datetime(2026, 8, 9))
        )

    response = client.get(
        "/api/articles", params={"date_from": "2026-08-03", "date_to": "2026-08-07"}
    )

    titles = {item["title"] for item in response.json()["items"]}
    assert titles == {"Aug 5"}


def test_list_articles_pagination(api_client):
    client, session_scope_factory = api_client

    with session_scope_factory() as session:
        ministry = Ministry(name="Ministry of Finance", slug="ministry-of-finance")
        for i in range(5):
            session.add(
                _make_article(
                    i, ministry, title=f"Article {i}", release_datetime=datetime(2026, 8, i + 1)
                )
            )

    first_page = client.get("/api/articles", params={"limit": 2, "offset": 0}).json()
    second_page = client.get("/api/articles", params={"limit": 2, "offset": 2}).json()

    assert first_page["total"] == 5
    assert len(first_page["items"]) == 2
    assert len(second_page["items"]) == 2
    first_titles = {item["title"] for item in first_page["items"]}
    second_titles = {item["title"] for item in second_page["items"]}
    assert first_titles.isdisjoint(second_titles)


def test_get_article_detail_includes_enrichment_and_related_articles(api_client):
    client, session_scope_factory = api_client

    with session_scope_factory() as session:
        ministry = Ministry(name="Ministry of New and Renewable Energy", slug="mnre")
        past = _make_article(1, ministry, title="Past Solar Milestone")
        session.add(_make_enrichment(past, summary="Past summary."))
        current = _make_article(2, ministry, title="Current Solar Milestone")
        session.add(
            _make_enrichment(
                current,
                summary="Current summary.",
                prelims_questions=[
                    {
                        "question": "Q?",
                        "options": ["A", "B", "C", "D"],
                        "correct_option_index": 0,
                        "explanation": "Because.",
                    }
                ],
                mains_questions=[{"question": "Discuss.", "gs_paper": "GS Paper 3"}],
            )
        )
        session.flush()
        session.add(
            ArticleLink(
                article_id=current.id,
                related_article_id=past.id,
                relationship_note="Both track solar capacity growth.",
            )
        )
        current_id = current.id

    response = client.get(f"/api/articles/{current_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Current Solar Milestone"
    assert body["ministry"]["slug"] == "mnre"
    assert body["enrichment"]["summary"] == "Current summary."
    assert body["enrichment"]["prelims_questions"][0]["question"] == "Q?"
    assert body["enrichment"]["mains_questions"][0]["gs_paper"] == "GS Paper 3"
    assert len(body["related_articles"]) == 1
    assert body["related_articles"][0]["title"] == "Past Solar Milestone"
    assert body["related_articles"][0]["relationship"] == "Both track solar capacity growth."


def test_get_article_detail_without_enrichment_or_links(api_client):
    client, session_scope_factory = api_client

    with session_scope_factory() as session:
        ministry = Ministry(name="Ministry of Finance", slug="ministry-of-finance")
        article = _make_article(1, ministry, title="Unenriched")
        session.add(article)
        session.flush()
        article_id = article.id

    response = client.get(f"/api/articles/{article_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["enrichment"] is None
    assert body["related_articles"] == []


def test_get_article_detail_404_for_missing_id(api_client):
    client, _ = api_client

    response = client.get("/api/articles/999999")

    assert response.status_code == 404

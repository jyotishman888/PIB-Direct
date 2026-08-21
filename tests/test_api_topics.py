from datetime import datetime

from pib_agent.db.models import Article, Enrichment, Ministry
from pib_agent.syllabus import area_slug

ECONOMY = "GS Paper 3 - Economy"
GOVERNANCE = "GS Paper 2 - Governance"


def _article(prid: int, ministry: Ministry, title: str = "Title") -> Article:
    return Article(
        prid=prid,
        ministry=ministry,
        title=title,
        subtitle=None,
        body_text="Body text.",
        body_html="<p>Body text.</p>",
        pib_office="PIB Delhi",
        release_datetime=datetime(2026, 8, 21, 12, 0),
        source_url=f"https://pib.gov.in/x?PRID={prid}",
    )


def _enrich(article: Article, topics: list[str], summary: str = "Summary.") -> Enrichment:
    return Enrichment(
        article=article,
        summary=summary,
        context="Context.",
        upsc_relevance=4,
        upsc_relevant=True,
        syllabus_topics=topics,
        prelims_questions=[],
        mains_questions=[],
        model="claude-sonnet-5",
    )


def _seed(session_scope_factory):
    with session_scope_factory() as session:
        ministry = Ministry(name="Ministry of Finance", slug="ministry-of-finance")
        other = Ministry(name="Ministry of Defence", slug="ministry-of-defence")
        a = _article(1, ministry, "Budget measures")
        b = _article(2, ministry, "Tax reform")
        c = _article(3, other, "Defence procurement")
        session.add(_enrich(a, [ECONOMY, GOVERNANCE]))
        session.add(_enrich(b, [ECONOMY], summary="Summary about revenue."))
        session.add(_enrich(c, [GOVERNANCE]))


def test_topics_lists_areas_with_counts(api_client):
    client, scope = api_client
    _seed(scope)

    body = client.get("/api/topics").json()

    by_name = {t["name"]: t for t in body}
    assert by_name[ECONOMY]["article_count"] == 2
    assert by_name[GOVERNANCE]["article_count"] == 2
    assert by_name[ECONOMY]["slug"] == area_slug(ECONOMY)


def test_topics_omits_areas_with_no_articles(api_client):
    client, scope = api_client
    _seed(scope)

    names = {t["name"] for t in client.get("/api/topics").json()}

    assert "GS Paper 4 - Ethics and Integrity" not in names


def test_topics_omits_legacy_freetext_tags(api_client):
    """Listing unmapped legacy wordings would rebuild the sprawl the closed
    vocabulary exists to prevent."""
    client, scope = api_client
    with scope() as session:
        ministry = Ministry(name="Ministry of Culture", slug="ministry-of-culture")
        article = _article(9, ministry)
        session.add(_enrich(article, ["GS Paper 2 - Something Nobody Standardised"]))

    assert client.get("/api/topics").json() == []


def test_filter_by_topic_slug(api_client):
    client, scope = api_client
    _seed(scope)

    body = client.get(f"/api/articles?topic={area_slug(ECONOMY)}").json()

    assert body["total"] == 2
    assert {i["title"] for i in body["items"]} == {"Budget measures", "Tax reform"}


def test_unknown_topic_slug_returns_empty_not_an_error(api_client):
    """A stale bookmark should land on an empty list, not an error page."""
    client, scope = api_client
    _seed(scope)

    response = client.get("/api/articles?topic=gs-paper-9-nonsense")

    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_topic_combines_with_ministry(api_client):
    client, scope = api_client
    _seed(scope)

    body = client.get(
        f"/api/articles?topic={area_slug(GOVERNANCE)}&ministry=ministry-of-defence"
    ).json()

    assert [i["title"] for i in body["items"]] == ["Defence procurement"]


def test_topic_combines_with_search(api_client):
    client, scope = api_client
    _seed(scope)

    body = client.get(f"/api/articles?topic={area_slug(ECONOMY)}&search=revenue").json()

    assert [i["title"] for i in body["items"]] == ["Tax reform"]


def test_list_items_expose_their_topics(api_client):
    """The static build filters by topic in the browser, so the list payload
    has to carry them."""
    client, scope = api_client
    _seed(scope)

    body = client.get("/api/articles?ministry=ministry-of-defence").json()

    assert body["items"][0]["syllabus_topics"] == [GOVERNANCE]

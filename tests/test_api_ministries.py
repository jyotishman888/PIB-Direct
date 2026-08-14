from datetime import datetime

from pib_agent.db.models import Article, Ministry


def _make_article(prid: int, ministry: Ministry, title: str = "Title") -> Article:
    return Article(
        prid=prid,
        ministry=ministry,
        title=title,
        subtitle=None,
        body_text="Body.",
        body_html="<p>Body.</p>",
        pib_office="PIB Delhi",
        release_datetime=datetime(2026, 8, 9, 12, 0),
        source_url=f"https://pib.gov.in/PressReleasePage.aspx?PRID={prid}",
    )


def test_list_ministries_returns_alphabetical_order_with_counts(api_client):
    client, session_scope_factory = api_client

    with session_scope_factory() as session:
        finance = Ministry(name="Ministry of Finance", slug="ministry-of-finance")
        defence = Ministry(name="Ministry of Defence", slug="ministry-of-defence")
        empty = Ministry(name="Ministry of Zero Articles", slug="ministry-of-zero-articles")
        session.add_all(
            [
                _make_article(1, finance),
                _make_article(2, finance),
                _make_article(3, defence),
                empty,
            ]
        )

    response = client.get("/api/ministries")

    assert response.status_code == 200
    body = response.json()
    names = [m["name"] for m in body]
    assert names == sorted(names)  # alphabetical, per the endpoint's ORDER BY

    by_slug = {m["slug"]: m for m in body}
    assert by_slug["ministry-of-finance"]["article_count"] == 2
    assert by_slug["ministry-of-defence"]["article_count"] == 1
    assert by_slug["ministry-of-zero-articles"]["article_count"] == 0


def test_list_ministries_empty_db_returns_empty_list(api_client):
    client, _ = api_client

    response = client.get("/api/ministries")

    assert response.status_code == 200
    assert response.json() == []

from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from pib_agent.db.models import Article, Ministry


def _make_article(ministry: Ministry, prid: int = 2296855) -> Article:
    return Article(
        prid=prid,
        ministry=ministry,
        title="CCI holds meeting of heads of BRICS competition authorities",
        subtitle="Joint statement adopted on fair competition in renewable energy markets",
        body_text="The Competition Commission of India held a meeting...",
        body_html="<p>The Competition Commission of India held a meeting...</p>",
        pib_office="PIB Delhi",
        release_datetime=datetime(2026, 8, 9, 15, 21),
        source_url="https://pib.gov.in/PressReleasePage.aspx?PRID=2296855",
    )


def test_create_ministry_and_article(db_session):
    ministry = Ministry(name="Ministry of Finance", slug="ministry-of-finance")
    article = _make_article(ministry)

    db_session.add(article)
    db_session.commit()

    stored = db_session.query(Article).one()
    assert stored.prid == 2296855
    assert stored.ministry.name == "Ministry of Finance"
    assert stored.ministry.slug == "ministry-of-finance"


def test_ministry_articles_relationship(db_session):
    ministry = Ministry(name="Ministry of Defence", slug="ministry-of-defence")
    article1 = _make_article(ministry, prid=1111)
    article2 = _make_article(ministry, prid=2222)

    db_session.add_all([article1, article2])
    db_session.commit()

    stored_ministry = db_session.query(Ministry).one()
    assert {a.prid for a in stored_ministry.articles} == {1111, 2222}


def test_prid_must_be_unique(db_session):
    ministry = Ministry(name="Ministry of Home Affairs", slug="ministry-of-home-affairs")
    db_session.add_all([_make_article(ministry, prid=42), _make_article(ministry, prid=42)])

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_ministry_name_and_slug_must_be_unique(db_session):
    db_session.add_all(
        [
            Ministry(name="Ministry of Home Affairs", slug="ministry-of-home-affairs"),
            Ministry(name="Ministry of Home Affairs", slug="mha-duplicate-slug"),
        ]
    )

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_deleting_ministry_cascades_to_articles(db_session):
    ministry = Ministry(name="Ministry of Civil Aviation", slug="ministry-of-civil-aviation")
    db_session.add(_make_article(ministry))
    db_session.commit()

    db_session.delete(ministry)
    db_session.commit()

    assert db_session.query(Article).count() == 0

"""Endpoint-level auth tests.

Token verification itself is covered in test_auth_verify.py against real
signatures; here it's stubbed so these tests are about routing, cookies and
authorization rather than crypto.
"""

import pytest

from pib_agent.api.routers import auth as auth_router
from pib_agent.auth.providers import ProviderProfile
from pib_agent.auth.service import ProviderNotConfiguredError
from pib_agent.auth.verify import TokenVerificationError
from pib_agent.db.models import Ministry

COOKIE = "pib_session"


@pytest.fixture()
def stub_verification(monkeypatch):
    """Map a fake id_token straight to a profile, bypassing the crypto."""

    def _verify(provider, id_token):
        if id_token == "bad":
            raise TokenVerificationError("Could not verify that sign-in.")
        if id_token == "unconfigured":
            raise ProviderNotConfiguredError("Google sign-in isn't configured on this server.")
        return ProviderProfile(
            subject=f"{provider.name}-{id_token}",
            display_name="Asha Rao",
            email=f"{id_token}@example.com",
            avatar_url=None,
        )

    monkeypatch.setattr(auth_router, "verify_provider_token", _verify)


def _sign_in(client, provider="google", token="tok-1"):
    return client.post(f"/api/auth/{provider}", json={"id_token": token})


def test_anonymous_session_is_200_with_null(api_client):
    client, _ = api_client

    response = client.get("/api/auth/session")

    assert response.status_code == 200
    assert response.json() is None


def test_anonymous_me_is_401(api_client):
    client, _ = api_client

    assert client.get("/api/auth/me").status_code == 401


def test_sign_in_sets_a_session_cookie_and_returns_the_user(api_client, stub_verification):
    client, _ = api_client

    response = _sign_in(client)

    assert response.status_code == 200
    body = response.json()
    assert body["display_name"] == "Asha Rao"
    assert body["providers"] == ["google"]
    assert COOKIE in response.cookies or COOKIE in client.cookies


def test_session_cookie_is_httponly(api_client, stub_verification):
    """JS must not be able to read it, or XSS becomes session theft."""
    client, _ = api_client

    response = _sign_in(client)

    set_cookie = response.headers.get("set-cookie", "")
    assert "httponly" in set_cookie.lower()
    assert "samesite=lax" in set_cookie.lower()


def test_signed_in_requests_resolve_the_user(api_client, stub_verification):
    client, _ = api_client
    _sign_in(client)

    me = client.get("/api/auth/me")

    assert me.status_code == 200
    assert me.json()["providers"] == ["google"]


def test_logout_clears_the_session(api_client, stub_verification):
    client, _ = api_client
    _sign_in(client)

    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_unverifiable_token_is_401(api_client, stub_verification):
    client, _ = api_client

    response = _sign_in(client, token="bad")

    assert response.status_code == 401


def test_unconfigured_provider_is_503(api_client, stub_verification):
    client, _ = api_client

    response = _sign_in(client, token="unconfigured")

    assert response.status_code == 503


def test_unknown_provider_is_404(api_client, stub_verification):
    client, _ = api_client

    response = _sign_in(client, provider="facebook")

    assert response.status_code == 404


def test_providers_endpoint_reports_configuration(api_client):
    client, _ = api_client

    body = client.get("/api/auth/providers").json()

    assert {p["name"] for p in body} == {"telegram", "google"}
    assert all("configured" in p for p in body)


def test_linking_a_second_provider(api_client, stub_verification):
    client, _ = api_client
    _sign_in(client, provider="google", token="tok-1")

    response = client.post("/api/auth/telegram/link", json={"id_token": "tok-2"})

    assert response.status_code == 200
    assert set(response.json()["providers"]) == {"google", "telegram"}


def test_linking_requires_being_signed_in(api_client, stub_verification):
    client, _ = api_client

    assert client.post("/api/auth/telegram/link", json={"id_token": "tok-2"}).status_code == 401


def test_linking_a_claimed_identity_is_409(api_client, stub_verification):
    client, _ = api_client
    # First account claims the telegram identity...
    _sign_in(client, provider="telegram", token="shared")
    client.post("/api/auth/logout")
    # ...then a different account tries to link the same one.
    _sign_in(client, provider="google", token="tok-2")

    response = client.post("/api/auth/telegram/link", json={"id_token": "shared"})

    assert response.status_code == 409


# --- subscriptions ---------------------------------------------------------


def test_subscriptions_require_sign_in(api_client):
    client, _ = api_client

    assert client.get("/api/auth/subscriptions").status_code == 401
    assert client.put("/api/auth/subscriptions", json={"ministry_ids": []}).status_code == 401


def test_put_and_get_subscriptions(api_client, stub_verification):
    client, scope = api_client
    with scope() as s:
        finance = Ministry(name="Ministry of Finance", slug="ministry-of-finance")
        defence = Ministry(name="Ministry of Defence", slug="ministry-of-defence")
        s.add_all([finance, defence])
        s.flush()
        ids = [finance.id, defence.id]

    _sign_in(client)
    put = client.put("/api/auth/subscriptions", json={"ministry_ids": ids})

    assert put.status_code == 200
    assert {m["slug"] for m in put.json()} == {"ministry-of-finance", "ministry-of-defence"}
    assert {m["slug"] for m in client.get("/api/auth/subscriptions").json()} == {
        "ministry-of-finance",
        "ministry-of-defence",
    }


def test_put_subscriptions_replaces_rather_than_appends(api_client, stub_verification):
    client, scope = api_client
    with scope() as s:
        finance = Ministry(name="Ministry of Finance", slug="ministry-of-finance")
        defence = Ministry(name="Ministry of Defence", slug="ministry-of-defence")
        s.add_all([finance, defence])
        s.flush()
        finance_id, defence_id = finance.id, defence.id

    _sign_in(client)
    client.put("/api/auth/subscriptions", json={"ministry_ids": [finance_id, defence_id]})
    response = client.put("/api/auth/subscriptions", json={"ministry_ids": [defence_id]})

    assert [m["slug"] for m in response.json()] == ["ministry-of-defence"]


def test_unknown_ministry_ids_are_ignored(api_client, stub_verification):
    """A stale tab shouldn't fail the whole save."""
    client, scope = api_client
    with scope() as s:
        finance = Ministry(name="Ministry of Finance", slug="ministry-of-finance")
        s.add(finance)
        s.flush()
        finance_id = finance.id

    _sign_in(client)
    response = client.put("/api/auth/subscriptions", json={"ministry_ids": [finance_id, 4242]})

    assert response.status_code == 200
    assert [m["slug"] for m in response.json()] == ["ministry-of-finance"]


def test_two_users_have_separate_subscriptions(api_client, stub_verification):
    client, scope = api_client
    with scope() as s:
        finance = Ministry(name="Ministry of Finance", slug="ministry-of-finance")
        s.add(finance)
        s.flush()
        finance_id = finance.id

    _sign_in(client, token="user-a")
    client.put("/api/auth/subscriptions", json={"ministry_ids": [finance_id]})
    client.post("/api/auth/logout")

    _sign_in(client, token="user-b")

    assert client.get("/api/auth/subscriptions").json() == []

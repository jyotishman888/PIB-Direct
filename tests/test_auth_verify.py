"""Verification is the security boundary, so it's tested against real signatures.

Tokens here are signed with a locally-generated RSA key and the JWKS lookup is
stubbed to return its public half — no network, but the actual PyJWT signature
path runs.
"""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from pib_agent.auth import verify as verify_module
from pib_agent.auth.verify import TokenVerificationError, verify_oidc_token

ISSUER = "https://oauth.telegram.org"
JWKS_URL = "https://oauth.telegram.org/.well-known/jwks.json"
AUDIENCE = "client-id-for-this-app"


@pytest.fixture(scope="module")
def keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


@pytest.fixture(autouse=True)
def _stub_jwks(monkeypatch, keypair):
    _, public_key = keypair

    class _Key:
        key = public_key

    class _Client:
        def get_signing_key_from_jwt(self, _token):
            return _Key()

    monkeypatch.setattr(verify_module, "_jwk_client", lambda _url: _Client())


def _make_token(
    keypair,
    *,
    issuer: str = ISSUER,
    audience: str = AUDIENCE,
    subject: str = "12345",
    expires_in: timedelta = timedelta(minutes=5),
    **extra,
):
    private_key, _ = keypair
    now = datetime.now(UTC)
    claims = {
        "iss": issuer,
        "aud": audience,
        "sub": subject,
        "iat": now,
        "exp": now + expires_in,
        **extra,
    }
    return jwt.encode(claims, private_key, algorithm="RS256")


def test_valid_token_returns_claims(keypair):
    token = _make_token(keypair, name="Asha")

    claims = verify_oidc_token(token, issuer=ISSUER, jwks_url=JWKS_URL, audience=AUDIENCE)

    assert claims["sub"] == "12345"
    assert claims["name"] == "Asha"


def test_token_for_another_app_is_rejected(keypair):
    """Without the audience check, anyone's Google token would sign someone in here."""
    token = _make_token(keypair, audience="some-other-apps-client-id")

    with pytest.raises(TokenVerificationError, match="different app"):
        verify_oidc_token(token, issuer=ISSUER, jwks_url=JWKS_URL, audience=AUDIENCE)


def test_token_from_unexpected_issuer_is_rejected(keypair):
    token = _make_token(keypair, issuer="https://evil.example.com")

    with pytest.raises(TokenVerificationError, match="issuer"):
        verify_oidc_token(token, issuer=ISSUER, jwks_url=JWKS_URL, audience=AUDIENCE)


def test_expired_token_is_rejected(keypair):
    token = _make_token(keypair, expires_in=timedelta(minutes=-1))

    with pytest.raises(TokenVerificationError, match="expired"):
        verify_oidc_token(token, issuer=ISSUER, jwks_url=JWKS_URL, audience=AUDIENCE)


def test_token_signed_by_the_wrong_key_is_rejected(keypair):
    """The whole point: a well-formed token we didn't get the key for must fail."""
    attacker_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": "12345",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        attacker_key,
        algorithm="RS256",
    )

    with pytest.raises(TokenVerificationError):
        verify_oidc_token(token, issuer=ISSUER, jwks_url=JWKS_URL, audience=AUDIENCE)


def test_garbage_and_empty_tokens_are_rejected():
    for value in ("", "   ", "not-a-jwt", "a.b.c"):
        with pytest.raises(TokenVerificationError):
            verify_oidc_token(value, issuer=ISSUER, jwks_url=JWKS_URL, audience=AUDIENCE)


def test_google_accepts_either_issuer_spelling(keypair):
    """Google mints tokens under both forms and treats them as equivalent."""
    accepted = ["https://accounts.google.com", "accounts.google.com"]

    for issuer in accepted:
        token = _make_token(keypair, issuer=issuer)
        claims = verify_oidc_token(
            token, issuer=accepted, jwks_url=JWKS_URL, audience=AUDIENCE
        )
        assert claims["iss"] == issuer

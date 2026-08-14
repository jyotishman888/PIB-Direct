"""Verification of OpenID Connect ID tokens.

Telegram and Google both hand the browser a signed JWT and publish their keys
at a JWKS endpoint, so one implementation covers both. That's deliberate:
a single verification path is far easier to get right, and to review, than two
provider-specific ones.

The JS callback also gives the frontend a decoded copy of the claims. That copy
is worthless for trust — anyone can POST a made-up one — so nothing here reads
the payload before the signature checks out.
"""

import logging
from typing import Any

import jwt
from jwt import PyJWKClient

logger = logging.getLogger(__name__)

# Signing keys change rarely; caching avoids a JWKS fetch on every sign-in.
_jwk_clients: dict[str, PyJWKClient] = {}


class TokenVerificationError(RuntimeError):
    """Raised when an ID token is missing, malformed, or fails verification."""


def _jwk_client(jwks_url: str) -> PyJWKClient:
    client = _jwk_clients.get(jwks_url)
    if client is None:
        client = PyJWKClient(jwks_url, cache_keys=True)
        _jwk_clients[jwks_url] = client
    return client


def verify_oidc_token(
    token: str, *, issuer: str | list[str], jwks_url: str, audience: str
) -> dict[str, Any]:
    """Verify an ID token and return its claims.

    Checks the signature against the provider's published keys, and that the
    token was issued by `issuer` for `audience` and hasn't expired. The
    audience check is what stops a token minted for somebody else's app from
    signing someone in here.
    """
    if not token or not token.strip():
        raise TokenVerificationError("No ID token supplied.")

    try:
        signing_key = _jwk_client(jwks_url).get_signing_key_from_jwt(token)
        claims: dict[str, Any] = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=audience,
            issuer=issuer,
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenVerificationError("That sign-in has expired. Please try again.") from exc
    except jwt.InvalidAudienceError as exc:
        raise TokenVerificationError("This sign-in was issued for a different app.") from exc
    except jwt.InvalidIssuerError as exc:
        raise TokenVerificationError("This sign-in came from an unexpected issuer.") from exc
    except jwt.PyJWTError as exc:
        # Deliberately vague to the caller, specific in the log — the details
        # of *why* a token failed are useful to us and useful to an attacker.
        logger.warning("ID token verification failed: %s", exc)
        raise TokenVerificationError("Could not verify that sign-in.") from exc

    if not claims.get("sub"):
        raise TokenVerificationError("Sign-in is missing a subject claim.")

    return claims

"""The sign-in providers and how to read a verified token from each."""

from dataclasses import dataclass
from typing import Any

from pib_agent.config import Settings


class UnknownProviderError(ValueError):
    """Raised for a provider name that isn't supported."""


@dataclass(frozen=True, slots=True)
class ProviderProfile:
    """The bits of a verified token we actually store."""

    subject: str
    display_name: str | None
    email: str | None
    avatar_url: str | None


@dataclass(frozen=True, slots=True)
class Provider:
    name: str
    label: str
    issuer: str | list[str]
    jwks_url: str

    def client_id(self, settings: Settings) -> str | None:
        return getattr(settings, f"{self.name}_client_id", None)


TELEGRAM = Provider(
    name="telegram",
    label="Telegram",
    issuer="https://oauth.telegram.org",
    jwks_url="https://oauth.telegram.org/.well-known/jwks.json",
)

GOOGLE = Provider(
    name="google",
    label="Google",
    # Google mints tokens under both spellings and treats them as equivalent.
    issuer=["https://accounts.google.com", "accounts.google.com"],
    jwks_url="https://www.googleapis.com/oauth2/v3/certs",
)

PROVIDERS: dict[str, Provider] = {p.name: p for p in (TELEGRAM, GOOGLE)}


def get_provider(name: str) -> Provider:
    try:
        return PROVIDERS[name]
    except KeyError as exc:
        raise UnknownProviderError(f"Unsupported sign-in provider: {name!r}") from exc


def profile_from_claims(provider: Provider, claims: dict[str, Any]) -> ProviderProfile:
    """Map a provider's verified claims onto the fields we keep.

    `sub` is the identity key for every provider — never email, which people
    change and which Telegram doesn't supply at all.
    """
    name = claims.get("name") or claims.get("preferred_username")
    if not name:
        parts = [claims.get("given_name"), claims.get("family_name")]
        name = " ".join(p for p in parts if p) or None

    email = claims.get("email")
    # An unverified Google email is not evidence of anything; don't store it.
    if email and claims.get("email_verified") is False:
        email = None

    return ProviderProfile(
        subject=str(claims["sub"]),
        display_name=name,
        email=email,
        avatar_url=claims.get("picture"),
    )

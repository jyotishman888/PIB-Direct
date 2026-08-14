from pib_agent.auth.providers import (
    PROVIDERS,
    Provider,
    ProviderProfile,
    UnknownProviderError,
    get_provider,
)
from pib_agent.auth.service import (
    AuthenticatedUser,
    AuthError,
    IdentityAlreadyLinkedError,
    ProviderNotConfiguredError,
    get_or_create_user_for_telegram,
    get_user_snapshot,
    link_identity,
    login_with_provider,
    verify_provider_token,
)
from pib_agent.auth.sessions import (
    create_session,
    resolve_session,
    revoke_all_sessions_for_user,
    revoke_session,
)
from pib_agent.auth.verify import TokenVerificationError, verify_oidc_token

__all__ = [
    "PROVIDERS",
    "AuthError",
    "AuthenticatedUser",
    "IdentityAlreadyLinkedError",
    "Provider",
    "ProviderNotConfiguredError",
    "ProviderProfile",
    "TokenVerificationError",
    "UnknownProviderError",
    "create_session",
    "get_or_create_user_for_telegram",
    "get_provider",
    "get_user_snapshot",
    "link_identity",
    "login_with_provider",
    "resolve_session",
    "revoke_all_sessions_for_user",
    "revoke_session",
    "verify_oidc_token",
    "verify_provider_token",
]

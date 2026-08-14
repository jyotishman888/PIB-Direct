import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from pib_agent.api.deps import SessionScopeFn, get_current_user, get_session_scope, require_user
from pib_agent.api.schemas import (
    AuthProviderInfo,
    CurrentUser,
    MinistryRefOut,
    SignInRequest,
    SubscriptionsUpdate,
)
from pib_agent.auth import (
    PROVIDERS,
    AuthenticatedUser,
    AuthError,
    IdentityAlreadyLinkedError,
    ProviderNotConfiguredError,
    TokenVerificationError,
    UnknownProviderError,
    create_session,
    get_provider,
    link_identity,
    login_with_provider,
    revoke_session,
    verify_provider_token,
)
from pib_agent.config import get_settings
from pib_agent.telegram.subscriptions import (
    list_subscriptions_for_user,
    set_subscriptions_for_user,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(response: Response, token: str, max_age_seconds: int) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=max_age_seconds,
        httponly=True,  # JS can't read it, so XSS can't exfiltrate the session
        secure=settings.session_cookie_secure,
        samesite="lax",  # blocks cross-site POSTs while keeping normal navigation working
        path="/",
    )


def _to_current_user(user: AuthenticatedUser) -> CurrentUser:
    return CurrentUser(
        id=user.id,
        display_name=user.display_name,
        email=user.email,
        avatar_url=user.avatar_url,
        providers=list(user.providers),
    )


def _resolve_and_verify(provider_name: str, id_token: str):
    try:
        provider = get_provider(provider_name)
    except UnknownProviderError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    try:
        return provider, verify_provider_token(provider, id_token)
    except ProviderNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except TokenVerificationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@router.get("/providers", response_model=list[AuthProviderInfo])
def list_providers() -> list[AuthProviderInfo]:
    """Which sign-in methods this server can actually offer.

    Lets the login page hide a button rather than render one that 503s.
    """
    settings = get_settings()
    return [
        AuthProviderInfo(
            name=p.name, label=p.label, configured=bool(p.client_id(settings))
        )
        for p in PROVIDERS.values()
    ]


@router.get("/me", response_model=CurrentUser)
def me(current: AuthenticatedUser = Depends(require_user)) -> CurrentUser:
    return _to_current_user(current)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    scope: SessionScopeFn = Depends(get_session_scope),
) -> None:
    settings = get_settings()
    revoke_session(request.cookies.get(settings.session_cookie_name), session_scope=scope)
    response.delete_cookie(settings.session_cookie_name, path="/")


@router.get("/subscriptions", response_model=list[MinistryRefOut])
def get_my_subscriptions(
    current: AuthenticatedUser = Depends(require_user),
    scope: SessionScopeFn = Depends(get_session_scope),
) -> list[MinistryRefOut]:
    return [
        MinistryRefOut(id=m.id, name=m.name, slug=m.slug)
        for m in list_subscriptions_for_user(current.id, session_scope=scope)
    ]


@router.put("/subscriptions", response_model=list[MinistryRefOut])
def put_my_subscriptions(
    payload: SubscriptionsUpdate,
    current: AuthenticatedUser = Depends(require_user),
    scope: SessionScopeFn = Depends(get_session_scope),
) -> list[MinistryRefOut]:
    """Replace the signed-in user's ministry subscriptions.

    The same rows the Telegram bot reads, so a change here shows up in
    /mysubs and in the next notification run.
    """
    updated = set_subscriptions_for_user(
        current.id, set(payload.ministry_ids), session_scope=scope
    )
    return [MinistryRefOut(id=m.id, name=m.name, slug=m.slug) for m in updated]


# Anonymous-friendly variant used by the frontend on load: 200 with null rather
# than a 401 that would show up as an error in the browser console on every
# visit by a signed-out reader.
@router.get("/session", response_model=CurrentUser | None)
def current_session(
    current: AuthenticatedUser | None = Depends(get_current_user),
) -> CurrentUser | None:
    return _to_current_user(current) if current else None


# --- provider routes -------------------------------------------------------
# Registered last, deliberately: `/{provider_name}` is a catch-all that would
# otherwise swallow POSTs to the fixed paths above (`/auth/logout` matched it
# and demanded a sign-in body, returning 422 instead of logging out).


@router.post("/{provider_name}", response_model=CurrentUser)
def sign_in(
    provider_name: str,
    payload: SignInRequest,
    response: Response,
    scope: SessionScopeFn = Depends(get_session_scope),
) -> CurrentUser:
    """Verify a provider ID token, sign the user in, and set the session cookie."""
    provider, profile = _resolve_and_verify(provider_name, payload.id_token)

    user = login_with_provider(provider, profile, session_scope=scope)
    token, _expires_at = create_session(user.id, session_scope=scope)
    _set_session_cookie(response, token, get_settings().session_ttl_days * 86400)
    logger.info("User %s signed in via %s", user.id, provider.name)
    return _to_current_user(user)


@router.post("/{provider_name}/link", response_model=CurrentUser)
def link_provider(
    provider_name: str,
    payload: SignInRequest,
    current: AuthenticatedUser = Depends(require_user),
    scope: SessionScopeFn = Depends(get_session_scope),
) -> CurrentUser:
    """Connect a second sign-in method to the account already signed in."""
    provider, profile = _resolve_and_verify(provider_name, payload.id_token)

    try:
        user = link_identity(current.id, provider, profile, session_scope=scope)
    except IdentityAlreadyLinkedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return _to_current_user(user)

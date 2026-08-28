"""Telling "this article broke" apart from "this account can't call Claude".

Both Claude-calling stages isolate failures per article, which is right when
one release is malformed and wrong when the account is out of credit: every
remaining article then fails identically, and the pass spends the whole
backlog on calls that cannot succeed. A 147-article backlog did exactly that
for five days, reporting "failed 147" each hour - which reads as "the
articles are broken" and buries the one fact that matters.
"""

import anthropic

# Substring of the 400 the API returns when the account is out of credit. It
# arrives as a plain invalid_request_error, so no status code or exception
# class separates it from a genuinely malformed request.
_OUT_OF_CREDIT = "credit balance is too low"


def is_account_level(exc: Exception) -> bool:
    """True when retrying a different article would fail exactly the same way."""
    if isinstance(exc, anthropic.AuthenticationError | anthropic.PermissionDeniedError):
        return True
    return _OUT_OF_CREDIT in str(exc)

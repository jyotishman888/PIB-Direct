"""Both Claude stages must tell a broken article apart from a broken account."""

import anthropic
import httpx
import pytest

from pib_agent.claude_errors import is_account_level


def _api_error(message: str) -> anthropic.APIError:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return anthropic.APIError(message, request=request, body=None)


@pytest.mark.parametrize(
    "message, expected",
    [
        ("Your credit balance is too low to access the Anthropic API.", True),
        ("messages.0.content: field required", False),
        ("Overloaded", False),
    ],
)
def test_out_of_credit_is_account_level(message, expected):
    assert is_account_level(_api_error(message)) is expected


def test_auth_and_permission_errors_are_account_level():
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    cases = (
        (401, anthropic.AuthenticationError),
        (403, anthropic.PermissionDeniedError),
    )
    for status, cls in cases:
        response = httpx.Response(status, request=request)
        assert is_account_level(cls("nope", response=response, body=None)) is True

import pytest
from pydantic import ValidationError

from pib_agent.config import Settings


def test_settings_defaults_when_no_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    settings = Settings(_env_file=None)

    assert settings.database_url.startswith("sqlite:///")
    assert settings.log_level == "INFO"
    assert settings.anthropic_api_key is None
    assert settings.telegram_bot_token is None
    assert len(settings.pib_listing_urls) >= 2
    assert all("pib.gov.in" in url for url in settings.pib_listing_urls)


def test_settings_read_env_overrides(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./somewhere/custom.db")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")

    settings = Settings(_env_file=None)

    assert settings.database_url == "sqlite:///./somewhere/custom.db"
    assert settings.log_level == "DEBUG"
    assert settings.anthropic_api_key == "sk-test-123"


def test_detail_url_template_formats_prid():
    settings = Settings(_env_file=None)
    url = settings.pib_detail_url_template.format(prid=2296855)
    assert url == "https://pib.gov.in/PressReleasePage.aspx?PRID=2296855"


def test_empty_database_url_is_rejected_with_a_useful_message():
    """An unset-but-present variable used to surface as an opaque SQLAlchemy
    ArgumentError thrown at import time, naming neither the variable nor why."""
    with pytest.raises(ValidationError, match="DATABASE_URL is empty"):
        Settings(_env_file=None, database_url="")


def test_unresolved_platform_reference_is_rejected():
    """Railway stores an unresolvable ${{Service.VAR}} reference verbatim."""
    with pytest.raises(ValidationError, match="doesn't look like a connection string"):
        Settings(_env_file=None, database_url="${{Postgres.DATABASE_PUBLIC_URL}}")


def test_quoted_database_url_is_tolerated():
    """Pasting a value with surrounding quotes is an easy and silent mistake."""
    settings = Settings(_env_file=None, database_url='"postgresql://u@h/db"')

    assert settings.database_url == "postgresql+psycopg://u@h/db"


def test_pasted_variable_name_is_rejected():
    """Pasting `KEY=value` into a value field passes every shape check but is
    not a connection string."""
    with pytest.raises(ValidationError, match="includes the variable name"):
        Settings(_env_file=None, database_url="DATABASE_URL=postgresql://u:p@h:5432/db")


def test_redaction_keeps_the_password_out_of_errors():
    """These messages land in deploy logs, which get pasted into chats."""
    from pib_agent.config import _redact

    redacted = _redact("postgresql://appuser:sup3r-s3cret@db.host:5432/railway")

    assert "sup3r-s3cret" not in redacted
    assert "appuser" in redacted
    assert "db.host:5432/railway" in redacted

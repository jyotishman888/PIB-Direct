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

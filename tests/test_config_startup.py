"""Tests for JWT config fields in Settings (Task 1.2).

Strict TDD: written BEFORE the implementation.
"""


class TestJwtConfigDefaults:
    def test_jwt_secret_defaults_to_empty(self, monkeypatch):
        """Settings().jwt_secret defaults to empty string when env var not set."""
        monkeypatch.delenv("CHESSLENS_JWT_SECRET", raising=False)

        from chesslens.config import Settings

        s = Settings()
        assert s.jwt_secret == ""

    def test_jwt_secret_loaded_from_env(self, monkeypatch):
        """Settings().jwt_secret reads from CHESSLENS_JWT_SECRET env var."""
        monkeypatch.setenv("CHESSLENS_JWT_SECRET", "mysupersecret")

        from chesslens.config import Settings

        s = Settings()
        assert s.jwt_secret == "mysupersecret"

    def test_access_token_ttl_minutes_defaults_to_15(self, monkeypatch):
        """access_token_ttl_minutes defaults to 15."""
        monkeypatch.delenv("CHESSLENS_ACCESS_TOKEN_TTL_MINUTES", raising=False)

        from chesslens.config import Settings

        s = Settings()
        assert s.access_token_ttl_minutes == 15

    def test_refresh_token_ttl_days_defaults_to_7(self, monkeypatch):
        """refresh_token_ttl_days defaults to 7."""
        monkeypatch.delenv("CHESSLENS_REFRESH_TOKEN_TTL_DAYS", raising=False)

        from chesslens.config import Settings

        s = Settings()
        assert s.refresh_token_ttl_days == 7

    def test_ttl_fields_loaded_from_env(self, monkeypatch):
        """access_token_ttl_minutes and refresh_token_ttl_days load from env vars."""
        monkeypatch.setenv("CHESSLENS_ACCESS_TOKEN_TTL_MINUTES", "30")
        monkeypatch.setenv("CHESSLENS_REFRESH_TOKEN_TTL_DAYS", "14")

        from chesslens.config import Settings

        s = Settings()
        assert s.access_token_ttl_minutes == 30
        assert s.refresh_token_ttl_days == 14

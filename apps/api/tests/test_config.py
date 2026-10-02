from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_environment_overrides_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text('CORS_ORIGINS=["https://file.example"]\n', encoding="utf-8")
    monkeypatch.setenv("CORS_ORIGINS", '["https://environment.example"]')
    assert Settings(_env_file=dotenv).cors_origins == ["https://environment.example"]


@pytest.mark.parametrize("url", ["sqlite:///test.db", "postgresql://u:p@localhost/db"])
def test_database_requires_postgres_psycopg(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", url)
    with pytest.raises(ValidationError):
        Settings()


def test_wildcard_cors_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", '["*"]')
    with pytest.raises(ValidationError):
        Settings()

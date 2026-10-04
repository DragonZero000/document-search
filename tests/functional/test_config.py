import pytest
from pydantic import ValidationError

from app.config import Settings


@pytest.mark.parametrize(("env", "value"), [("ES_MAX_IDS", "10001"), ("ES_MAX_IDS", "0"), ("SEARCH_LIMIT", "0")])
def test_invalid_limits_are_rejected(monkeypatch: pytest.MonkeyPatch, env: str, value: str):
    monkeypatch.setenv(env, value)

    with pytest.raises(ValidationError):
        Settings()

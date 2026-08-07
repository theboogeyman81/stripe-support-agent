from unittest.mock import MagicMock, patch

from src.observability.langfuse_client import get_langfuse_client


def _settings(**overrides):
    """Return a mock settings object with Langfuse attributes."""
    defaults = {
        "langfuse_public_key": "pk-lf-test",
        "langfuse_secret_key": "sk-lf-test",
        "langfuse_host": "https://cloud.langfuse.com",
    }
    m = MagicMock()
    for k, v in {**defaults, **overrides}.items():
        setattr(m, k, v)
    return m


def test_returns_client_when_keys_present():
    with patch("src.observability.langfuse_client.Langfuse") as mock_cls:
        mock_cls.return_value = MagicMock()
        result = get_langfuse_client(_settings())
    assert result is not None


def test_returns_none_when_public_key_missing():
    result = get_langfuse_client(_settings(langfuse_public_key=""))
    assert result is None


def test_returns_none_when_secret_key_missing():
    result = get_langfuse_client(_settings(langfuse_secret_key=""))
    assert result is None


def test_passes_correct_args_to_langfuse():
    with patch("src.observability.langfuse_client.Langfuse") as mock_cls:
        get_langfuse_client(_settings(langfuse_host="https://us.cloud.langfuse.com"))
        mock_cls.assert_called_once_with(
            public_key="pk-lf-test",
            secret_key="sk-lf-test",
            host="https://us.cloud.langfuse.com",
        )

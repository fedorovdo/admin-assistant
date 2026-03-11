from __future__ import annotations

import httpx

from admin_assistant.infrastructure.ai.httpx_provider import HttpxAIProviderClient
from admin_assistant.modules.settings.models import AIProviderConfig


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.is_error = False
        self.status_code = 200
        self.text = ""

    def json(self) -> dict:
        return self._payload


class FakeClient:
    def __init__(
        self,
        timeout,
        response_payload: dict | None = None,
        get_payload: dict | None = None,
    ) -> None:
        self.timeout = timeout
        self.response_payload = response_payload
        self.get_payload = get_payload
        self.post_calls: list[tuple[str, dict, dict]] = []
        self.get_calls: list[tuple[str, dict]] = []

    def __enter__(self) -> "FakeClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def post(self, endpoint: str, headers: dict, json: dict) -> FakeResponse:
        self.post_calls.append((endpoint, headers, json))
        return FakeResponse(self.response_payload)

    def get(self, endpoint: str, headers: dict | None = None) -> FakeResponse:
        self.get_calls.append((endpoint, headers or {}))
        return FakeResponse(self.get_payload or {})


def test_httpx_provider_uses_responses_api_json_schema_payload(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_client_factory(*, timeout):
        client = FakeClient(
            timeout=timeout,
            response_payload={
                "output_text": (
                    '{"summary":"analysis ok","probable_causes":[],"next_steps":[],"suggested_actions":[]}'
                )
            },
        )
        captured["client"] = client
        return client

    monkeypatch.setattr("admin_assistant.infrastructure.ai.httpx_provider.httpx.Client", fake_client_factory)

    provider = HttpxAIProviderClient()
    config = AIProviderConfig(
        id="provider-1",
        provider_name="openai",
        display_name="OpenAI",
        base_url="https://api.openai.com/v1",
        model_name="gpt-4o-mini",
        api_key_ref="openai-key",
        timeout_sec=30,
        temperature=0.1,
        is_default=True,
        is_enabled=True,
    )

    result = provider.analyze(prompt="analyze this", provider_config=config, api_key="sk-test")

    client = captured["client"]
    assert isinstance(client, FakeClient)
    assert result.summary == "analysis ok"
    assert isinstance(client.timeout, httpx.Timeout)
    assert client.timeout.read == 30
    assert len(client.post_calls) == 1
    endpoint, headers, payload = client.post_calls[0]
    assert endpoint == "https://api.openai.com/v1/responses"
    assert headers["Authorization"] == "Bearer sk-test"
    assert payload["input"] == "analyze this"
    assert "messages" not in payload
    assert "response_format" not in payload
    assert payload["text"]["format"]["type"] == "json_schema"
    assert payload["text"]["format"]["strict"] is True
    assert payload["text"]["format"]["schema"]["type"] == "object"
    assert payload["text"]["format"]["schema"]["additionalProperties"] is False
    assert payload["text"]["format"]["schema"]["$defs"]["ProviderSuggestedActionResponse"]["additionalProperties"] is False
    assert payload["text"]["format"]["schema"]["$defs"]["ProviderFixStepResponse"]["additionalProperties"] is False


def test_httpx_provider_uses_ollama_generate_endpoint(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_client_factory(*, timeout):
        client = FakeClient(
            timeout=timeout,
            response_payload={
                "response": (
                    '{"summary":"local ok","probable_causes":[],"next_steps":["check logs"],'
                    '"suggested_actions":[]}'
                )
            },
        )
        captured["client"] = client
        return client

    monkeypatch.setattr("admin_assistant.infrastructure.ai.httpx_provider.httpx.Client", fake_client_factory)

    provider = HttpxAIProviderClient()
    config = AIProviderConfig(
        id="provider-2",
        provider_name="ollama",
        display_name="Ollama",
        base_url="http://localhost:11434",
        model_name="llama3",
        api_key_ref=None,
        timeout_sec=45,
        temperature=0.2,
        is_default=True,
        is_enabled=True,
    )

    result = provider.analyze(prompt="analyze this locally", provider_config=config, api_key=None)

    client = captured["client"]
    assert isinstance(client, FakeClient)
    assert result.summary == "local ok"
    assert result.next_steps == ("check logs",)
    assert isinstance(client.timeout, httpx.Timeout)
    assert client.timeout.connect == 10
    assert client.timeout.read == 180
    assert client.timeout.write == 30
    assert len(client.post_calls) == 1
    endpoint, headers, payload = client.post_calls[0]
    assert endpoint == "http://localhost:11434/api/generate"
    assert "Authorization" not in headers
    assert payload["model"] == "llama3"
    assert payload["prompt"] == "analyze this locally"
    assert payload["stream"] is False
    assert payload["format"] == "json"


def test_httpx_provider_checks_openai_connection_via_models_endpoint(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_client_factory(*, timeout):
        client = FakeClient(timeout=timeout, get_payload={"data": [{"id": "gpt-4o-mini"}]})
        captured["client"] = client
        return client

    monkeypatch.setattr("admin_assistant.infrastructure.ai.httpx_provider.httpx.Client", fake_client_factory)

    provider = HttpxAIProviderClient()
    config = AIProviderConfig(
        id="provider-3",
        provider_name="openai",
        display_name="OpenAI",
        base_url="https://api.openai.com/v1",
        model_name="gpt-4o-mini",
        api_key_ref="openai-key",
        timeout_sec=30,
        temperature=0.1,
        is_default=True,
        is_enabled=True,
    )

    result = provider.test_connection(provider_config=config, api_key="sk-test")

    client = captured["client"]
    assert isinstance(client, FakeClient)
    assert result.success is True
    assert result.message == "OpenAI connection successful."
    assert isinstance(client.timeout, httpx.Timeout)
    assert client.timeout.read == 30
    assert len(client.get_calls) == 1
    endpoint, headers = client.get_calls[0]
    assert endpoint == "https://api.openai.com/v1/models"
    assert headers["Authorization"] == "Bearer sk-test"


def test_httpx_provider_reports_ollama_model_not_found(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_client_factory(*, timeout):
        client = FakeClient(timeout=timeout, get_payload={"models": [{"name": "mistral:latest"}]})
        captured["client"] = client
        return client

    monkeypatch.setattr("admin_assistant.infrastructure.ai.httpx_provider.httpx.Client", fake_client_factory)

    provider = HttpxAIProviderClient()
    config = AIProviderConfig(
        id="provider-4",
        provider_name="ollama",
        display_name="Ollama",
        base_url="http://localhost:11434",
        model_name="llama3",
        api_key_ref=None,
        timeout_sec=30,
        temperature=0.1,
        is_default=True,
        is_enabled=True,
    )

    result = provider.test_connection(provider_config=config, api_key=None)

    client = captured["client"]
    assert isinstance(client, FakeClient)
    assert result.success is False
    assert result.message == "Ollama reachable, model not found."
    assert isinstance(client.timeout, httpx.Timeout)
    assert client.timeout.read == 30
    assert len(client.get_calls) == 1
    endpoint, headers = client.get_calls[0]
    assert endpoint == "http://localhost:11434/api/tags"
    assert headers == {}


def test_httpx_provider_reports_ollama_read_timeout_with_runtime_details(monkeypatch) -> None:
    def fake_client_factory(*, timeout):
        class TimeoutClient(FakeClient):
            def post(self, endpoint: str, headers: dict, json: dict):
                raise httpx.ReadTimeout("timed out", request=httpx.Request("POST", endpoint))

        return TimeoutClient(timeout=timeout)

    monkeypatch.setattr("admin_assistant.infrastructure.ai.httpx_provider.httpx.Client", fake_client_factory)

    provider = HttpxAIProviderClient()
    config = AIProviderConfig(
        id="provider-timeout-1",
        provider_name="ollama",
        display_name="Ollama",
        base_url="http://127.0.0.1:11434",
        model_name="qwen2.5:7b",
        api_key_ref=None,
        timeout_sec=30,
        temperature=0.1,
        is_default=True,
        is_enabled=True,
    )

    try:
        provider.analyze(prompt="x" * 5000, provider_config=config, api_key=None)
    except Exception as exc:
        message = str(exc)
    else:  # pragma: no cover - defensive failure path
        raise AssertionError("Expected Ollama timeout.")

    assert "endpoint 'http://127.0.0.1:11434/api/generate'" in message
    assert "model 'qwen2.5:7b'" in message
    assert "prompt length 5000 characters" in message
    assert "read=" in message

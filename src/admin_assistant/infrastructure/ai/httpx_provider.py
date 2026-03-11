from __future__ import annotations

import json
import logging
import time

import httpx
from pydantic import ValidationError as PydanticValidationError

from admin_assistant.core.errors import ExternalIntegrationError
from admin_assistant.modules.ai.dto import AIProviderAnalysisResponse
from admin_assistant.modules.settings.dto import ProviderConnectionTestResult
from admin_assistant.modules.settings.models import AIProviderConfig


logger = logging.getLogger(__name__)


class HttpxAIProviderClient:
    def analyze(
        self,
        prompt: str,
        provider_config: AIProviderConfig,
        api_key: str | None = None,
    ) -> AIProviderAnalysisResponse:
        provider_name = provider_config.provider_name.strip().lower()
        if provider_name in {"openai", "openai_compatible"}:
            return self._analyze_openai_like(
                prompt=prompt,
                provider_config=provider_config,
                api_key=api_key,
            )
        if provider_name == "ollama":
            return self._analyze_ollama(
                prompt=prompt,
                provider_config=provider_config,
            )
        raise ExternalIntegrationError(f"Unsupported AI provider '{provider_config.provider_name}'.")

    def test_connection(
        self,
        provider_config: AIProviderConfig,
        api_key: str | None = None,
    ) -> ProviderConnectionTestResult:
        provider_name = provider_config.provider_name.strip().lower()
        if provider_name in {"openai", "openai_compatible"}:
            return self._test_openai_like_connection(provider_config=provider_config, api_key=api_key)
        if provider_name == "ollama":
            return self._test_ollama_connection(provider_config=provider_config)
        return ProviderConnectionTestResult(
            success=False,
            message=f"Provider '{provider_config.provider_name}' is not supported.",
        )

    def _analyze_openai_like(
        self,
        prompt: str,
        provider_config: AIProviderConfig,
        api_key: str | None,
    ) -> AIProviderAnalysisResponse:
        endpoint = self._resolve_openai_endpoint(provider_config.base_url)
        timeout = self._build_timeout(provider_config, purpose="analysis")
        response_schema = self._build_response_schema()
        payload = {
            "model": provider_config.model_name,
            "input": prompt,
            "temperature": provider_config.temperature,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "admin_assistant_analysis",
                    "strict": True,
                    "schema": response_schema,
                }
            },
        }
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        started_at = time.perf_counter()
        logger.debug(
            "Starting %s analysis request | endpoint=%s | model=%s | timeout=%s | prompt_length=%s",
            provider_config.provider_name,
            endpoint,
            provider_config.model_name,
            self._format_timeout(timeout),
            len(prompt),
        )
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(endpoint, headers=headers, json=payload)
                if response.is_error:
                    raise ExternalIntegrationError(
                        self._build_http_error_message(
                            provider_label="OpenAI-compatible provider" if provider_config.provider_name.strip().lower() == "openai_compatible" else "OpenAI",
                            response=response,
                            model_name=provider_config.model_name,
                        )
                    )
        except httpx.ConnectTimeout as exc:
            raise ExternalIntegrationError(
                self._build_timeout_error_message(
                    provider_label=provider_config.provider_name,
                    endpoint=endpoint,
                    model_name=provider_config.model_name,
                    timeout=timeout,
                    prompt_length=len(prompt),
                    elapsed_sec=time.perf_counter() - started_at,
                    phase="connect",
                )
            ) from exc
        except httpx.ReadTimeout as exc:
            raise ExternalIntegrationError(
                self._build_timeout_error_message(
                    provider_label=provider_config.provider_name,
                    endpoint=endpoint,
                    model_name=provider_config.model_name,
                    timeout=timeout,
                    prompt_length=len(prompt),
                    elapsed_sec=time.perf_counter() - started_at,
                    phase="read",
                )
            ) from exc
        except httpx.TimeoutException as exc:
            raise ExternalIntegrationError(
                self._build_timeout_error_message(
                    provider_label=provider_config.provider_name,
                    endpoint=endpoint,
                    model_name=provider_config.model_name,
                    timeout=timeout,
                    prompt_length=len(prompt),
                    elapsed_sec=time.perf_counter() - started_at,
                    phase="request",
                )
            ) from exc
        except httpx.HTTPError as exc:
            raise ExternalIntegrationError(
                f"{provider_config.provider_name} request failed for endpoint '{endpoint}' "
                f"with model '{provider_config.model_name}' and timeout {self._format_timeout(timeout)}: {exc}"
            ) from exc

        logger.debug(
            "Completed %s analysis request | endpoint=%s | model=%s | elapsed=%.2fs",
            provider_config.provider_name,
            endpoint,
            provider_config.model_name,
            time.perf_counter() - started_at,
        )

        try:
            response_json = response.json()
        except json.JSONDecodeError as exc:
            raise ExternalIntegrationError("Provider returned invalid JSON.") from exc

        output_text = self._extract_openai_output_text(response_json)
        return self._validate_analysis_output(output_text, provider_label=provider_config.provider_name)

    def _analyze_ollama(
        self,
        prompt: str,
        provider_config: AIProviderConfig,
    ) -> AIProviderAnalysisResponse:
        endpoint = self._resolve_ollama_endpoint(provider_config.base_url)
        timeout = self._build_timeout(provider_config, purpose="analysis")
        payload = {
            "model": provider_config.model_name,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": provider_config.temperature,
            },
        }
        headers = {"Content-Type": "application/json"}

        started_at = time.perf_counter()
        logger.debug(
            "Starting Ollama analysis request | endpoint=%s | model=%s | timeout=%s | prompt_length=%s",
            endpoint,
            provider_config.model_name,
            self._format_timeout(timeout),
            len(prompt),
        )
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(endpoint, headers=headers, json=payload)
                if response.is_error:
                    raise ExternalIntegrationError(
                        self._build_http_error_message(
                            provider_label="Ollama",
                            response=response,
                            model_name=provider_config.model_name,
                        )
                    )
        except httpx.ConnectTimeout as exc:
            raise ExternalIntegrationError(
                self._build_timeout_error_message(
                    provider_label="Ollama",
                    endpoint=endpoint,
                    model_name=provider_config.model_name,
                    timeout=timeout,
                    prompt_length=len(prompt),
                    elapsed_sec=time.perf_counter() - started_at,
                    phase="connect",
                )
            ) from exc
        except httpx.ReadTimeout as exc:
            raise ExternalIntegrationError(
                self._build_timeout_error_message(
                    provider_label="Ollama",
                    endpoint=endpoint,
                    model_name=provider_config.model_name,
                    timeout=timeout,
                    prompt_length=len(prompt),
                    elapsed_sec=time.perf_counter() - started_at,
                    phase="read",
                )
            ) from exc
        except httpx.TimeoutException as exc:
            raise ExternalIntegrationError(
                self._build_timeout_error_message(
                    provider_label="Ollama",
                    endpoint=endpoint,
                    model_name=provider_config.model_name,
                    timeout=timeout,
                    prompt_length=len(prompt),
                    elapsed_sec=time.perf_counter() - started_at,
                    phase="request",
                )
            ) from exc
        except httpx.HTTPError as exc:
            raise ExternalIntegrationError(
                f"Ollama request failed for endpoint '{endpoint}' with model '{provider_config.model_name}' "
                f"and timeout {self._format_timeout(timeout)}: {exc}"
            ) from exc

        logger.debug(
            "Completed Ollama analysis request | endpoint=%s | model=%s | elapsed=%.2fs",
            endpoint,
            provider_config.model_name,
            time.perf_counter() - started_at,
        )

        try:
            response_json = response.json()
        except json.JSONDecodeError as exc:
            raise ExternalIntegrationError("Ollama returned invalid JSON.") from exc

        output_text = self._extract_ollama_output_text(response_json)
        return self._validate_analysis_output(output_text, provider_label="Ollama")

    def _resolve_openai_endpoint(self, base_url: str) -> str:
        normalized = base_url.rstrip("/")
        if normalized.endswith("/responses"):
            return normalized
        return f"{normalized}/responses"

    def _resolve_openai_models_endpoint(self, base_url: str) -> str:
        normalized = base_url.rstrip("/")
        if normalized.endswith("/responses"):
            normalized = normalized[: -len("/responses")]
        if normalized.endswith("/models"):
            return normalized
        return f"{normalized}/models"

    def _resolve_ollama_endpoint(self, base_url: str) -> str:
        normalized = base_url.rstrip("/")
        if normalized.endswith("/api/generate"):
            return normalized
        return f"{normalized}/api/generate"

    def _resolve_ollama_tags_endpoint(self, base_url: str) -> str:
        normalized = base_url.rstrip("/")
        if normalized.endswith("/api/tags"):
            return normalized
        return f"{normalized}/api/tags"

    def _extract_openai_output_text(self, response_json: dict) -> str:
        output_text = response_json.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text

        for output_item in response_json.get("output", []):
            if not isinstance(output_item, dict):
                continue
            for content_item in output_item.get("content", []):
                if not isinstance(content_item, dict):
                    continue
                text_value = content_item.get("text")
                if isinstance(text_value, str) and text_value.strip():
                    return text_value

        raise ExternalIntegrationError("OpenAI response did not include a text analysis payload.")

    def _extract_ollama_output_text(self, response_json: dict) -> str:
        response_value = response_json.get("response")
        if isinstance(response_value, str) and response_value.strip():
            return response_value
        if isinstance(response_value, (dict, list)):
            return json.dumps(response_value, ensure_ascii=False)

        message = response_json.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return content

        raise ExternalIntegrationError("Ollama response did not include a usable text analysis payload.")

    def _validate_analysis_output(self, output_text: str, provider_label: str) -> AIProviderAnalysisResponse:
        cleaned_output = self._normalize_json_text(output_text)
        try:
            return AIProviderAnalysisResponse.model_validate_json(cleaned_output)
        except PydanticValidationError as exc:
            raise ExternalIntegrationError(
                f"{provider_label} returned an invalid structured analysis payload."
            ) from exc

    def _normalize_json_text(self, output_text: str) -> str:
        cleaned = output_text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()

        start_index = cleaned.find("{")
        end_index = cleaned.rfind("}")
        if start_index != -1 and end_index > start_index:
            return cleaned[start_index : end_index + 1]
        return cleaned

    def _build_response_schema(self) -> dict:
        schema = AIProviderAnalysisResponse.model_json_schema()
        return self._normalize_schema(schema)

    def _normalize_schema(self, node: object, *, in_properties: bool = False) -> object:
        if isinstance(node, dict):
            normalized: dict[str, object] = {}
            for key, value in node.items():
                if not in_properties and key in {"title", "default"}:
                    continue
                normalized[key] = self._normalize_schema(value, in_properties=(key == "properties"))

            if normalized.get("type") == "object":
                properties = normalized.get("properties")
                if isinstance(properties, dict):
                    normalized["required"] = list(properties.keys())
                normalized.setdefault("additionalProperties", False)
            return normalized

        if isinstance(node, list):
            return [self._normalize_schema(item, in_properties=in_properties) for item in node]

        return node

    def _build_http_error_message(self, provider_label: str, response: httpx.Response, model_name: str) -> str:
        try:
            body = json.dumps(response.json(), ensure_ascii=False)
        except (json.JSONDecodeError, ValueError):
            body = response.text

        return (
            f"{provider_label} request failed with HTTP {response.status_code} "
            f"for model '{model_name}': {body}"
        )

    def _test_openai_like_connection(
        self,
        provider_config: AIProviderConfig,
        api_key: str | None,
    ) -> ProviderConnectionTestResult:
        if not api_key:
            return ProviderConnectionTestResult(success=False, message="API key missing.")

        provider_label = (
            "OpenAI-compatible provider"
            if provider_config.provider_name.strip().lower() == "openai_compatible"
            else "OpenAI"
        )
        endpoint = self._resolve_openai_models_endpoint(provider_config.base_url)
        timeout = self._build_timeout(provider_config, purpose="test")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        logger.debug(
            "Testing %s connectivity | endpoint=%s | model=%s | timeout=%s",
            provider_label,
            endpoint,
            provider_config.model_name,
            self._format_timeout(timeout),
        )
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.get(endpoint, headers=headers)
                if response.is_error:
                    return ProviderConnectionTestResult(
                        success=False,
                        message=self._build_http_error_message(
                            provider_label=provider_label,
                            response=response,
                            model_name=provider_config.model_name,
                        ),
                    )
        except httpx.HTTPError as exc:
            return ProviderConnectionTestResult(
                success=False,
                message=f"Failed to connect to provider: {exc}",
            )

        return ProviderConnectionTestResult(
            success=True,
            message=f"{provider_label} connection successful.",
        )

    def _test_ollama_connection(
        self,
        provider_config: AIProviderConfig,
    ) -> ProviderConnectionTestResult:
        endpoint = self._resolve_ollama_tags_endpoint(provider_config.base_url)
        timeout = self._build_timeout(provider_config, purpose="test")
        logger.debug(
            "Testing Ollama connectivity | endpoint=%s | model=%s | timeout=%s",
            endpoint,
            provider_config.model_name,
            self._format_timeout(timeout),
        )
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.get(endpoint)
                if response.is_error:
                    return ProviderConnectionTestResult(
                        success=False,
                        message=self._build_http_error_message(
                            provider_label="Ollama",
                            response=response,
                            model_name=provider_config.model_name,
                        ),
                    )
        except httpx.HTTPError as exc:
            return ProviderConnectionTestResult(
                success=False,
                message=f"Failed to connect to provider: {exc}",
            )

        try:
            payload = response.json()
        except json.JSONDecodeError:
            return ProviderConnectionTestResult(success=False, message="Ollama returned invalid JSON.")

        models = payload.get("models", [])
        available_names: set[str] = set()
        for item in models:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if isinstance(name, str) and name.strip():
                available_names.add(name.strip())
                available_names.add(name.strip().split(":", 1)[0])

        requested_model = provider_config.model_name.strip()
        if requested_model and requested_model in available_names:
            return ProviderConnectionTestResult(success=True, message="Ollama reachable, model found.")
        if requested_model:
            return ProviderConnectionTestResult(success=False, message="Ollama reachable, model not found.")
        return ProviderConnectionTestResult(success=True, message="Ollama connection successful.")

    def _build_timeout(self, provider_config: AIProviderConfig, *, purpose: str) -> httpx.Timeout:
        configured_timeout = max(float(provider_config.timeout_sec), 1.0)
        provider_name = provider_config.provider_name.strip().lower()
        if provider_name == "ollama" and purpose == "analysis":
            read_timeout = max(configured_timeout, 180.0)
            return httpx.Timeout(connect=10.0, read=read_timeout, write=30.0, pool=10.0)
        return httpx.Timeout(configured_timeout)

    def _format_timeout(self, timeout: httpx.Timeout) -> str:
        return (
            f"connect={timeout.connect}s read={timeout.read}s "
            f"write={timeout.write}s pool={timeout.pool}s"
        )

    def _build_timeout_error_message(
        self,
        *,
        provider_label: str,
        endpoint: str,
        model_name: str,
        timeout: httpx.Timeout,
        prompt_length: int,
        elapsed_sec: float,
        phase: str,
    ) -> str:
        return (
            f"{provider_label} request timed out during {phase} for endpoint '{endpoint}' "
            f"using model '{model_name}' after {elapsed_sec:.2f}s with timeout "
            f"{self._format_timeout(timeout)} and prompt length {prompt_length} characters."
        )

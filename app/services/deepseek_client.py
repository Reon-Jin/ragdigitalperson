from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, Literal, Sequence

import httpx

from app.config import Settings


ModelProvider = Literal["deepseek", "qwen", "mimo", "ollama"]


class CompatibleLLMClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _raise_api_error(self, provider: ModelProvider, exc: httpx.HTTPStatusError) -> None:
        status_code = exc.response.status_code
        raw_body = exc.response.text.strip()
        detail = raw_body[:600] if raw_body else ""
        if provider == "mimo" and status_code == 402:
            message = "Xiaomi Mimo API returned 402 Payment Required. Check whether the account has available balance, billing is activated, and the model is enabled."
        else:
            message = f"{self.provider_label(provider)} API returned HTTP {status_code}."
        if detail:
            message = f"{message} Response: {detail}"
        raise RuntimeError(message) from exc

    def providers(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "deepseek",
                "label": "DeepSeek",
                "model": self.settings.deepseek_model,
                "configured": bool(self.settings.deepseek_api_key),
            },
            {
                "id": "qwen",
                "label": "Qwen",
                "model": self.settings.qwen_model,
                "configured": bool(self.settings.qwen_api_key),
            },
            {
                "id": "mimo",
                "label": "Xiaomi Mimo",
                "model": self.settings.mimo_model,
                "configured": bool(self.settings.mimo_api_key),
            },
            {
                "id": "ollama",
                "label": "Ollama",
                "model": self.settings.ollama_model,
                "configured": self.is_configured("ollama"),
            },
        ]

    def normalize_provider(self, provider: str | None) -> ModelProvider:
        if provider == "qwen":
            return "qwen"
        if provider == "mimo":
            return "mimo"
        if provider == "ollama":
            return "ollama"
        return "deepseek"

    def is_configured(self, provider: str | None) -> bool:
        normalized = self.normalize_provider(provider)
        if normalized == "ollama":
            return bool(self.settings.ollama_base_url.strip() and self.settings.ollama_model.strip())
        if normalized == "qwen":
            return bool(self.settings.qwen_api_key)
        if normalized == "mimo":
            return bool(self.settings.mimo_api_key)
        return bool(self.settings.deepseek_api_key)

    def provider_label(self, provider: str | None) -> str:
        normalized = self.normalize_provider(provider)
        if normalized == "qwen":
            return "Qwen"
        if normalized == "mimo":
            return "Xiaomi Mimo"
        if normalized == "ollama":
            return "Ollama"
        return "DeepSeek"

    def _headers(self, provider: ModelProvider) -> dict[str, str]:
        if provider == "ollama":
            return {"Content-Type": "application/json"}
        if provider == "qwen":
            api_key = self.settings.qwen_api_key
        elif provider == "mimo":
            api_key = self.settings.mimo_api_key
        else:
            api_key = self.settings.deepseek_api_key
        if not api_key:
            raise RuntimeError(f"{self.provider_label(provider)} API key is not configured.")
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def _base_url(self, provider: ModelProvider) -> str:
        if provider == "qwen":
            return self.settings.qwen_base_url
        if provider == "mimo":
            return self.settings.mimo_base_url
        if provider == "ollama":
            return self.settings.ollama_base_url
        return self.settings.deepseek_base_url

    def _model_name(self, provider: ModelProvider) -> str:
        if provider == "qwen":
            return self.settings.qwen_model
        if provider == "mimo":
            return self.settings.mimo_model
        if provider == "ollama":
            return self.settings.ollama_model
        return self.settings.deepseek_model

    def _url(self, provider: ModelProvider) -> str:
        if provider == "ollama":
            return f"{self._base_url(provider).rstrip('/')}/api/chat"
        return f"{self._base_url(provider).rstrip('/')}/chat/completions"

    async def _remote_chat(
        self,
        messages: Sequence[dict[str, str]],
        *,
        provider: ModelProvider,
        temperature: float,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self._model_name(provider),
            "temperature": temperature,
            "messages": list(messages),
        }
        if response_format:
            payload["response_format"] = response_format

        async with httpx.AsyncClient(timeout=90) as client:
            try:
                response = await client.post(
                    self._url(provider),
                    headers=self._headers(provider),
                    json=payload,
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                self._raise_api_error(provider, exc)
            data = response.json()

        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Unexpected response from {self.provider_label(provider)} API.") from exc

    async def _ollama_chat(
        self,
        messages: Sequence[dict[str, str]],
        *,
        temperature: float,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self._model_name("ollama"),
            "messages": list(messages),
            "stream": False,
            "options": {"temperature": temperature},
        }
        if response_format and response_format.get("type") == "json_object":
            payload["format"] = "json"

        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                self._url("ollama"),
                headers=self._headers("ollama"),
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        content = data.get("message", {}).get("content")
        if isinstance(content, str):
            return content.strip()
        raise RuntimeError("Unexpected response from Ollama API.")

    async def _remote_stream_chat(
        self,
        messages: Sequence[dict[str, str]],
        *,
        provider: ModelProvider,
        temperature: float,
    ) -> AsyncIterator[str]:
        payload = {
            "model": self._model_name(provider),
            "temperature": temperature,
            "messages": list(messages),
            "stream": True,
        }

        async with httpx.AsyncClient(timeout=None) as client:
            try:
                async with client.stream(
                    "POST",
                    self._url(provider),
                    headers=self._headers(provider),
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk_payload = json.loads(data)
                            delta = chunk_payload["choices"][0]["delta"].get("content", "")
                        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                            continue
                        if delta:
                            yield delta
            except httpx.HTTPStatusError as exc:
                self._raise_api_error(provider, exc)

    async def _ollama_stream_chat(
        self,
        messages: Sequence[dict[str, str]],
        *,
        temperature: float,
    ) -> AsyncIterator[str]:
        payload = {
            "model": self._model_name("ollama"),
            "messages": list(messages),
            "stream": True,
            "options": {"temperature": temperature},
        }

        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                self._url("ollama"),
                headers=self._headers("ollama"),
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk_payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    delta = chunk_payload.get("message", {}).get("content", "")
                    if isinstance(delta, str) and delta:
                        yield delta
                    if chunk_payload.get("done"):
                        break

    async def chat(
        self,
        messages: Sequence[dict[str, str]],
        *,
        provider: str | None = None,
        temperature: float = 0.2,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        normalized_provider = self.normalize_provider(provider)
        if normalized_provider == "ollama":
            return await self._ollama_chat(
                messages,
                temperature=temperature,
                response_format=response_format,
            )
        return await self._remote_chat(
            messages,
            provider=normalized_provider,
            temperature=temperature,
            response_format=response_format,
        )

    async def json_chat(
        self,
        messages: Sequence[dict[str, str]],
        *,
        provider: str | None = None,
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        normalized_provider = self.normalize_provider(provider)
        content = await self.chat(
            messages,
            provider=normalized_provider,
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"{self.provider_label(normalized_provider)} did not return valid JSON.") from exc

    async def stream_chat(
        self,
        messages: Sequence[dict[str, str]],
        *,
        provider: str | None = None,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        normalized_provider = self.normalize_provider(provider)
        if normalized_provider == "ollama":
            async for delta in self._ollama_stream_chat(messages, temperature=temperature):
                yield delta
            return

        async for delta in self._remote_stream_chat(
            messages,
            provider=normalized_provider,
            temperature=temperature,
        ):
            yield delta

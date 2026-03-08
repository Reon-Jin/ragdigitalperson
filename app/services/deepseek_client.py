from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, Literal, Sequence

import httpx

from app.config import Settings


ModelProvider = Literal["deepseek", "qwen"]


class CompatibleLLMClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

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
        ]

    def normalize_provider(self, provider: str | None) -> ModelProvider:
        if provider == "qwen":
            return "qwen"
        return "deepseek"

    def is_configured(self, provider: str | None) -> bool:
        normalized = self.normalize_provider(provider)
        if normalized == "qwen":
            return bool(self.settings.qwen_api_key)
        return bool(self.settings.deepseek_api_key)

    def provider_label(self, provider: str | None) -> str:
        return "Qwen" if self.normalize_provider(provider) == "qwen" else "DeepSeek"

    def _headers(self, provider: ModelProvider) -> dict[str, str]:
        api_key = self.settings.qwen_api_key if provider == "qwen" else self.settings.deepseek_api_key
        if not api_key:
            raise RuntimeError(f"{self.provider_label(provider)} API key is not configured.")
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def _base_url(self, provider: ModelProvider) -> str:
        return self.settings.qwen_base_url if provider == "qwen" else self.settings.deepseek_base_url

    def _model_name(self, provider: ModelProvider) -> str:
        return self.settings.qwen_model if provider == "qwen" else self.settings.deepseek_model

    def _url(self, provider: ModelProvider) -> str:
        return f"{self._base_url(provider).rstrip('/')}/chat/completions"

    async def chat(
        self,
        messages: Sequence[dict[str, str]],
        *,
        provider: str | None = None,
        temperature: float = 0.2,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        normalized_provider = self.normalize_provider(provider)
        payload: dict[str, Any] = {
            "model": self._model_name(normalized_provider),
            "temperature": temperature,
            "messages": list(messages),
        }
        if response_format:
            payload["response_format"] = response_format

        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                self._url(normalized_provider),
                headers=self._headers(normalized_provider),
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Unexpected response from {self.provider_label(normalized_provider)} API.") from exc

    async def json_chat(
        self,
        messages: Sequence[dict[str, str]],
        *,
        provider: str | None = None,
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        content = await self.chat(
            messages,
            provider=provider,
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"{self.provider_label(provider)} did not return valid JSON.") from exc

    async def stream_chat(
        self,
        messages: Sequence[dict[str, str]],
        *,
        provider: str | None = None,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        normalized_provider = self.normalize_provider(provider)
        payload = {
            "model": self._model_name(normalized_provider),
            "temperature": temperature,
            "messages": list(messages),
            "stream": True,
        }

        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                self._url(normalized_provider),
                headers=self._headers(normalized_provider),
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

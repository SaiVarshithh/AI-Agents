from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.exceptions import LLMError, LLMProviderNotFoundError


class LLMClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        provider = self.settings.LLM_PROVIDER.strip().lower()
        if provider == "openai":
            return await self._openai_chat(system_prompt, user_prompt)
        if provider == "ollama":
            return await self._ollama_chat(system_prompt, user_prompt)
        raise LLMProviderNotFoundError(f"Unsupported LLM provider: {provider}")

    async def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        text = await self.complete(system_prompt=system_prompt, user_prompt=user_prompt)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(text[start : end + 1])
            raise LLMError("Model output is not valid JSON", detail=text[:300])

    async def _openai_chat(self, system_prompt: str, user_prompt: str) -> str:
        if not self.settings.OPENAI_API_KEY:
            raise LLMError("OPENAI_API_KEY is missing for OpenAI provider")
        payload = {
            "model": self.settings.OPENAI_MODEL,
            "temperature": self.settings.LLM_TEMPERATURE,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {"Authorization": f"Bearer {self.settings.OPENAI_API_KEY}"}
        url = f"{self.settings.OPENAI_BASE_URL.rstrip('/')}/chat/completions"
        async with httpx.AsyncClient(timeout=self.settings.LLM_TIMEOUT_SECONDS) as client:
            res = await client.post(url, headers=headers, json=payload)
            if res.status_code >= 400:
                raise LLMError("OpenAI request failed", detail=res.text[:400])
            data = res.json()
        return data["choices"][0]["message"]["content"].strip()

    async def _ollama_chat(self, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self.settings.OLLAMA_MODEL,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "options": {"temperature": self.settings.LLM_TEMPERATURE},
        }
        url = f"{self.settings.OLLAMA_BASE_URL.rstrip('/')}/api/chat"
        async with httpx.AsyncClient(timeout=self.settings.LLM_TIMEOUT_SECONDS) as client:
            res = await client.post(url, json=payload)
            if res.status_code >= 400:
                raise LLMError("Ollama request failed", detail=res.text[:400])
            data = res.json()
        return data["message"]["content"].strip()

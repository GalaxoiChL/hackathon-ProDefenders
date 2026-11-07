"""Local AI through Ollama (gemma3:4b). Every call has a deterministic fallback, so the tool
works offline / without Ollama, and the response says which one was used (`ai`: ollama | rules)."""
from __future__ import annotations

import json
import re
from typing import Callable

import httpx

from .config import OutreachSettings

Generate = Callable[[str], str | None]


class LLM:
    def __init__(self, settings: OutreachSettings, generate: Generate | None = None):
        self.s = settings
        self._generate = generate or self._ollama
        self._available: bool | None = None if settings.ai_enabled else False

    def _ollama(self, prompt: str) -> str | None:
        r = httpx.post(f"{self.s.ollama_url}/api/generate", timeout=90,
                       json={"model": self.s.ollama_model, "prompt": prompt, "stream": False,
                             "format": "json", "options": {"temperature": 0.4}})
        r.raise_for_status()
        return r.json().get("response")

    def json(self, prompt: str) -> dict | None:
        """Ask for a JSON object; None if the model is unavailable or answers garbage."""
        if self._available is False:
            return None
        try:
            raw = self._generate(prompt)
        except Exception:
            self._available = False          # don't wait for a dead server on every lead
            return None
        self._available = True
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", raw, re.S)
            if not m:
                return None
            try:
                data = json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
        return data if isinstance(data, dict) else None

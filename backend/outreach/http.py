"""Tiny synchronous HTTP wrapper so tests can swap the network out."""
from __future__ import annotations

import httpx

from .config import OutreachSettings


class Http:
    def __init__(self, settings: OutreachSettings):
        self.s = settings
        self._c: httpx.Client | None = None

    @property
    def _client(self) -> httpx.Client:
        if self._c is None:  # lazy: building the SSL context is slow and most requests never need it
            self._c = httpx.Client(timeout=self.s.http_timeout, follow_redirects=True,
                                   headers={"User-Agent": self.s.user_agent})
        return self._c

    def get_json(self, url: str, params: dict | None = None, headers: dict | None = None):
        r = self._client.get(url, params=params, headers=headers)
        r.raise_for_status()
        return r.json()

    def post_json(self, url: str, data: dict, timeout: float | None = None):
        r = self._client.post(url, data=data, timeout=timeout or self.s.http_timeout)
        r.raise_for_status()
        return r.json()

    def get_text(self, url: str, max_bytes: int = 1_500_000) -> tuple[str, str]:
        """(final_url, text); refuses non-HTML and huge pages."""
        with self._client.stream("GET", url) as r:
            r.raise_for_status()
            ctype = r.headers.get("content-type", "")
            if "html" not in ctype and "text/plain" not in ctype:
                raise ValueError(f"not html: {ctype}")
            chunks, size = [], 0
            for chunk in r.iter_bytes():
                chunks.append(chunk)
                size += len(chunk)
                if size > max_bytes:
                    break
            enc = r.encoding or "utf-8"
            return str(r.url), b"".join(chunks).decode(enc, errors="replace")

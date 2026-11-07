"""Settings read from the environment (and an optional `.env` at the repo root).

Every value has a demo-safe default, so `uvicorn backend.app:app` works with no configuration.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path) -> None:
    """Minimal `.env` loader (KEY=value lines); real environment variables win."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    root: Path = ROOT
    default_region: str = "RO"
    # Free IP geolocation, no key. {ip} is replaced with the viewer's IP.
    geo_url: str = "http://ip-api.com/json/{ip}?fields=status,countryCode"
    geo_enabled: bool = True
    geo_timeout: float = 1.5
    cors_origins: tuple[str, ...] = ("*",)
    python: str = sys.executable
    # dashboard assumptions (USD); can be overridden per request
    default_views: int = 10_000
    ai_cost_per_placement: float = 0.04   # image generation + local compute
    manual_hours_per_placement: float = 3.0
    editor_hourly_rate: float = 40.0
    extra: dict = field(default_factory=dict)

    @property
    def output_dir(self) -> Path:
        return self.root / "output"

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def assets_dir(self) -> Path:
        return self.root / "assets"

    @property
    def clips_dir(self) -> Path:
        return self.assets_dir / "clips"

    @property
    def frontend_dir(self) -> Path:
        return self.root / "frontend"

    @classmethod
    def from_env(cls, root: Path | None = None) -> "Settings":
        root = root or ROOT
        load_dotenv(root / ".env")
        env = os.environ
        origins = tuple(o.strip() for o in env.get("CORS_ORIGINS", "*").split(",") if o.strip())
        return cls(
            root=root,
            default_region=env.get("DEFAULT_REGION", "RO").upper(),
            geo_url=env.get("GEO_URL", cls.geo_url),
            geo_enabled=_bool(env.get("GEO_ENABLED"), True),
            geo_timeout=float(env.get("GEO_TIMEOUT", cls.geo_timeout)),
            cors_origins=origins or ("*",),
            python=env.get("PIPELINE_PYTHON", sys.executable),
        )

"""Pydantic models for the JSON contracts in CLAUDE.md.

They are permissive (`extra="allow"`): other modules can add fields without breaking the API.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Open(BaseModel):
    model_config = ConfigDict(extra="allow")


# ---- data/ads.json (task 4 -> task 2) ----
class Ad(_Open):
    id: str
    region: str
    brand: str
    category: str | None = None
    headline: str | None = None
    price: str | None = None
    colors: dict[str, str] = Field(default_factory=dict)
    product_image: str | None = None
    fits: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)


# ---- <clip>.surfaces.json (task 1) ----
class Surface(_Open):
    id: str
    type: str = "billboard"
    frame: int = 0
    corners: list[list[float]]
    aspect: float | None = None
    confidence: float | None = None

    @field_validator("corners")
    @classmethod
    def _four_points(cls, v: list[list[float]]) -> list[list[float]]:
        if len(v) != 4 or any(len(p) != 2 for p in v):
            raise ValueError("corners must be 4 [x, y] points (TL, TR, BR, BL)")
        return v


class Surfaces(_Open):
    clip: str
    surfaces: list[Surface] = Field(default_factory=list)


# ---- <clip>.scene.json (task 2 -> task 1) ----
class BrandSafety(_Open):
    safe: bool = True
    reasons: list[str] = Field(default_factory=list)


class Choice(_Open):
    ad_id: str
    reason: str | None = None


class Scene(_Open):
    clip: str
    location: str | None = None
    time_of_day: str | None = None
    weather: str | None = None
    mood: str | None = None
    brand_safety: BrandSafety = Field(default_factory=BrandSafety)
    choices: dict[str, Choice] = Field(default_factory=dict)


# ---- output/<clip>.manifest.json (task 1 -> task 3) ----
class ClipStats(_Open):
    """Optional block written by the backend job runner: what the engine reported."""
    frames: int | None = None
    lost_frames: int | None = None
    fps: float | None = None
    width: int | None = None
    height: int | None = None


class ManifestRegion(_Open):
    code: str
    label: str | None = None
    video: str
    ad_id: str | None = None
    reason: str | None = None


class Manifest(_Open):
    clip: str
    ai_view: str | None = None
    regions: list[ManifestRegion] = Field(default_factory=list)
    stats: ClipStats | None = None


# ---- job requests ----
class JobRequest(BaseModel):
    clip: str
    video: str | None = Field(None, description="default: assets/clips/<clip>.mp4")
    corners: str | None = Field(None, description="default: <clip>.surfaces.json, then assets/clips/<clip>.corners.json")
    ads: dict[str, str] | None = Field(None, description="region -> ad image; default: generated PNGs, then assets/ads")
    track: bool = True
    occlude: bool = True
    debug: bool = True
    max_frames: int = 0
    regions: list[str] | None = Field(None, description="pipeline/run.py: which countries (default: all with an ad)")

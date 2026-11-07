"""Reads the files other modules produce, with fallbacks so the demo never shows an empty page.

| What            | Primary source                    | Fallback                                         |
|-----------------|-----------------------------------|--------------------------------------------------|
| manifest        | output/<clip>.manifest.json       | built from output/<clip>_<xx>.mp4 files          |
| scene           | output/ or assets/clips/<clip>.scene.json | none (endpoint returns 404)              |
| surfaces        | output/ or assets/clips/<clip>.surfaces.json | assets/clips/<clip>.corners.json (manual) |
| ads             | data/ads.json                     | SAMPLE_ADS below (the example from CLAUDE.md)    |
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import ValidationError

from . import regions
from .config import Settings
from .models import Ad, Manifest, ManifestRegion, Scene, Surface, Surfaces

CLIP_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_REGION_FILE_RE = re.compile(r"^(?P<clip>.+)_(?P<code>[A-Za-z]{2})\.mp4$")

# Used until task 4 commits data/ads.json. Invented brands only.
SAMPLE_ADS: list[dict] = [
    {
        "id": "ro-pizza-bunicii", "region": "RO", "brand": "Pizza Bunicii", "category": "food",
        "headline": "Felia caldă, la tine în cartier", "price": "19 lei",
        "colors": {"bg": "#C81E23", "fg": "#FFFFFF", "accent": "#FFC800"},
        "product_image": "data/products/ro-pizza-bunicii.png",
        "fits": ["evening", "rain", "cold", "urban"], "avoid": ["violence", "accident", "sad"],
    },
    {
        "id": "us-burger-bros", "region": "US", "brand": "Burger Bros", "category": "food",
        "headline": "Stacked high. Priced low.", "price": "$4.99",
        "colors": {"bg": "#1D3557", "fg": "#FFFFFF", "accent": "#F4A261"},
        "product_image": "data/products/us-burger-bros.png",
        "fits": ["day", "urban", "busy"], "avoid": ["violence", "accident", "sad"],
    },
    {
        "id": "jp-sakura-ramen", "region": "JP", "brand": "Sakura Ramen", "category": "food",
        "headline": "一杯で、心まであたたかく", "price": "¥680",
        "colors": {"bg": "#FFFFFF", "fg": "#1A1A1A", "accent": "#E63946"},
        "product_image": "data/products/jp-sakura-ramen.png",
        "fits": ["evening", "rain", "cold", "urban"], "avoid": ["violence", "accident", "sad"],
    },
]


class NotFound(Exception):
    pass


class BadData(Exception):
    """A file exists but does not match its contract."""


def check_clip(clip: str) -> str:
    if not CLIP_RE.match(clip):
        raise NotFound(f"invalid clip name: {clip!r}")
    return clip


def url_for(rel_path: str | None) -> str | None:
    """Repo-relative path ('output/x.mp4') -> URL served by the app ('/output/x.mp4')."""
    if not rel_path:
        return None
    return "/" + rel_path.replace("\\", "/").lstrip("/")


class Store:
    def __init__(self, settings: Settings):
        self.s = settings

    # ---------- helpers ----------
    def rel(self, path: Path) -> str:
        return path.resolve().relative_to(self.s.root.resolve()).as_posix()

    def _read_json(self, path: Path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise BadData(f"{self.rel(path)}: invalid JSON ({e})") from e

    def _first_existing(self, *paths: Path) -> Path | None:
        return next((p for p in paths if p.is_file()), None)

    # ---------- clips ----------
    def list_clips(self) -> list[str]:
        names: set[str] = set()
        out = self.s.output_dir
        if out.is_dir():
            for p in out.glob("*.manifest.json"):
                names.add(p.name[: -len(".manifest.json")])
            for p in out.glob("*.mp4"):
                m = _REGION_FILE_RE.match(p.name)
                if m and not p.name.endswith(".tmp.mp4"):
                    names.add(m["clip"])
        return sorted(n for n in names if CLIP_RE.match(n))

    def manifest(self, clip: str) -> Manifest:
        check_clip(clip)
        path = self.s.output_dir / f"{clip}.manifest.json"
        if path.is_file():
            try:
                return Manifest.model_validate(self._read_json(path))
            except ValidationError as e:
                raise BadData(f"{self.rel(path)}: {e.errors()[0]['msg']}") from e
        return self._synthesize_manifest(clip)

    def _synthesize_manifest(self, clip: str) -> Manifest:
        out = self.s.output_dir
        files = sorted(out.glob(f"{clip}_*.mp4")) if out.is_dir() else []
        scene = self.scene_or_none(clip)
        regs = []
        for p in files:
            m = _REGION_FILE_RE.match(p.name)
            if not m or m["clip"] != clip or p.name.endswith(".tmp.mp4"):
                continue
            code = m["code"].upper()
            choice = scene.choices.get(code) if scene else None
            regs.append(ManifestRegion(
                code=code, label=regions.label(code), video=self.rel(p),
                ad_id=choice.ad_id if choice else None, reason=choice.reason if choice else None,
            ))
        if not regs:
            raise NotFound(f"no rendered videos for clip {clip!r} in output/")
        ai = out / f"{clip}_ai_view.mp4"
        return Manifest(clip=clip, ai_view=self.rel(ai) if ai.is_file() else None,
                        regions=regs, synthesized=True)

    # ---------- scene ----------
    def scene_or_none(self, clip: str) -> Scene | None:
        check_clip(clip)
        path = self._first_existing(self.s.output_dir / f"{clip}.scene.json",
                                    self.s.clips_dir / f"{clip}.scene.json")
        if not path:
            return None
        try:
            return Scene.model_validate(self._read_json(path))
        except ValidationError as e:
            raise BadData(f"{self.rel(path)}: {e.errors()[0]['msg']}") from e

    def scene(self, clip: str) -> Scene:
        sc = self.scene_or_none(clip)
        if sc is None:
            raise NotFound(f"no scene analysis for clip {clip!r} yet (task 2 writes <clip>.scene.json)")
        return sc

    # ---------- surfaces ----------
    def surfaces(self, clip: str) -> Surfaces:
        check_clip(clip)
        path = self._first_existing(self.s.output_dir / f"{clip}.surfaces.json",
                                    self.s.clips_dir / f"{clip}.surfaces.json")
        try:
            if path:
                return Surfaces.model_validate(self._read_json(path))
            manual = self.s.clips_dir / f"{clip}.corners.json"
            if manual.is_file():
                data = self._read_json(manual)
                surf = Surface(id="s1", type="billboard", frame=data.get("frame", 0),
                               corners=data["corners"], confidence=1.0, source="manual")
                return Surfaces(clip=clip, surfaces=[surf], source="manual")
        except (ValidationError, KeyError) as e:
            raise BadData(f"surfaces for {clip!r} do not match the contract: {e}") from e
        raise NotFound(f"no surfaces for clip {clip!r}")

    def surfaces_or_none(self, clip: str) -> Surfaces | None:
        try:
            return self.surfaces(clip)
        except NotFound:
            return None

    # ---------- ads ----------
    def ads(self) -> tuple[list[Ad], str]:
        path = self.s.data_dir / "ads.json"
        if path.is_file():
            data = self._read_json(path)
            try:
                return [Ad.model_validate(a) for a in data], "data/ads.json"
            except (ValidationError, TypeError) as e:
                raise BadData(f"data/ads.json does not match the contract: {e}") from e
        return [Ad.model_validate(a) for a in SAMPLE_ADS], "sample"

    def ad(self, ad_id: str) -> Ad:
        for a in self.ads()[0]:
            if a.id == ad_id:
                return a
        raise NotFound(f"no ad with id {ad_id!r}")

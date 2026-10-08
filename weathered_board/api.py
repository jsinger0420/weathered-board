"""Public API: build weathered boards from another add-on.

This is the only module other add-ons should import. Everything else in
the package (``core``, ``preset_store``, the operators) is internal and may
change between versions; this module keeps its names and meanings.

Finding it at runtime (extensions can't depend on each other)::

    import importlib
    import bpy

    def weathered_board_api():
        for name in bpy.context.preferences.addons.keys():
            if name.endswith(".weathered_board"):
                return importlib.import_module(name + ".api")
        return None

Coordinate convention: the board is centred on the origin, with its
length along X, width along Y and thickness along Z. Face names are
``top`` (+Z), ``bottom`` (-Z), ``front`` (-Y), ``back`` (+Y), ``end_a``
(-X) and ``end_b`` (+X). This will not change.

Versioning: ``API_VERSION`` is (major, minor). The minor number goes up
when features are added; the major number only for a breaking change,
which is avoided. Check ``api.API_VERSION[0] == 1`` before calling.

Nothing here creates Blender objects, changes the scene or needs a bpy
context. ``build_board`` works from plain Python, and the same arguments
always give the same mesh.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np

from .core import build
from .core.params import FACES, PRINTER_DEFAULTS, ParamError
from .core.presets import (
    BUILTIN_PRESETS, DEFAULT_VALUES, PRESET_KEYS, PresetError,
    from_json, get_builtin, params_from_values, to_json,
)

API_VERSION = (1, 0)

SEED_LIMIT = 2**31  # seeds are kept in 0 .. 2**31 - 1

__all__ = [
    "API_VERSION", "BoardError", "BoardMesh", "PresetInfo",
    "build_board", "get_preset_values", "list_presets",
]


class BoardError(ValueError):
    """The one exception the API raises, with a message fit for a panel."""


@dataclass(frozen=True)
class PresetInfo:
    """One preset in the menu: its name, tooltip and whether it is built in."""

    name: str
    description: str
    builtin: bool


@dataclass(frozen=True)
class BoardMesh:
    """A built board, in printed millimetres, centred on the origin.

    Length is along X, width along Y and thickness along Z. ``vertices``
    is (N, 3) float64; ``triangles`` is (M, 3) int32, wound outward, and
    the mesh is watertight. Both arrays are read-only. ``face_depth`` is
    the deepest cut on each face (keys as in ``FACES``), in printed mm.
    ``boost`` is the detail boost applied, and ``carve_depth_mm`` the
    printed carving depth after the boost and the quarter-thickness cap.
    """

    vertices: np.ndarray
    triangles: np.ndarray
    face_depth: dict[str, float]
    boost: float
    carve_depth_mm: float


def _saved_store():
    """The saved-preset module, or None when running without Blender.

    ``preset_store`` imports bpy, so it is only imported when needed.
    """
    try:
        from . import preset_store
    except ImportError:
        return None
    return preset_store


def list_presets() -> list[PresetInfo]:
    """Every preset: the built-in ones first, then the user's saved ones.

    Saved presets need Blender; from plain Python only the built-ins are
    listed.
    """
    out = [PresetInfo(p.name, p.description, True) for p in BUILTIN_PRESETS]
    store = _saved_store()
    if store is not None:
        out += [PresetInfo(name, "Saved preset", False)
                for name in store.saved_names() if not store.is_builtin(name)]
    return out


def get_preset_values(name: str) -> dict[str, Any]:
    """The full settings of a built-in or saved preset, keyed as PRESET_KEYS.

    Raises BoardError if there is no such preset or its file can't be read.
    """
    preset = get_builtin(name)
    if preset is not None:
        return preset.full_values()
    store = _saved_store()
    if store is None or name.casefold() not in {n.casefold() for n in store.saved_names()}:
        raise BoardError(f"No preset named '{name}'.")
    try:
        saved = store.load(name)
    except PresetError as err:
        raise BoardError(str(err)) from None
    out = {k: DEFAULT_VALUES[k] for k in PRESET_KEYS}
    out.update(saved)
    return out


def _checked_values(values: Mapping[str, Any]) -> dict[str, Any]:
    """Caller-supplied settings, checked the same way a preset file is."""
    unknown = sorted(str(k) for k in values if k not in PRESET_KEYS)
    if unknown:
        raise BoardError(f"Unknown setting(s): {', '.join(unknown)}.")
    try:
        return from_json(to_json(values))
    except (TypeError, ValueError) as err:  # PresetError, or not JSON-able
        raise BoardError(str(err)) from None


def _number(name: str, value: Any) -> float:
    """``value`` as a float, or BoardError naming the argument."""
    if isinstance(value, bool) or not isinstance(value, (int, float, np.number)):
        raise BoardError(f"{name} must be a number.")
    return float(value)


def build_board(
    *,
    preset: str | None = None,
    values: Mapping[str, Any] | None = None,
    length_mm: float,
    width_mm: float,
    thickness_mm: float,
    scale: float,
    printer: str = "RESIN",
    seed: int = 0,
    weather_bottom: bool | None = False,
    resolution: float | None = None,
    min_feature: float | None = None,
    detail_boost: float | None = None,
    auto_detail: bool | None = None,
) -> BoardMesh:
    """Build one weathered board and return its mesh in printed millimetres.

    The look comes from ``preset`` (a name from ``list_presets``), then
    ``values`` (settings keyed as PRESET_KEYS) on top of it; with neither,
    the defaults. ``length_mm``, ``width_mm`` and ``thickness_mm`` are
    full-size millimetres and always replace the preset's size. ``scale``
    is N in 1:N. ``printer`` is "RESIN" or "FDM" and sets the default
    ``resolution`` and ``min_feature`` (printed mm). ``seed`` is wrapped
    into 0 .. 2**31 - 1. ``weather_bottom`` is False by default so the
    bottom stays flat; None keeps the preset's choice. ``resolution``,
    ``min_feature``, ``detail_boost`` and ``auto_detail`` left as None use
    the printer's or the add-on's defaults.

    The board is centred on the origin with length on X, width on Y and
    thickness on Z. No Blender objects are created. Raises BoardError for
    an unknown preset or settings that can't make a board.
    """
    look: dict[str, Any] = (get_preset_values(preset) if preset is not None
                            else {k: DEFAULT_VALUES[k] for k in PRESET_KEYS})
    if values is not None:
        look.update(_checked_values(values))

    if printer not in PRINTER_DEFAULTS:
        raise BoardError(f"Printer must be one of {', '.join(PRINTER_DEFAULTS)}.")
    if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)):
        raise BoardError("Seed must be a whole number.")
    default_res, default_feature = PRINTER_DEFAULTS[printer]

    look.update(
        units="MM",
        length=_number("length_mm", length_mm),
        width=_number("width_mm", width_mm),
        thickness=_number("thickness_mm", thickness_mm),
    )
    if weather_bottom is not None:
        look["weather_bottom"] = bool(weather_bottom)
    settings = {
        **look,
        "scale_n": _number("scale", scale),
        "printer": printer,
        "seed": int(seed) % SEED_LIMIT,
        "resolution": default_res if resolution is None else _number("resolution", resolution),
        "min_feature": (default_feature if min_feature is None
                        else _number("min_feature", min_feature)),
        "detail_boost": (DEFAULT_VALUES["detail_boost"] if detail_boost is None
                         else _number("detail_boost", detail_boost)),
        "auto_detail": DEFAULT_VALUES["auto_detail"] if auto_detail is None else bool(auto_detail),
    }

    params = params_from_values(settings)
    try:
        result = build(params)
    except ParamError as err:
        raise BoardError(str(err)) from None

    vertices = np.array(result.vertices, dtype=np.float64)
    triangles = np.array(result.triangles, dtype=np.int32)
    vertices.flags.writeable = False
    triangles.flags.writeable = False
    return BoardMesh(
        vertices=vertices,
        triangles=triangles,
        face_depth={f: float(result.face_depth.get(f, 0.0)) for f in FACES},
        boost=float(params.boost()),
        carve_depth_mm=float(params.carve_depth() / params.scale),
    )

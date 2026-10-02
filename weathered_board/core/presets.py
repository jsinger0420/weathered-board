"""Presets: named sets of board settings, built in or saved by the user.

A preset is a dict of setting values keyed by the Blender property names
in properties.py (``depth``, ``round_top_front``, ``weather_end_a`` ...).
It holds the board's look (faces, edge rounding and weathering) and its
full-size dimensions. It never holds the scale, printer, mesh or seed
settings, so a preset looks the same at any scale and on any printer, and
the dimensions can be left out when it is applied (Presets Set Size).

Kept free of bpy, so the built-in presets can be built and checked by the
core tests. ``params_from_values`` is also what ``WBOARD_Settings.to_params``
uses, so a preset and the panel always mean the same thing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from .params import EDGES, FACES, BoardParams, to_mm

SIZE_KEYS = ("units", "length", "width", "thickness")
LOOK_KEYS = (
    tuple(f"weather_{f}" for f in FACES)
    + tuple(f"round_{e}" for e in EDGES)
    + (
        "depth", "edge_margin", "patchiness", "checks",
        "ring_spacing_min", "ring_spacing_max", "ridge_sharpness", "grain_waviness",
        "knots_min", "knots_max",
        "end_spacing", "end_center", "end_wobble", "use_end_depth", "end_depth",
    )
)
PRESET_KEYS = SIZE_KEYS + LOOK_KEYS

# Default of every setting that becomes part of BoardParams, matching the
# defaults in properties.py (a Blender test checks they agree).
DEFAULT_VALUES: dict[str, Any] = {
    "units": "IN", "length": 96.0, "width": 5.5, "thickness": 1.5, "scale_n": 48.0,
    **{f"weather_{f}": f != "bottom" for f in FACES},
    **{f"round_{e}": 0.15 for e in EDGES},
    "depth": 3.0, "edge_margin": 0.0, "patchiness": 0.5, "checks": 0.3,
    "ring_spacing_min": 3.0, "ring_spacing_max": 6.0,
    "ridge_sharpness": 0.6, "grain_waviness": 0.4,
    "knots_min": 0, "knots_max": 2,
    "end_spacing": 4.0, "end_center": "RANDOM", "end_wobble": 0.1,
    "use_end_depth": False, "end_depth": 3.0,
    "printer": "RESIN", "resolution": 0.05, "min_feature": 0.1,
    "detail_boost": 1.0, "auto_detail": True, "seed": 0,
}

CHOICES = {
    "units": ("IN", "MM"),
    "end_center": ("RANDOM", "TOP", "BOTTOM", "FRONT", "BACK"),
    "printer": ("RESIN", "FDM"),
}

FILE_VERSION = 1


class PresetError(ValueError):
    """Raised when a saved preset file can't be read."""


@dataclass(frozen=True)
class Preset:
    """One built-in look: its menu name, tooltip and setting values.

    ``values`` only needs the settings that differ from DEFAULT_VALUES;
    ``full_values`` fills in the rest.
    """

    name: str
    description: str
    values: Mapping[str, Any]

    def full_values(self) -> dict[str, Any]:
        """Every preset setting: this preset's values over the defaults."""
        out = {k: DEFAULT_VALUES[k] for k in PRESET_KEYS}
        out.update(self.values)
        return out


def _rounding(long: float, ends: float) -> dict[str, float]:
    """Rounding for the 4 long edges and the 8 end edges."""
    out = {}
    for edge in EDGES:
        out[f"round_{edge}"] = ends if edge.startswith(("a_", "b_")) else long
    return out


BUILTIN_PRESETS: tuple[Preset, ...] = (
    Preset(
        "Barn Siding",
        "Rough-sawn 1x12 siding, 10 ft, after decades in the sun: deep, crisp grain, "
        "wide checks, a few knots and hard-worn ends. The back stays flat",
        {
            "units": "IN", "length": 120.0, "width": 11.5, "thickness": 0.875,
            **_rounding(long=0.25, ends=0.3),
            "depth": 4.5, "patchiness": 0.6, "checks": 0.6,
            "ring_spacing_min": 3.0, "ring_spacing_max": 7.0,
            "ridge_sharpness": 0.8, "grain_waviness": 0.5,
            "knots_min": 1, "knots_max": 3,
            "end_spacing": 4.0, "end_wobble": 0.2,
            "use_end_depth": True, "end_depth": 5.0,
        },
    ),
    Preset(
        "Dock Plank",
        "2x6 decking, 12 ft, worn by feet and water: well-rounded top edges, softer "
        "rolling grain, end checks and deeply eroded end grain",
        {
            "units": "IN", "length": 144.0, "width": 5.5, "thickness": 1.5,
            "round_top_front": 0.5, "round_top_back": 0.5,
            "round_bottom_front": 0.2, "round_bottom_back": 0.2,
            **{f"round_{e}": 0.35 for e in EDGES if e.startswith(("a_", "b_"))},
            "depth": 4.0, "patchiness": 0.4, "checks": 0.5,
            "ring_spacing_min": 4.0, "ring_spacing_max": 8.0,
            "ridge_sharpness": 0.4, "grain_waviness": 0.3,
            "knots_min": 0, "knots_max": 2,
            "end_spacing": 5.0, "end_wobble": 0.15,
            "use_end_depth": True, "end_depth": 6.0,
        },
    ),
    Preset(
        "Fence Board",
        "5/8 in cedar fence picket, 6 ft: fine, tight grain, near-square edges, "
        "a few knots and light, patchy wear",
        {
            "units": "IN", "length": 72.0, "width": 5.5, "thickness": 0.625,
            **_rounding(long=0.1, ends=0.1),
            "depth": 2.5, "patchiness": 0.5, "checks": 0.35,
            "ring_spacing_min": 2.0, "ring_spacing_max": 4.0,
            "ridge_sharpness": 0.6, "grain_waviness": 0.35,
            "knots_min": 1, "knots_max": 3,
            "end_spacing": 3.0, "end_wobble": 0.1,
            "use_end_depth": False, "end_depth": 2.5,
        },
    ),
)


def get_builtin(name: str) -> Preset | None:
    """The built-in preset with this name, or None."""
    for preset in BUILTIN_PRESETS:
        if preset.name == name:
            return preset
    return None


def params_from_values(values: Mapping[str, Any]) -> BoardParams:
    """Turn setting values, keyed by property name, into BoardParams.

    Missing settings take their DEFAULT_VALUES. Length, width and thickness
    are in ``units``; everything else is already in core units.
    """
    v = {**DEFAULT_VALUES, **values}
    mm = lambda x: to_mm(x, v["units"])  # noqa: E731
    return BoardParams(
        length=mm(v["length"]),
        width=mm(v["width"]),
        thickness=mm(v["thickness"]),
        scale=v["scale_n"],
        faces={f: bool(v[f"weather_{f}"]) for f in FACES},
        edge_round={e: v[f"round_{e}"] for e in EDGES},
        depth=v["depth"],
        edge_margin=v["edge_margin"],
        ring_spacing=(v["ring_spacing_min"], v["ring_spacing_max"]),
        ridge_sharpness=v["ridge_sharpness"],
        grain_waviness=v["grain_waviness"],
        end_spacing=v["end_spacing"],
        end_center=v["end_center"],
        end_wobble=v["end_wobble"],
        end_depth=v["end_depth"] if v["use_end_depth"] else None,
        knots=(v["knots_min"], max(v["knots_min"], v["knots_max"])),
        checks=v["checks"],
        patchiness=v["patchiness"],
        printer=v["printer"],
        resolution=v["resolution"],
        min_feature=v["min_feature"],
        detail_boost=v["detail_boost"],
        auto_detail=bool(v["auto_detail"]),
        seed=v["seed"],
    )


def to_json(values: Mapping[str, Any]) -> str:
    """Write the preset settings from ``values`` as the text of a preset file."""
    data = {"version": FILE_VERSION, "values": {k: values[k] for k in PRESET_KEYS if k in values}}
    return json.dumps(data, indent=2)


def from_json(text: str) -> dict[str, Any]:
    """Read a preset file's text back into setting values.

    Settings this version doesn't know (from a newer add-on) are skipped.
    Raises PresetError for a file that isn't a preset or has a value of
    the wrong kind.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError as err:
        raise PresetError(f"Not a preset file: {err}") from None
    if not isinstance(data, dict) or not isinstance(data.get("values"), dict):
        raise PresetError("Not a preset file: no settings in it.")
    out: dict[str, Any] = {}
    for key, value in data["values"].items():
        if key not in PRESET_KEYS:
            continue
        default = DEFAULT_VALUES[key]
        if isinstance(default, bool):
            ok = isinstance(value, bool)
        elif isinstance(default, int):
            ok = isinstance(value, int) and not isinstance(value, bool)
        elif isinstance(default, float):
            ok = isinstance(value, (int, float)) and not isinstance(value, bool)
            value = float(value) if ok else value
        else:
            ok = isinstance(value, str) and value in CHOICES.get(key, (value,))
        if not ok:
            raise PresetError(f"Setting '{key}' has an unusable value: {value!r}.")
        out[key] = value
    return out

"""Built-in presets and preset files (build plan step 7)."""

import json

import pytest

from core import build, check
from core.params import EDGES, FACES
from core.presets import (
    BUILTIN_PRESETS, DEFAULT_VALUES, PRESET_KEYS, SIZE_KEYS, PresetError,
    from_json, get_builtin, params_from_values, to_json,
)
from core.printcheck import ERROR, WARNING


def preset_params(preset, scale=48.0, **extra):
    """BoardParams for a built-in preset at 1:``scale``, with overrides."""
    values = preset.full_values()
    values.update(scale_n=scale, **extra)
    return params_from_values(values)


def test_presets_only_use_known_settings():
    """Every value in a built-in preset is a preset setting."""
    for preset in BUILTIN_PRESETS:
        assert set(preset.values) <= set(PRESET_KEYS), preset.name


def test_presets_hold_no_scale_printer_or_seed():
    """Presets look the same at any scale, on any printer, with any seed."""
    for key in ("scale_n", "printer", "resolution", "min_feature", "seed", "detail_boost"):
        assert key not in PRESET_KEYS


def test_full_values_cover_every_preset_setting():
    """full_values fills in every preset setting, defaults where not given."""
    for preset in BUILTIN_PRESETS:
        assert set(preset.full_values()) == set(PRESET_KEYS)


def test_preset_names_are_unique():
    """No two built-in presets share a name, and each can be looked up."""
    names = [p.name for p in BUILTIN_PRESETS]
    assert len(set(names)) == len(names)
    assert {"Barn Siding", "Dock Plank", "Fence Board"} <= set(names)
    for name in names:
        assert get_builtin(name).name == name
    assert get_builtin("No Such Look") is None


def test_defaults_match_board_params():
    """params_from_values with no values gives a default board's settings."""
    p = params_from_values({})
    assert p.depth == 3.0 and p.ring_spacing == (3.0, 6.0)
    assert p.faces == {f: f != "bottom" for f in FACES}
    assert p.edge_round == {e: 0.15 for e in EDGES}
    assert p.length == pytest.approx(96 * 25.4)


def test_end_depth_only_when_switched_on():
    """end_depth reaches the core only with use_end_depth on."""
    assert params_from_values({"end_depth": 5.0}).end_depth is None
    assert params_from_values({"end_depth": 5.0, "use_end_depth": True}).end_depth == 5.0


@pytest.mark.parametrize("preset", BUILTIN_PRESETS, ids=lambda p: p.name)
def test_presets_are_valid(preset):
    """Each built-in preset passes validation at common scales."""
    for scale in (1, 24, 48, 87):
        preset_params(preset, scale).validate()


@pytest.mark.parametrize("preset", BUILTIN_PRESETS, ids=lambda p: p.name)
def test_presets_print_at_1_48(preset):
    """Each built-in preset builds and passes every check at 1:48.

    A 2 ft length and a coarser mesh keep the test quick; the look
    settings are the preset's own.
    """
    params = preset_params(preset, 48, length=24.0, resolution=0.1)
    findings = check(params)
    assert not [f for f in findings if f.level in (ERROR, WARNING)], findings


def test_presets_differ_from_each_other():
    """The built-in looks really are different boards."""
    looks = [{k: v for k, v in p.full_values().items() if k not in SIZE_KEYS}
             for p in BUILTIN_PRESETS]
    for i in range(len(looks)):
        for j in range(i + 1, len(looks)):
            assert looks[i] != looks[j]


def test_dock_plank_tops_are_worn_round():
    """The dock plank's walked-on top edges are rounder than its bottom edges."""
    v = get_builtin("Dock Plank").full_values()
    assert v["round_top_front"] > v["round_bottom_front"]


def test_json_round_trip():
    """A preset written to a file reads back to the same values."""
    values = get_builtin("Barn Siding").full_values()
    assert from_json(to_json(values)) == values


def test_json_only_writes_preset_settings():
    """Scale, printer and seed are never written to a preset file."""
    values = {**DEFAULT_VALUES, "seed": 1234, "scale_n": 87.0}
    data = json.loads(to_json(values))
    assert set(data["values"]) == set(PRESET_KEYS)


def test_json_skips_unknown_settings():
    """Settings from a newer version of the add-on are skipped, not an error."""
    text = json.dumps({"version": 2, "values": {"depth": 2, "sparkle": 0.5}})
    assert from_json(text) == {"depth": 2.0}


@pytest.mark.parametrize("text", [
    "not json",
    "[]",
    json.dumps({"version": 1}),
    json.dumps({"values": {"depth": "deep"}}),
    json.dumps({"values": {"knots_min": 1.5}}),
    json.dumps({"values": {"weather_top": 1}}),
    json.dumps({"values": {"end_center": "MIDDLE"}}),
    json.dumps({"values": {"units": "FT"}}),
])
def test_json_rejects_bad_files(text):
    """Files that aren't presets, or have values of the wrong kind, are refused."""
    with pytest.raises(PresetError):
        from_json(text)

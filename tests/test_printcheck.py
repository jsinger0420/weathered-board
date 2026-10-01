"""Printability checks (build plan step 6)."""

import numpy as np
import pytest

from core import build, check
from core import printcheck
from core.params import BoardParams, FACES
from core.printcheck import ERROR, INFO, OK, WARNING, is_watertight


def one_by_six(scale, **kw):
    # 1x6, 4 ft, coarse enough to be quick.
    base = dict(length=1219.2, width=139.7, thickness=19.05, scale=scale, resolution=0.1)
    base.update(kw)
    return BoardParams(**base)


def by_title(findings):
    return {f.title: f for f in findings}


def test_watertight_detects_holes():
    r = build(one_by_six(48))
    assert is_watertight(r.triangles)
    assert not is_watertight(r.triangles[1:])  # one triangle removed


def test_default_board_at_1_48_passes():
    findings = check(one_by_six(48))
    assert not [f for f in findings if f.level in (ERROR, WARNING)], findings
    titles = by_title(findings)
    assert "Ring detail" in titles and "Wall thickness" in titles and "Flat base" in titles


def test_face_depths_are_reported():
    r = build(one_by_six(48))
    assert set(r.face_depth) == set(FACES)
    # Not weathered by default; only the edge it shares with weathered
    # faces moves, by a hair, where their depth eases off.
    assert r.face_depth["bottom"] < 0.001
    assert r.face_depth["top"] > 0.0


def test_rings_too_fine_without_auto_boost_suggests_a_boost():
    p = one_by_six(48, auto_detail=False)
    f = by_title(check(p))["Rings too fine for the mesh"]
    assert f.level == ERROR
    assert f"{p.needed_boost():.1f}" in f.detail


def test_thin_board_at_small_scale_fails_wall_check():
    # A 3/4 in board at 1:87 is only 0.22 mm thick.
    f = by_title(check(one_by_six(87)))
    assert f["Wall too thin"].level == ERROR


def test_weathered_bottom_needs_supports():
    p = one_by_six(48, faces={f: True for f in FACES})
    assert by_title(check(p))["Bottom is weathered"].level == INFO


def test_heavy_mesh_warning(monkeypatch):
    monkeypatch.setattr(printcheck, "MAX_TRIANGLES", 1000)
    assert by_title(check(one_by_six(48)))["Heavy mesh"].level == WARNING


def test_shallow_carving_warning():
    p = one_by_six(48, depth=0.05, auto_detail=True)
    f = by_title(check(p))
    assert "Carving very shallow" in f

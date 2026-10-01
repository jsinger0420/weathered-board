"""Ring patterns: noise, the virtual log, end semicircles and the preview
(build plan step 3)."""

import math

import numpy as np
import pytest

from core import build
from core.ends import END_EDGES, EndRings
from core.geometry import FACE_NAMES, rounded_box
from core.grain import VirtualLog
from core.noise import Noise
from core.params import BoardParams
from core.patterns import UNSELECTED, board_patterns, latewood, preview_colors
from core.rng import streams


def params(**kw):
    base = dict(length=600.0, width=139.7, thickness=19.05, scale=1.0, resolution=2.0, seed=11,
                auto_detail=False)
    base.update(kw)
    return BoardParams(**base)


# --------------------------------------------------------------------------
# Noise and random streams
# --------------------------------------------------------------------------

def test_noise_is_repeatable_and_seeded():
    pts = np.random.default_rng(0).uniform(-50, 50, size=(1000, 3))
    a = Noise(np.random.default_rng(5))(pts)
    b = Noise(np.random.default_rng(5))(pts)
    c = Noise(np.random.default_rng(6))(pts)
    assert np.array_equal(a, b)
    assert not np.allclose(a, c)


def test_noise_is_smooth_and_bounded():
    n = Noise(np.random.default_rng(1))
    for axis in range(3):
        p = np.tile([0.37, 0.52, 0.81], (4001, 1))
        p[:, axis] = np.linspace(0, 8, 4001)
        v = n(p)
        assert np.abs(v).max() <= 1.2
        assert np.abs(np.diff(v)).max() < 0.01  # step 0.002: no jumps
    f = n.fbm(np.random.default_rng(2).uniform(-20, 20, size=(5000, 3)), octaves=4)
    assert np.abs(f).max() <= 1.2 and f.std() > 0.05


def test_random_streams_are_independent_and_repeatable():
    a, b = streams(123), streams(123)
    assert a["grain"].random() == b["grain"].random()
    # Drawing more from one stream never shifts another.
    c = streams(123)
    c["ends"].random(size=1000)
    assert c["grain"].random() == streams(123)["grain"].random()


# --------------------------------------------------------------------------
# Virtual log (long faces)
# --------------------------------------------------------------------------

def make_log(p):
    return VirtualLog(p, streams(p.seed)["grain"])


@pytest.mark.parametrize("seed", range(30))
def test_pith_is_outside_the_board_and_barely_tilted(seed):
    p = params(seed=seed)
    log = make_log(p)
    hy, hz = 0.5 * p.width, 0.5 * p.thickness
    y, z = log.pith_point[1], log.pith_point[2]
    assert abs(y) > hy or abs(z) > hz
    tilt = math.degrees(math.acos(log.pith_dir[0]))
    assert tilt <= 2.0 * math.sqrt(2) + 1e-9


def test_most_boards_are_flat_sawn():
    # Pith behind the top or bottom face, giving arches on the wide face.
    behind_wide_face = 0
    for seed in range(300):
        log = make_log(params(seed=seed))
        behind_wide_face += abs(math.sin(log.angle)) > abs(math.cos(log.angle))
    assert behind_wide_face / 300 > 0.6


def test_even_rings_when_spacing_is_fixed():
    p = params(ring_spacing=(4.0, 4.0), grain_waviness=0.0)
    log = make_log(p)
    r = np.linspace(50, 400, 200)
    assert np.allclose(log.ring_count(r + 4.0) - log.ring_count(r), 1.0, atol=1e-9)


def test_ring_widths_stay_within_the_range():
    p = params(ring_spacing=(3.0, 6.0))
    log = make_log(p)
    r = np.linspace(10, 500, 2000)
    rings_per_mm = np.gradient(log.ring_count(r), r)
    assert rings_per_mm.max() <= 1 / 3.0 + 1e-6
    assert rings_per_mm.min() >= 1 / 6.0 - 1e-6


def test_detail_boost_widens_the_rings():
    plain = make_log(params(ring_spacing=(4.0, 4.0), grain_waviness=0.0))
    boosted = make_log(params(ring_spacing=(4.0, 4.0), grain_waviness=0.0, detail_boost=2.0))
    r = np.linspace(50, 300, 50)
    assert np.allclose(boosted.ring_count(r + 8.0) - boosted.ring_count(r), 1.0, atol=1e-9)
    assert plain.spacing == (4.0, 4.0) and boosted.spacing == (8.0, 8.0)


def test_grain_phase_is_repeatable_and_varies_by_seed():
    p = params()
    mesh = rounded_box(p)
    a = make_log(p).phase(mesh.vertices)
    b = make_log(p).phase(mesh.vertices)
    c = make_log(params(seed=12)).phase(mesh.vertices)
    assert np.array_equal(a, b)
    assert ((0 <= a) & (a < 1)).all()
    assert np.mean(np.abs(a - c)) > 0.1


def test_grain_runs_along_the_board():
    # Phase changes far more slowly along the length than across it.
    p = params(seed=3)
    log = make_log(p)
    x = np.linspace(-200, 200, 401)
    along = np.stack([x, np.zeros_like(x), np.full_like(x, p.thickness / 2)], 1)
    y = np.linspace(-60, 60, 401)
    across = np.stack([np.zeros_like(y), y, np.full_like(y, p.thickness / 2)], 1)
    rings_along = np.abs(np.diff(log.ring_count(log.radius(along)))).sum() / 400
    rings_across = np.abs(np.diff(log.ring_count(log.radius(across)))).sum() / 120
    assert rings_across > 3 * rings_along


# --------------------------------------------------------------------------
# End semicircles
# --------------------------------------------------------------------------

def make_ends(p):
    return EndRings(p, streams(p.seed)["ends"])


@pytest.mark.parametrize("seed", range(20))
def test_end_centres_sit_on_an_edge_in_its_middle_half(seed):
    p = params(seed=seed)
    hy, hz = 0.5 * p.width, 0.5 * p.thickness
    for c in make_ends(p).centres.values():
        assert c.edge in END_EDGES
        if c.edge in ("TOP", "BOTTOM"):
            assert c.z == (hz if c.edge == "TOP" else -hz)
            assert abs(c.y) <= 0.5 * hy
        else:
            assert c.y == (-hy if c.edge == "FRONT" else hy)
            assert abs(c.z) <= 0.5 * hz


@pytest.mark.parametrize("edge", END_EDGES)
def test_fixed_end_centre_edge(edge):
    p = params(end_center=edge)
    assert all(c.edge == edge for c in make_ends(p).centres.values())


def test_rings_are_evenly_spaced_without_wobble():
    p = params(end_spacing=4.0, end_wobble=0.0)
    ends = make_ends(p)
    pts = np.random.default_rng(0).uniform(-1, 1, size=(2000, 3)) * [300, 70, 9.5]
    expected = np.mod(ends.distance(pts) / 4.0, 1.0)
    assert np.allclose(ends.phase(pts), expected)


def test_the_two_ends_differ():
    differ = sum(
        (lambda c: (c["end_a"].y, c["end_a"].z) != (c["end_b"].y, c["end_b"].z))(make_ends(params(seed=s)).centres)
        for s in range(20)
    )
    assert differ == 20


def test_wobble_stays_small():
    p = params(end_wobble=1.0)
    ends = make_ends(p)
    pts = np.random.default_rng(1).uniform(-1, 1, size=(2000, 3)) * [300, 70, 9.5]
    clean = ends.distance(pts) / ends.spacing
    wobbled = clean + 0.5 * ends.noise.fbm(pts / (1.5 * ends.spacing), octaves=2)
    assert np.abs(wobbled - clean).max() <= 0.6  # at most about half a ring


# --------------------------------------------------------------------------
# Patterns on the board and the colour preview
# --------------------------------------------------------------------------

def test_end_settings_do_not_change_the_grain():
    mesh = rounded_box(params())
    a = board_patterns(params(), mesh)
    b = board_patterns(params(end_spacing=9.0, end_center="TOP", end_wobble=0.7), mesh)
    assert np.array_equal(a.long_phase, b.long_phase)
    assert not np.array_equal(a.end_phase, b.end_phase)


def test_latewood_band():
    assert latewood(np.array([0.0, 0.5, 0.7]))[...].max() == 0.0
    assert latewood(np.array([0.95, 0.99])).min() == 1.0


def test_preview_greys_out_unselected_faces():
    p = params()
    p.faces = {f: f != "top" for f in FACE_NAMES}
    mesh = rounded_box(p)
    colors = preview_colors(p, mesh, board_patterns(p, mesh))
    top = mesh.face_weights[:, FACE_NAMES.index("top")] == 1.0
    assert np.allclose(colors[top], UNSELECTED)
    front = mesh.face_weights[:, FACE_NAMES.index("front")] == 1.0
    assert not np.allclose(colors[front], UNSELECTED)


def test_preview_shows_both_ring_patterns():
    p = params()
    p.faces = {f: True for f in FACE_NAMES}
    mesh = rounded_box(p)
    colors = preview_colors(p, mesh, board_patterns(p, mesh))
    for face in ("top", "end_a"):
        on = mesh.face_weights[:, FACE_NAMES.index(face)] == 1.0
        shade = colors[on, 0]
        assert shade.max() - shade.min() > 0.3, f"no rings visible on {face}"


def test_build_returns_a_colour_per_vertex():
    r = build(params(scale=48.0, resolution=0.1))
    assert r.preview.shape == r.vertices.shape
    assert (r.preview >= 0).all() and (r.preview <= 1).all()

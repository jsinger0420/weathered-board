import pytest

from core.params import EDGES, BoardParams, ParamError, to_mm


def board(**kw):
    # A nominal 1x6 board: 0.75 x 5.5 x 96 in, in mm.
    base = dict(length=to_mm(96, "IN"), width=to_mm(5.5, "IN"), thickness=to_mm(0.75, "IN"))
    base.update(kw)
    return BoardParams(**base)


def test_defaults_are_valid():
    board().validate()


def test_twelve_edges():
    assert len(EDGES) == 12


def test_long_edge_max_radius_is_half_thickness():
    p = board()
    assert p.max_radius("top_front") == pytest.approx(p.thickness / 2)


def test_end_edge_across_width_limited_by_thickness():
    p = board()
    # a_top joins end_a (X) and top (Z): cross-section is X by Z.
    assert p.max_radius("a_top") == pytest.approx(p.thickness / 2)


def test_edge_radius_scales_with_slider():
    p = board()
    p.edge_round["top_front"] = 1.0
    assert p.edge_radius("top_front") == pytest.approx(p.max_radius("top_front"))


def test_depth_limit():
    p = board(depth=10.0)  # thickness is 19.05 mm, limit is ~4.76 mm
    with pytest.raises(ParamError):
        p.validate()


def test_rounding_out_of_range():
    p = board()
    p.edge_round["b_back"] = 1.5
    with pytest.raises(ParamError):
        p.validate()


def test_bottom_not_weathered_by_default():
    assert board().faces["bottom"] is False


# --------------------------------------------------------------------------
# Detail boost
# --------------------------------------------------------------------------

def test_auto_boost_makes_rings_printable_at_small_scales():
    # 1x6 at 1:48 on a resin printer: true 3 mm rings would print at
    # 0.06 mm, finer than 4 mesh vertices (0.2 mm) can carve.
    p = board(scale=48.0)
    assert p.needed_boost() == pytest.approx(0.2 * 48 / 3.0)
    assert p.boost() == pytest.approx(3.2)


def test_auto_boost_is_not_needed_at_large_scales():
    assert board(scale=1.0).boost() == 1.0


def test_manual_boost_when_auto_is_off():
    p = board(scale=48.0, auto_detail=False, detail_boost=1.5)
    assert p.boost() == 1.5


def test_manual_boost_above_auto_wins():
    assert board(scale=48.0, detail_boost=5.0).boost() == 5.0


def test_boosted_depth_never_passes_a_quarter_of_the_thickness():
    p = board(scale=48.0, depth=3.0)  # 3 mm x 3.2 = 9.6 mm, more than 19.05 / 4
    assert p.carve_depth() == pytest.approx(p.thickness / 4)
    q = board(scale=1.0, depth=3.0, end_depth=1.0)
    assert q.carve_depth() == 3.0 and q.carve_depth(end=True) == 1.0

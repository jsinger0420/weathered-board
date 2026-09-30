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

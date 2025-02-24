#!/usr/bin/env python3

##
# Assumptions:
# - units in integer micrometers (avoid FP for now, but accommodate half mms)
#

import typing


class Bit(typing.NamedTuple):
    name: str
    key: str
    dx: int
    dy: int
    # dz: int


mm = 1000
µm = 1

WHOLE_BRICK = Bit("whole brick", key="W", dx=210 * mm, dy=50 * mm)
HALF_BRICK = Bit("half brick", key="H", dx=100 * mm, dy=50 * mm)
HEAD_JOINT = Bit("head joint", key="|", dx=10 * mm, dy=50 * mm)
BED_JOINT = Bit("bed joint", key="_", dx=1 * mm, dy=12500 * µm)

bits = [WHOLE_BRICK, HALF_BRICK, HEAD_JOINT, BED_JOINT]
bits_by_key = {b.key: b for b in bits}
bit_keys = list(bits_by_key.keys())
row_bit_keys = [WHOLE_BRICK.key, HALF_BRICK.key, HEAD_JOINT.key]


WALL = Bit("wall", key="", dx=2300 * mm, dy=2000 * mm)

##
# util functions -- don't be picky about classes etc here
#


def join_row(row: str) -> str:
    "turn row of bricks into row of bricks with head joints"
    return HEAD_JOINT.key.join(row)


def row_width(row: str) -> int:
    "calculate row width, including head joints"
    return sum((bits_by_key[key].dx for key in join_row(row)))


def rows_height(row_count: int) -> int:
    return row_count * (WHOLE_BRICK.dy + BED_JOINT.dy)


class Layout:
    """Represent brick grid, nominally by rows. Row 0 is lowest, with all bricks having same height,
    and ordered from left-to-right (and thus increasing X).

    Does some basic checking (total width) and normalizing.

    Head and Bed joints are implied and not explicitly tracked, but are included in calculations.
    """

    def __init__(self, *, rows: typing.Iterable[str]):
        """takes a sequence of rows, each row rep'd as string of half and whole bricks, e.g.
        "HWWWWH", which would represent a row beginning with a single half brick, then four
        consecutive whole bricks, and ending with a half."""
        grid = []
        layout_width: int = -1

        for i, row in enumerate(rows):
            for key in row:
                assert key in row_bit_keys, "Got invalid key"
            row_normalized = row.replace(HEAD_JOINT.key, "")
            grid.append(row_normalized)
            width = row_width(row_normalized)
            if i == 0:
                layout_width = width
            else:
                assert layout_width == width, (
                    f"Got layout != row width: {layout_width} != {row_width}"
                )

    @classmethod
    def rows_from_stretcher_bond(cls, *, width: int, height: int) -> list[str]:
        # XXX: Temporarily hard code the layout
        assert width == WALL.dx, "invalid width, only fixed WALL"
        assert height == WALL.dy, "invalid height, only fixed WALL"

        # NOTE: - order is bottom-to-top, reverse of how we'll visualize it!
        wall_layout = [
            "W" * 10 + "H",
            "H" + "W" * 10,
        ] * 16

        assert rows_height(len(wall_layout)) == height
        for row in wall_layout:
            assert row_width(row) == width

        return wall_layout


def test():
    test_rows_from()


def test_rows_from():
    rows = Layout.rows_from_stretcher_bond(width=WALL.dx, height=WALL.dy)
    assert rows
    assert len(rows) == 32
    for row in rows:
        assert len(row) == 11

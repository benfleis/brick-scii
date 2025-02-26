#!/usr/bin/env python3

##
# NOTE: also to see in `README.md`
# - units in integer micrometers (avoid FP for now, but accommodate half mms)
# - strong pref immutable/dataclass for most things, but leverage OO-ish funcs
# - constants >> magic strings
# - "bit" is the name for all installed things: bricks & mortar; bad name but works for now
# - docs are minimal, not prod ready
#

from colored import Fore, Style
from dataclasses import dataclass
from itertools import cycle, dropwhile, islice, takewhile
import copy
import sys
import typing

########################################################################
# Data defs
#


@dataclass(frozen=True)
class Bit:
    name: str
    key: str  # single char rep'ing bit type, could later fancy for e.g. dynamic brick sizes
    dx: int
    dy: int
    # dz: int # unmodeled


class Position(typing.NamedTuple):
    """Logical Position for bit/row indices within a layout."""

    bit: int  # analogue: Coordinate.x
    row: int  # analogue: Coordinate.y


class Coordinate(typing.NamedTuple):
    """Coordinate is classic cartesian on 2d space."""

    x: int  # analogue: Position.bit
    y: int  # analogue: Position.row

    def stride(self, dx: int) -> typing.Self:
        return self.__class__(self.x + dx, self.y) if dx else self

    def raise_(self, dy: int) -> typing.Self:
        return self.__class__(self.x, self.y + dy) if dy else self


@dataclass(frozen=True)
class BoundingBox:
    """BoundingBox from 2 Coordinates, lower left and upper right"""

    lower_left: Coordinate
    upper_right: Coordinate

    @classmethod
    def make(cls, c0: Coordinate, c1: Coordinate) -> typing.Self:
        x_ll = min(c0.x, c1.x)
        x_ur = max(c0.x, c1.x)
        y_ll = min(c0.y, c1.y)
        y_ur = max(c0.y, c1.y)
        return cls(lower_left=_CC(x_ll, y_ll), upper_right=_CC(x_ur, y_ur))

    def stride(self, dx: int) -> typing.Self:
        return (
            self.__class__(self.lower_left.stride(dx), self.upper_right.stride(dx))
            if dx
            else self
        )

    def raise_(self, dy: int) -> typing.Self:
        return (
            self.__class__(self.lower_left.raise_(dy), self.upper_right.raise_(dy))
            if dy
            else self
        )

    def contains(self, other: typing.Self) -> bool:
        return (
            self.lower_left.x <= other.lower_left.x
            and other.upper_right.x <= self.upper_right.x
            and self.lower_left.y <= other.lower_left.y
            and other.upper_right.y <= self.upper_right.y
        )

    def overlaps(self, other: typing.Self) -> bool:
        overlaps_x = self.dx() + other.dx() > (
            max(self.upper_right.x, other.upper_right.x)
            - min(self.lower_left.x, other.lower_left.x)
        )
        overlaps_y = self.dy() + other.dy() > (
            max(self.upper_right.y, other.upper_right.y)
            - min(self.lower_left.y, other.lower_left.y)
        )
        return overlaps_x and overlaps_y

    def touches(self, other: typing.Self) -> bool:
        touches_x = self.dx() + other.dx() >= (
            max(self.upper_right.x, other.upper_right.x)
            - min(self.lower_left.x, other.lower_left.x)
        )
        touches_y = self.dy() + other.dy() >= (
            max(self.upper_right.y, other.upper_right.y)
            - min(self.lower_left.y, other.lower_left.y)
        )
        return touches_x and touches_y

    def dx(self) -> int:
        return self.upper_right.x - self.lower_left.x

    def dy(self) -> int:
        return self.upper_right.y - self.lower_left.y


# local make shorthands for long name, since it's usually quite evident in-situ
_Pos = Position
_CC = Coordinate
_BBox = BoundingBox.make

########################################################################
# constants
#


# NOTE: upper case means _placed_ brick in State so use Uppers here
WHOLE_BRICK = Bit("whole brick", key="W", dx=210_000, dy=50_000)
HALF_BRICK = Bit("half brick", key="H", dx=100_000, dy=WHOLE_BRICK.dy)
HEAD_JOINT = Bit("head joint", key="|", dx=10_000, dy=WHOLE_BRICK.dy)
BED_JOINT = Bit("bed joint", key="_", dx=1_000, dy=12_500)

BITS = [WHOLE_BRICK, HALF_BRICK, HEAD_JOINT, BED_JOINT]
BITS_BY_KEY = {b.key: b for b in BITS}
BIT_KEYS = list(BITS_BY_KEY.keys())
ROW_BIT_KEYS = [WHOLE_BRICK.key, HALF_BRICK.key, HEAD_JOINT.key]


ORIGIN = Coordinate(0, 0)
COURSE_DY = WHOLE_BRICK.dy + BED_JOINT.dy

# Specifics of the test
WALL_2320 = _BBox(ORIGIN, _CC(x=2300_000, y=2000_000))
ROBOT_813 = _BBox(ORIGIN, _CC(x=800_000, y=1300_000))


@dataclass(frozen=True)
class PositionedBit:
    bit: Bit
    pos: Position
    bbox: BoundingBox


@dataclass(frozen=True)
class Row:
    bits: list[PositionedBit]

    @classmethod
    def make(cls, row_idx: int, row_str: str) -> typing.Self:
        y0 = row_idx * WHOLE_BRICK.dy
        y1 = y0 + WHOLE_BRICK.dy
        row: list[PositionedBit] = []
        x0 = 0
        for bit_idx, bit_key in enumerate(row_str):
            bit = BITS_BY_KEY[bit_key]
            pb = PositionedBit(
                bit=bit,
                pos=_Pos(bit=bit_idx, row=row_idx),
                bbox=_BBox(_CC(x0, y0), _CC(x0 + bit.dx, y1)),
            )
            row.append(pb)
            x0 += bit.dx
        return cls(row)

    def __str__(self) -> str:
        return self.format()

    __repr__ = __str__

    def format(self, to_lower: bool = False) -> str:
        out = "".join(map(lambda pb: pb.bit.key, self.bits))
        return out if not to_lower else out.lower()

    def overlaps_x(self, bbox: BoundingBox) -> list[PositionedBit]:
        """Return sequence of bricks overlapping _in x axis_ of `bbox`."""
        bbox = _BBox(
            _CC(bbox.lower_left.x, self.bits[0].bbox.lower_left.y),
            _CC(bbox.upper_right.x, self.bits[0].bbox.upper_right.y),
        )
        it = iter(self.bits)
        it = dropwhile(lambda pb: not bbox.overlaps(pb.bbox), it)
        return list(takewhile(lambda pb: bbox.overlaps(pb.bbox), it))

    def dx(self, first: int = 0, last: int = -1) -> int:
        return self.bits[last].bbox.upper_right.x - self.bits[first].bbox.lower_left.x


@dataclass(frozen=True)
class Layout:
    """Represent brick grid, nominally by rows. Row 0 is lowest, with all bricks having same height,
    and ordered from left-to-right (and thus increasing X).
    """

    wall: BoundingBox
    rows: list[Row]

    @classmethod
    def make(cls, wall: BoundingBox, row_strs: typing.Iterable[str]) -> typing.Self:
        """takes a sequence of rows, each row rep'd as string of half and whole bricks, e.g.
        "hwwwwh", which would represent a row beginning with a single half brick, then four
        consecutive whole bricks, and ending with a half."""
        rows: list[Row] = [
            Row.make(row_idx, row_str) for row_idx, row_str in enumerate(row_strs)
        ]

        # validate some things
        for row in rows:
            sum_x = sum((pb.bit.dx for pb in row.bits))
            dx = row.bits[-1].bbox.upper_right.x - row.bits[0].bbox.lower_left.x
            dy = row.bits[-1].bbox.upper_right.y - row.bits[0].bbox.lower_left.y
            assert sum_x == dx and dx == wall.dx()
            assert WHOLE_BRICK.dy == dy
        assert wall.dy() == len(rows) * COURSE_DY

        return cls(wall, rows)

    @classmethod
    def make_stretcher_bond(cls, wall: BoundingBox) -> typing.Self:
        # XXX: hard code the layout
        # rows = [
        # "|".join("W" * 10 + "H"),
        # "|".join("H" + "W" * 10),
        # ] * 16

        # require that width satisfies HALF + N * (HEAD+WHOLE)
        dx = wall.dx()
        whole_cnt = (dx - HALF_BRICK.dx) // (HEAD_JOINT.dx + WHOLE_BRICK.dx)
        assert dx == HALF_BRICK.dx + (whole_cnt * (HEAD_JOINT.dx + WHOLE_BRICK.dx))
        dy = wall.dy()
        row_cnt = dy // COURSE_DY
        assert dy % COURSE_DY == 0

        pattern = "H" + "|W" * whole_cnt
        rows = list(islice(cycle([pattern, "".join(reversed(pattern))]), row_cnt))
        return cls.make(wall, rows)


# NOTE: can adjust to display, but these felt good for moderate dims
_HALF_CHARS = 4
_WHOLE_CHARS = _HALF_CHARS * 2

BIT_FORMATS_BY_KEY: dict[str, tuple[str, str]] = {
    WHOLE_BRICK.key: ("▓" * _WHOLE_CHARS, "░" * _WHOLE_CHARS),
    HALF_BRICK.key: ("▓" * _HALF_CHARS, "░" * _HALF_CHARS),
    HEAD_JOINT.key: ("|", " "),
}

# Quick magic strings avoid

INITIAL = " "
FRONTIER = "f"
COMPLETE = "C"

STATUSES = [INITIAL, FRONTIER, COMPLETE]


def format_bit(bit: Bit, status: str, reachable: bool) -> str:
    complete, incomplete = BIT_FORMATS_BY_KEY[bit.key]
    if status == COMPLETE:
        return f"{Fore.red}{complete}"
    elif status == FRONTIER and reachable:
        return f"{Fore.green}{incomplete}"
    elif status == FRONTIER:
        return f"{Fore.yellow}{incomplete}"
    elif reachable:
        return f"{Fore.blue}{incomplete}"
    else:
        return f"{Style.reset}{incomplete}"


@dataclass(frozen=True)
class State:
    """
    State keeps refs to layout/wall, and manages robot action. Every action produces a new state.

    The logical layout is structurally mirrored with status cells, which can be
    initial, frontier, or complete. States can be set and checked. (Clear currently not needed.)

    Additionally provide 2 key functions that allow decision making:
    - is_reachable tells whether the robot can reach a positioned bit.
    - is_supported tells whether a positioned bit may be built (ie, the things underneath are complete)

    Main access point is the `steps()` function, which iterates through all steps until completion.

    Each step attempts to place a reachable frontier brick/mortar. If none available, consider a
    robot stride (x axis). As last resort consider a robot raise (y axis).
    """

    layout: Layout
    robot: BoundingBox
    status: list[str]

    @classmethod
    def make(cls, layout: Layout, robot: BoundingBox) -> typing.Self:
        status: list[str] = [INITIAL * len(row.bits) for row in layout.rows]
        status[0] = FRONTIER * len(layout.rows[0].bits)
        return cls(layout=layout, robot=robot, status=status)

    def print(self):
        for row_idx in range(len(self.layout.rows) - 1, -1, -1):
            bit_row = self.layout.rows[row_idx]
            bit_strings = []
            for bp in bit_row.bits:
                bit_strings.append(
                    format_bit(
                        bp.bit,
                        status=self.status[bp.pos.row][bp.pos.bit],
                        reachable=self.is_reachable(bp.bbox),
                    )
                )
            print(*bit_strings, sep="", end=Style.reset + "\n")

    def set_frontier(self, pos: Position) -> typing.Self:
        bit_idx, row_idx = pos
        row = self.status[row_idx]
        bit_status = row[bit_idx]
        assert not bit_status.isupper(), "set_frontier called on completed bit"
        if bit_status == INITIAL:
            updated_row = row[:bit_idx] + FRONTIER + row[bit_idx + 1 :]
            updated_rows = copy.copy(self.status)
            updated_rows[row_idx] = updated_row
            return copy.replace(self, status=updated_rows)
        return self  # unmodified

    def is_frontier(self, pos: Position) -> bool:
        return self.status[pos.row][pos.bit].islower()

    def set_complete(self, pos: Position) -> typing.Self:
        bit_idx, row_idx = pos
        row = self.status[row_idx]
        bit_status = row[bit_idx]
        assert bit_status != INITIAL, "set_complete called on non frontier bit"
        if bit_status.islower():
            updated_row = row[:bit_idx] + COMPLETE + row[bit_idx + 1 :]
            updated_rows = copy.copy(self.status)
            updated_rows[row_idx] = updated_row
            return copy.replace(self, status=updated_rows)
        return self  # unmodified

    def is_complete(self, pos: Position) -> bool:
        return self.status[pos.row][pos.bit].isupper()

    def is_reachable(self, bbox: BoundingBox) -> bool:
        return self.robot.contains(bbox)

    def step(self) -> typing.Self | None:
        # lay brick in reachable frontier
        if to_install := self.reachable_frontier_head():
            return self.install_bit(to_install)

        # NOTE: presume costs of brick << stride << raise_
        # frontier plucking is relatively straightforward, greedy lowest is probably enough
        # when that's empty, choosing stride trickier
        # - naively choose most current frontier works but not well
        # - better to look at sum of unlocking weight -- eg take the upward pyramid of all supported bricks
        #   - could be done here if I am ready to compute the support tree in both dirs
        # - raise should actually be straightforward if we presume to perform all horizontal work
        #   first; in that case simply ratchet high enough to maximize next round
        #

        # stride first - find lowest unreachable frontiers, stride to them (ideally centered)
        if pair := next(
            filter(lambda pair: FRONTIER in pair[1], enumerate(self.status)), None
        ):
            (row_idx, row_fs) = pair
            first = row_fs.find(FRONTIER)
            last = row_fs.rfind(FRONTIER)
            target_x = self.layout.rows[row_idx].bits[first].bbox.lower_left.x
            target_dx = self.layout.rows[row_idx].dx(first, last)
            if margin := self.robot.dx() - target_dx:
                target_x -= (margin // 10) * 10

            stride = target_x - self.robot.lower_left.x
            if stride:
                return copy.replace(self, robot=self.robot.stride(stride))

        # raise robot
        robot_course_cnt = self.robot.dy() // COURSE_DY
        rise = robot_course_cnt * COURSE_DY
        risen_robot = self.robot.raise_(rise)
        if risen_robot.lower_left.y < self.layout.wall.dy():
            return copy.replace(self, robot=risen_robot)

        # TODO: assert all complete

    def reachable_frontier_head(self) -> PositionedBit | None:
        return next(self.reachable_frontier(), None)

    def reachable_frontier(self) -> typing.Generator[PositionedBit]:
        # bottom to top, left to right
        for pb_row, status_row in zip(self.layout.rows, self.status):
            for pb, status in zip(pb_row.bits, status_row):
                if status == FRONTIER and self.is_reachable(pb.bbox):
                    yield pb

    def install_bit(self, pb: PositionedBit) -> typing.Self:
        rv = self.set_complete(pb.pos)

        if pb.pos.row != len(rv.layout.rows) - 1:
            up_row = rv.layout.rows[pb.pos.row + 1]
            new_frontier = [
                pb
                for pb in up_row.overlaps_x(pb.bbox.raise_(COURSE_DY))
                if rv.is_supported(pb)
            ]
            for frontier_pb in new_frontier:
                rv = rv.set_frontier(frontier_pb.pos)

        return rv

    def is_supported(self, pb: PositionedBit) -> bool:
        if pb.pos.row == 0:
            return True
        support_row = self.layout.rows[pb.pos.row - 1]
        support_overlaps = [
            pb for pb in support_row.overlaps_x(pb.bbox) if self.is_complete(pb.pos)
        ]
        if not support_overlaps:
            return False

        # shift bbox definition to up_row so we can use contains
        lhs_x = support_overlaps[0].bbox.lower_left.x
        rhs_x = support_overlaps[-1].bbox.upper_right.x
        support_bbox = _BBox(
            _CC(lhs_x, pb.bbox.lower_left.y),
            _CC(rhs_x, pb.bbox.upper_right.y),
        )
        return support_bbox.contains(pb.bbox)

    def steps(self) -> typing.Generator[typing.Self]:
        cur = self
        while cur:
            yield cur
            cur = cur.step()


def _test_rows_from():
    layout = Layout.make_stretcher_bond(wall=WALL_2320)
    assert layout.rows
    assert len(layout.rows) == 61
    for row in layout.rows:
        assert len(row.bits) == 11


def test_print():
    layout = Layout.make_stretcher_bond(WALL_2320)
    s0 = State.make(layout, ROBOT_813)
    s0.print()


def _t_bbox(x0, x1, y0=0, y1=1):
    return _BBox(_CC(x0, y0), _CC(x1, y1))


b02 = _t_bbox(0, 2)
b13 = _t_bbox(1, 3)
b24 = _t_bbox(2, 4)
b35 = _t_bbox(3, 5)


def test_boundingbox():
    # TODO: y tests

    # self tests
    assert b02.touches(b02)
    assert b02.overlaps(b02)
    assert b02.contains(b02)

    # b02 vs b24 (touching)
    assert b02.touches(b24)
    assert not b02.overlaps(b24)
    assert not b02.contains(b24)

    assert b24.touches(b02)
    assert not b24.overlaps(b02)
    assert not b24.contains(b02)

    # b02 vs b35 (apart)
    assert not b02.touches(b35)
    assert not b02.overlaps(b35)
    assert not b02.contains(b35)

    assert not b35.touches(b02)
    assert not b35.overlaps(b02)
    assert not b35.contains(b02)

    # b02 vs b13 (overlap)
    assert b02.touches(b13)
    assert b02.overlaps(b13)
    assert not b02.contains(b13)

    assert b13.touches(b02)
    assert b13.overlaps(b02)
    assert not b13.contains(b02)


def test_overlaps_x():
    rHWW = Row.make(0, "H|W|W")
    rWWH = Row.make(0, "W|W|H")
    r_dx = rHWW.dx()

    ols = rHWW.overlaps_x(_t_bbox(0, r_dx))
    assert len(ols) == 5
    assert ols == rHWW.bits

    ols = rHWW.overlaps_x(_t_bbox(1, r_dx - 1))
    assert len(ols) == 5
    assert ols == rHWW.bits

    ols = rHWW.overlaps_x(_t_bbox(HALF_BRICK.dx - 1, r_dx - 1))
    assert len(ols) == 5
    assert ols == rHWW.bits

    ols = rHWW.overlaps_x(_t_bbox(HALF_BRICK.dx, r_dx))
    assert len(ols) == 4
    assert ols == rHWW.bits[1:]


patterns = [
    ["H"],
    ["W"],
    ["W", "HH"],
    ["HW", "WH"],
    ["HWHW", "WHWH"],
    ["HWWW", "WHWW", "WWHW", "WWWH"],
]


def pattern_to_layout(pattern: str, row_cnt: int) -> tuple[BoundingBox, list[str]]:
    row = Row.make(0, pattern)
    dx = row.bits[-1].bbox.upper_right.x - row.bits[0].bbox.lower_left.x
    dy = row_cnt * COURSE_DY
    wall = _BBox(ORIGIN, _CC(dx, dy))
    row_strs = ([pattern, "".join(reversed(pattern))] * (1 + row_cnt // 2))[:row_cnt]
    return wall, row_strs


def main(args):
    layout = Layout.make_stretcher_bond(WALL_2320)
    robot = ROBOT_813

    # NOTE: tweak here for variations
    # wall, row_strs = pattern_to_layout("H|W|W|W", 4)
    # layout = Layout.make(wall, row_strs)
    # TODO: breaks with different robot
    # robot = _BBox(ORIGIN, _CC(600, 2000))

    s0 = State.make(layout, robot)
    for step, state in enumerate(s0.steps()):
        print("step =", step)
        print("robot =", state.robot)
        state.print()
        print()


if __name__ == "__main__":
    main(sys.argv[:])

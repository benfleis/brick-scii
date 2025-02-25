#!/usr/bin/env python3

##
# Assumptions:
# - units in integer micrometers (avoid FP for now, but accommodate half mms)
#

from colored import Fore, Style
from dataclasses import dataclass
import copy
import typing


# NOTE: I prefer immutables when reasonable, and have several helper immutables with oo-ish
# helper functions below.


@dataclass(frozen=True)
class Bit:
    name: str
    key: str
    dx: int
    dy: int
    # dz: int


class Position(typing.NamedTuple):
    """Position is brick/row index within a layout."""

    bit: int  # analogue: Coordinate.x
    row: int  # analogue: Coordinate.y


class Coordinate(typing.NamedTuple):
    """Coordinate is classic cartesian on 2d space."""

    x: int  # analogue: Position.bit
    y: int  # analogue: Position.row

    def stride(self, dx: int) -> typing.Self:
        return self.__class__(self.x + dx, self.y)

    def raise_(self, dy: int) -> typing.Self:
        return self.__class__(self.x, self.y + dy)


ORIGIN = Coordinate(0, 0)


@dataclass(frozen=True)
class BoundingBox:
    """BoundingBox from 2 Coordinates, lower left and upper right"""

    lower_left: Coordinate
    upper_right: Coordinate

    def stride(self, dx: int) -> typing.Self:
        return self.__class__(self.lower_left.stride(dx), self.upper_right.stride(dx))

    def raise_(self, dy: int) -> typing.Self:
        return self.__class__(self.lower_left.raise_(dy), self.upper_right.raise_(dy))

    def contains(self, other: typing.Self) -> bool:
        return (
            self.lower_left.x <= other.lower_left.x
            and other.upper_right.x <= self.upper_right.x
            and self.lower_left.y <= other.lower_left.y
            and other.upper_right.y <= self.upper_right.y
        )

    def touches(self, other: typing.Self) -> bool:
        return not (
            (  # x axis
                self.upper_right.x < other.lower_left.x
                or other.upper_right.x < self.lower_left.x
            )
            or (  # y axis
                self.upper_right.y < other.lower_left.y
                or other.upper_right.y < self.lower_left.y
            )
        )

    # @property
    def dx(self) -> int:
        return self.upper_right.x - self.lower_left.x

    # @property
    def dy(self) -> int:
        return self.upper_right.y - self.lower_left.y


# NOTE: upper case means _placed_ brick in State so use Uppers here
WHOLE_BRICK = Bit("whole brick", key="W", dx=210_000, dy=50_000)
HALF_BRICK = Bit("half brick", key="H", dx=100_000, dy=50_000)
HEAD_JOINT = Bit("head joint", key="|", dx=10_000, dy=50_000)
BED_JOINT = Bit("bed joint", key="_", dx=1_000, dy=12_500)

bits = [WHOLE_BRICK, HALF_BRICK, HEAD_JOINT, BED_JOINT]
bits_by_key = {b.key: b for b in bits}
bit_keys = list(bits_by_key.keys())
row_bit_keys = [WHOLE_BRICK.key, HALF_BRICK.key, HEAD_JOINT.key]

COURSE = Bit("course", key="", dx=1_000, dy=WHOLE_BRICK.dy + BED_JOINT.dy)

WALL = BoundingBox(lower_left=ORIGIN, upper_right=Coordinate(x=2300_000, y=2000_000))
ROBOT_813 = BoundingBox(ORIGIN, Coordinate(x=800_000, y=1300_000))


##
# util functions -- don't be picky about classes etc here
#


def jointed_row(row: str) -> str:
    "turn row of bricks into row of bricks with head joints"
    return HEAD_JOINT.key.join(row)


def row_width(row: str) -> int:
    "calculate row width, including head joints"
    return sum((bits_by_key[key.upper()].dx for key in row))


def row_to_brick_bboxes(y: int, row: str) -> typing.Iterable[BoundingBox]:
    x = 0
    y_top = y + WHOLE_BRICK.dy
    for bit_key in jointed_row(row):
        bit = bits_by_key[bit_key]
        x_rhs = x + bit.dx
        if bit_key != HEAD_JOINT.key:
            yield BoundingBox(Coordinate(x, y), Coordinate(x_rhs, y_top))
        x = x_rhs


def row_to_laid_bboxes(y: int, row: str) -> typing.Iterable[BoundingBox]:
    x = 0
    y_top = y + WHOLE_BRICK.dy
    laid = None
    for bit_key in jointed_row(row):
        bit = bits_by_key[bit_key]
        x_rhs = x + bit.dx
        if not laid:
            laid = [x, x_rhs]
        else:
            if bit_key.isupper():  # expand
                laid[1] = x_rhs
            else:
                yield BoundingBox(Coordinate(laid[0], y), Coordinate(laid[1], y_top))
                laid = None


def row_next_x(row: str) -> int:
    """if row empty, returns `0`; otherwise returns current row_width plus head joint width."""
    return 0 if not row else row_width(row) + HEAD_JOINT.dx


def row_slice(
    row: str, bbox: BoundingBox, include_partial: bool = True
) -> tuple[int | None, int | None]:
    """Return sequence of bricks contained by BoundingBox `row`. `include_partial` means include
    bricks that are partially in, and partially out, of box."""
    # TODO: needs unit tests
    bit_idx = x = 0
    lhs = rhs = None

    for bit_idx, bit_key in enumerate(jointed_row(row)):
        bit = bits_by_key[bit_key]
        x_rhs = x + bit.dx
        if bit == HEAD_JOINT.key:
            x = x_rhs
            continue

        # check starting point
        if lhs is None:
            if bbox.lower_left.x <= x_rhs:
                lhs = (bit_idx // 2) + 1
                if include_partial or bbox.lower_left.x <= x:
                    lhs -= 1
        # check ending point
        else:
            if x <= bbox.upper_right.x:
                rhs = bit_idx // 2
                if include_partial or x_rhs <= bbox.upper_right.x:
                    rhs += 1
                break

    return (lhs, rhs)


def rows_height(row_count: int) -> int:
    return row_count * (WHOLE_BRICK.dy + BED_JOINT.dy)


def brick_bbox(pos: Position, row: str) -> BoundingBox:
    # assert pos.row < len(layout), "Invalid brick box row"
    y0 = pos.row * COURSE.dy
    y1 = y0 + COURSE.dy

    # row = layout[pos.row]
    assert pos.bit < len(row), "Invalid brick box column"
    x0 = row_next_x(row[: pos.bit])
    x1 = x0 + bits_by_key[row[pos.bit].upper()].dx

    return BoundingBox(Coordinate(x=x0, y=y0), Coordinate(x=x1, y=y1))


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
            bit = bits_by_key[bit_key]
            pb = PositionedBit(
                bit=bit,
                pos=Position(bit=bit_idx, row=row_idx),
                bbox=BoundingBox(
                    lower_left=Coordinate(x0, y0),
                    upper_right=Coordinate(x0 + bit.dx, y1),
                ),
            )
            row.append(pb)
            x0 += bit.dx
        return cls(row)

    def format(self, to_lower: bool = False) -> str:
        out = "".join(map(lambda pb: pb.bit.key, self.bits))
        return out if not to_lower else out.lower()

    def overlaps(
        self,
        bbox: BoundingBox,
        *,
        include_partial: bool = True,
        exclude_joints: bool = False,
    ) -> list[PositionedBit]:
        """Return sequence of bricks contained by BoundingBox `bbox`. `include_partial` means include
        bricks that are partially in, and partially out, of bbox."""
        # XXX: needs unit tests
        start = stop = None
        step = 1

        for pb in self.bits:
            # check starting point
            if start is None:
                if bbox.lower_left.x <= pb.bbox.upper_right.x:
                    start = (pb.pos.bit // 2) + 1
                    if include_partial or bbox.lower_left.x <= pb.bbox.lower_left.x:
                        start -= 1

            # check ending point
            else:
                if pb.bbox.lower_left.x <= bbox.upper_right.x:
                    stop = pb.pos.bit // 2
                    if include_partial or pb.bbox.upper_right.x <= bbox.upper_right.x:
                        stop += 1
                    break

        if exclude_joints and start and not self.bits[start].bit.key.isalpha():
            start += 1
            step = 2

        return self.bits[slice(start, stop, step)]


@dataclass(frozen=True)
class Layout:
    """Represent brick grid, nominally by rows. Row 0 is lowest, with all bricks having same height,
    and ordered from left-to-right (and thus increasing X).

    Does some basic checking (total width) and normalizing.

    Head and Bed joints are implied and not explicitly tracked, but are included in calculations.
    """

    wall: BoundingBox
    rows: list[Row]

    @classmethod
    def make(cls, wall: BoundingBox, rows: typing.Iterable[str]) -> typing.Self:
        """takes a sequence of rows, each row rep'd as string of half and whole bricks, e.g.
        "hwwwwh", which would represent a row beginning with a single half brick, then four
        consecutive whole bricks, and ending with a half."""
        normalized: list[Row] = [
            Row.make(row_idx, row_str) for row_idx, row_str in enumerate(rows)
        ]
        return cls(wall, normalized)

    @classmethod
    def make_stretcher_bond(cls, wall: BoundingBox) -> typing.Self:
        # XXX: hard code the layout
        assert wall == WALL, "invalid wall, only fixed WALL"

        rows = [
            "|".join("W" * 10 + "H"),
            "|".join("H" + "W" * 10),
        ] * 16

        assert rows_height(len(rows)) == wall.dy()
        for row in rows:
            assert row_width(row) == wall.dx()

        return cls.make(wall, rows)


_HALF_CHARS = 4
_WHOLE_CHARS = _HALF_CHARS * 2

BIT_FORMATS_BY_KEY: dict[str, tuple[str, str]] = {
    WHOLE_BRICK.key: ("▓" * _WHOLE_CHARS, "░" * _WHOLE_CHARS),
    HALF_BRICK.key: ("▓" * _HALF_CHARS, "░" * _HALF_CHARS),
    HEAD_JOINT.key: ("|", " "),
}


def format_bit(bit: Bit, status: str, reachable: bool) -> str:
    complete, incomplete = BIT_FORMATS_BY_KEY[bit.key]
    if status == "C":
        return f"{Fore.red}{complete}"
    elif status == "f" and reachable:
        return f"{Fore.green}{incomplete}"
    elif status == "f":
        return f"{Fore.yellow}{incomplete}"
    else:
        return f"{Style.reset}{incomplete}"


@dataclass(frozen=True)
class State:
    layout: Layout
    robot: BoundingBox
    status: list[str]  # NOTE: map= " ": non-frontier, "f": frontier, "C": complete

    @classmethod
    def make(cls, layout: Layout, robot: BoundingBox) -> typing.Self:
        status: list[str] = [" " * len(row.bits) for row in layout.rows]
        status[0] = "f" * len(layout.rows[0].bits)
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
        if bit_status == " ":
            updated_row = row[:bit_idx] + "f" + row[bit_idx + 1 :]
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
        assert bit_status != " ", "set_complete called on non frontier bit"
        if bit_status.islower():
            updated_row = row[:bit_idx] + "C" + row[bit_idx + 1 :]
            updated_rows = copy.copy(self.status)
            updated_rows[row_idx] = updated_row
            return copy.replace(self, status=updated_rows)
        return self  # unmodified

    def is_complete(self, pos: Position) -> bool:
        return self.status[pos.row][pos.bit].isupper()

    def is_reachable(self, bbox: BoundingBox) -> bool:
        return self.robot.contains(bbox)

    def step(self) -> typing.Self | None:
        # NOTE: presume costs of brick << stride << raise_

        # lay brick in reachable frontier
        if to_complete := self.reachable_frontier_head():
            return self.do_bit(to_complete)

        # otherwise move robot -- greedy/naive way is to try all possible strides, keep all that produce
        # reachable frontier, and choose shortest stride among max
        best = ([], self)
        stride_dx = HEAD_JOINT.dx
        for x in range(
            0, (self.layout.wall.dx() - self.robot.dx()) + stride_dx, stride_dx
        ):
            stride = x - self.robot.lower_left.x
            strode = copy.replace(self, robot=self.robot.stride(stride))
            reachables = list(strode.reachable_frontier())
            if len(reachables) > len(best[0]):  # or == and abs(stride) smaller
                best = (reachables, strode)
        if reachables := best[0]:
            wip = best[1]
            for frontier_pb in reachables:
                wip = wip.set_frontier(frontier_pb.pos)
            return wip

    def reachable_frontier_head(self) -> PositionedBit | None:
        return next(self.reachable_frontier(), None)

    def reachable_frontier(self) -> typing.Generator[PositionedBit]:
        # bottom to top, left to right
        for pb_row, status_row in zip(self.layout.rows, self.status):
            for pb, status in zip(pb_row.bits, status_row):
                if status == "f" and self.is_reachable(pb.bbox):
                    yield pb

    def do_bit(self, pb: PositionedBit) -> typing.Self:
        rv = self.set_complete(pb.pos)

        if pb.pos.row != len(rv.layout.rows) - 1:
            up_row = rv.layout.rows[pb.pos.row + 1]
            new_frontier = [
                pb
                for pb in up_row.overlaps(
                    pb.bbox, include_partial=True, exclude_joints=False
                )
                if rv.is_supported(pb)
            ]
            for frontier_pb in new_frontier:
                rv = self.set_frontier(frontier_pb.pos)

        return rv

    def is_supported(self, pb: PositionedBit) -> bool:
        if pb.pos.row == 0:
            return True
        support_row = self.layout.rows[pb.pos.row - 1]
        support_overlaps = [
            pb
            for pb in support_row.overlaps(
                pb.bbox, include_partial=True, exclude_joints=False
            )
            if self.is_complete(pb.pos)
        ]
        if not support_overlaps:
            return False

        support_bbox = BoundingBox(
            lower_left=support_overlaps[0].bbox.lower_left,
            upper_right=support_overlaps[-1].bbox.upper_right,
        )
        return support_bbox.contains(pb.bbox)

    def steps(self) -> typing.Iterable[typing.Self]:
        cur = self
        while cur:
            yield cur
            cur = cur.step()


def test():
    test_rows_from()
    test_print()


def test_rows_from():
    layout = Layout.make_stretcher_bond(wall=WALL)
    assert layout.rows
    assert len(layout.rows) == 61
    for row in layout.rows:
        assert len(row.bits) == 11


def test_print():
    layout = Layout.make_stretcher_bond(WALL)
    s0 = State.make(layout, ROBOT_813)
    s0.print()


def test_steps():
    layout = Layout.make_stretcher_bond(WALL)
    s0 = State.make(layout, ROBOT_813)
    for step, state in enumerate(s0.steps()):
        print("step =", step)
        print("robot = ", state.robot)
        state.print()
        print()


if __name__ == "__main__":
    test_steps()

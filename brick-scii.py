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


@dataclass(frozen=True, kw_only=True)
class Position:
    """Position is brick/row index within a layout."""

    brick: int
    row: int


@dataclass(frozen=True)
class Coordinate:
    """Coordinate is classic cartesian on 2d space."""

    x: int
    y: int

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
    return sum((bits_by_key[key.upper()].dx for key in jointed_row(row)))


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
    assert pos.brick < len(row), "Invalid brick box column"
    x0 = row_next_x(row[: pos.brick])
    x1 = x0 + bits_by_key[row[pos.brick].upper()].dx

    return BoundingBox(Coordinate(x=x0, y=y0), Coordinate(x=x1, y=y1))


@dataclass(frozen=True)
class Layout:
    """Represent brick grid, nominally by rows. Row 0 is lowest, with all bricks having same height,
    and ordered from left-to-right (and thus increasing X).

    Does some basic checking (total width) and normalizing.

    Head and Bed joints are implied and not explicitly tracked, but are included in calculations.
    """

    wall: BoundingBox
    rows: list[str]

    @classmethod
    def normalize(cls, wall: BoundingBox, rows: typing.Iterable[str]) -> typing.Self:
        """takes a sequence of rows, each row rep'd as string of half and whole bricks, e.g.
        "hwwwwh", which would represent a row beginning with a single half brick, then four
        consecutive whole bricks, and ending with a half."""
        normalized = []
        layout_width: int = -1

        for i, row in enumerate(rows):
            for key in row:
                assert key in row_bit_keys, "Got invalid key"
            row_normalized = row.replace(HEAD_JOINT.key, "")
            normalized.append(row_normalized)
            width = row_width(row_normalized)
            if i == 0:
                layout_width = width
            else:
                assert layout_width == width, (
                    f"Got layout != row width: {layout_width} != {row_width}"
                )

        return cls(wall, normalized)

    @classmethod
    def from_stretcher_bond(cls, wall: BoundingBox) -> typing.Self:
        # XXX: hard code the layout
        assert wall == WALL, "invalid wall, only fixed WALL"

        # NOTE: - order is bottom-to-top, reverse of how we'll visualize it!
        rows = [
            "W" * 10 + "H",
            "H" + "W" * 10,
        ] * 16

        assert rows_height(len(rows)) == wall.dy()
        for row in rows:
            assert row_width(row) == wall.dx()

        return cls.normalize(wall, rows)

    def to_init_rows(self) -> list[str]:
        return [row.lower() for row in self.rows]


PRINT_BITS_BY_KEY = {
    WHOLE_BRICK.key: "▓" * (WHOLE_BRICK.dx // HEAD_JOINT.dx),
    WHOLE_BRICK.key.lower(): "░" * (WHOLE_BRICK.dx // HEAD_JOINT.dx),
    HALF_BRICK.key: "▓" * (HALF_BRICK.dx // HEAD_JOINT.dx),
    HALF_BRICK.key.lower(): "░" * (HALF_BRICK.dx // HEAD_JOINT.dx),
    HEAD_JOINT.key: " ",
}


def format_bit(key: str, in_frontier: bool, in_reach: bool) -> str:
    output = PRINT_BITS_BY_KEY[key]
    if key.isupper():
        return f"{Fore.red}{output}{Style.reset}"
    elif in_reach and in_frontier:
        return f"{Fore.green}{output}{Style.reset}"
    elif in_frontier:  # and not in_reach
        return f"{Fore.yellow}{output}{Style.reset}"
    else:  # not in_frontier
        return output


@dataclass(frozen=True)
class State:
    rows: list[str]
    robot: BoundingBox
    frontier: list[Position]

    @classmethod
    def initial(cls, layout: Layout, robot: BoundingBox) -> typing.Self:
        return cls(
            rows=layout.to_init_rows(),
            robot=robot,
            # first frontier is bottom row
            frontier=[Position(brick=n, row=0) for n in range(len(layout.rows))],
        )

    def print(self):
        for row_idx in range(len(self.rows) - 1, -1, -1):
            row = self.rows[row_idx]
            brick_strings = []
            for brick_idx, brick_key in enumerate(row):
                pos = Position(row=row_idx, brick=brick_idx)
                in_frontier = pos in self.frontier
                in_reach = self.robot.contains(brick_bbox(pos, row))
                brick_strings.append(
                    format_bit(
                        key=brick_key, in_frontier=in_frontier, in_reach=in_reach
                    )
                )
            print(*brick_strings)

    @property
    def reachable_frontier(self):
        return [
            pos
            for pos in self.frontier
            if self.robot.contains(brick_bbox(pos, self.rows[pos.row]))
        ]

    def set_brick(self, pos: Position) -> typing.Self:
        # first update brick
        rows = self.rows
        row = rows[pos.row]
        updated_row = row[: pos.brick] + row[pos.brick].upper() + row[pos.brick + 1 :]
        updated_rows = rows[: pos.row] + [updated_row] + rows[pos.row + 1 :]

        # then remove brick from frontier
        updated_frontier = copy.copy(self.frontier)
        updated_frontier.remove(pos)

        # then add newly unlocked positions
        if pos.row != len(self.rows) - 1:
            up_row_y = pos.row * COURSE.dy
            # pos_bbox = brick_bbox(pos, row)
            # first find all touched upward bricks
            up_row = self.rows[pos.row + 1]
            # start, stop = row_slice(up_row, pos_bbox, True)
            up_bricks_bboxes = row_to_brick_bboxes(up_row_y, up_row)
            # NOTE: laid bboxes calculated with up_row_y to allow contains checks
            supporting_bboxes = list(row_to_laid_bboxes(up_row_y, updated_row))

            def is_unlocked(bbox: BoundingBox) -> bool:
                return any((supp.contains(bbox) for supp in supporting_bboxes))

            new_frontier = [
                Position(brick=idx, row=pos.row + 1)
                for idx, bbox in enumerate(up_bricks_bboxes)
                if Position(brick=idx, row=pos.row + 1) not in self.frontier
                and is_unlocked(bbox)
            ]
            if new_frontier:
                updated_frontier.extend(new_frontier)
                # TODO: sort

        return copy.replace(self, rows=updated_rows, frontier=updated_frontier)

    def step(self) -> typing.Self | None:
        # lay bricks in reachable frontier
        cur = self
        for pos in cur.reachable_frontier:
            if cur.robot.contains(brick_bbox(pos, cur.rows[pos.brick])):
                return cur.set_brick(pos)

    def steps(self) -> typing.Iterable[typing.Self]:
        cur = self
        while cur:
            yield cur
            cur = cur.step()


def test():
    test_rows_from()
    test_print()


def test_rows_from():
    layout = Layout.from_stretcher_bond(wall=WALL)
    assert layout.rows
    assert len(layout.rows) == 32
    for row in layout.rows:
        assert len(row) == 11


def test_print():
    layout = Layout.from_stretcher_bond(WALL)
    s0 = State.initial(layout, ROBOT_813)
    s0.print()


def test_steps():
    layout = Layout.from_stretcher_bond(WALL)
    s0 = State.initial(layout, ROBOT_813)
    for state in s0.steps():
        state.print()


if __name__ == "__main__":
    test_steps()

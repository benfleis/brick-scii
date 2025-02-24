#!/usr/bin/env python3

##
# Assumptions:
# - units in integer micrometers (avoid FP for now, but accommodate half mms)
#

from colored import Fore, Style
import typing


class Bit(typing.NamedTuple):
    name: str
    key: str
    dx: int
    dy: int
    # dz: int


mm = 1000
µm = 1

# NOTE: upper case means _placed_ brick in State so use Uppers here
WHOLE_BRICK = Bit("whole brick", key="W", dx=210 * mm, dy=50 * mm)
HALF_BRICK = Bit("half brick", key="H", dx=100 * mm, dy=50 * mm)
HEAD_JOINT = Bit("head joint", key="|", dx=10 * mm, dy=50 * mm)
BED_JOINT = Bit("bed joint", key="_", dx=1 * mm, dy=12500 * µm)

bits = [WHOLE_BRICK, HALF_BRICK, HEAD_JOINT, BED_JOINT]
bits_by_key = {b.key: b for b in bits}
bit_keys = list(bits_by_key.keys())
row_bit_keys = [WHOLE_BRICK.key, HALF_BRICK.key, HEAD_JOINT.key]


WALL = Bit("wall", key="", dx=2300 * mm, dy=2000 * mm)
COURSE = Bit("course", key="", dx=1 * mm, dy=WHOLE_BRICK.dy + BED_JOINT.dy)
ROBOT = Bit("robot", key="", dx=800 * mm, dy=1300 * mm)


class Position(typing.NamedTuple):
    """Position is row/brick index within a layout."""

    row: int
    brick: int


class Coordinate(typing.NamedTuple):
    """Coordinate is classic cartesian on 2d space."""

    x: int
    y: int


##
# util functions -- don't be picky about classes etc here
#


def join_row(row: str) -> str:
    "turn row of bricks into row of bricks with head joints"
    return HEAD_JOINT.key.join(row)


def row_width(row: str) -> int:
    "calculate row width, including head joints"
    return sum((bits_by_key[key.upper()].dx for key in join_row(row)))


def row_next_x(row: str) -> int:
    """if row empty, returns `0`; otherwise returns current row_width plus head joint width."""
    return 0 if not row else row_width(row) + HEAD_JOINT.dx


def rows_height(row_count: int) -> int:
    return row_count * (WHOLE_BRICK.dy + BED_JOINT.dy)


def brick_box(layout: list[str], pos: Position) -> tuple[Coordinate, Coordinate]:
    assert pos.row < len(layout), "Invalid brick box row"
    y0 = pos.row * COURSE.dy
    y1 = y0 + COURSE.dy

    row = layout[pos.row]
    assert pos.brick < len(row), "Invalid brick box column"
    x0 = row_next_x(row[: pos.brick])
    x1 = x0 + bits_by_key[row[pos.brick].upper()].dx

    return (Coordinate(x=x0, y=y0), Coordinate(x=x1, y=y1))


class Layout:
    """Represent brick grid, nominally by rows. Row 0 is lowest, with all bricks having same height,
    and ordered from left-to-right (and thus increasing X).

    Does some basic checking (total width) and normalizing.

    Head and Bed joints are implied and not explicitly tracked, but are included in calculations.
    """

    def __init__(self, rows: typing.Iterable[str]):
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
        self.rows = grid

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


class Robot:
    def __init__(self, *, box_dx, box_dy):
        """Define robot by its envelope. Assume its starting position to be lower left."""
        self.x0 = 0
        self.x1 = box_dx
        self.y0 = 0
        self.y1 = box_dy

    def reaches(self, *, x0, x1, y0, y1) -> bool:
        assert x0 <= x1 and y0 <= y1, "covers got invalid bounding box"
        return x0 >= self.x0 and x1 <= self.x1 and y0 >= self.y0 and y1 <= self.y1


def format_bit(key: str, in_frontier: bool, in_reach: bool) -> str:
    print_bits_by_key = {
        WHOLE_BRICK.key: "▓▓▓▓",
        WHOLE_BRICK.key.lower(): "░░░░",
        HALF_BRICK.key: "▓▓",
        HALF_BRICK.key.lower(): "░░",
        HEAD_JOINT.key: " ",
    }
    output = print_bits_by_key[key]
    if key.isupper():
        return f"{Fore.red}{output}{Style.reset}"
    elif in_reach and in_frontier:
        return f"{Fore.green}{output}{Style.reset}"
    elif in_frontier:  # and not in_reach
        return f"{Fore.yellow}{output}{Style.reset}"
    else:  # not in_frontier
        return output


class State:
    def __init__(
        self,
        *,
        layout: Layout,
        robot: Robot,
        frontier: typing.Iterable[Position] = (),
    ):
        self.layout = [row.lower() for row in layout.rows]
        self.robot = robot
        self.frontier = list(frontier)

    def robot_reaches_brick(self, pos: Position) -> bool:
        # first calculate lower left corner of given brick
        lower_left, upper_right = brick_box(self.layout, pos)
        return self.robot.reaches(
            x0=lower_left.x, y0=lower_left.y, x1=upper_right.x, y1=upper_right.y
        )

    def print(self):
        for row_idx in range(len(self.layout) - 1, -1, -1):
            row = self.layout[row_idx]
            brick_strings = []
            for brick_idx, brick_key in enumerate(row):
                pos = Position(row=row_idx, brick=brick_idx)
                in_frontier = pos in self.frontier
                in_reach = self.robot_reaches_brick(pos)
                brick_strings.append(
                    format_bit(
                        key=brick_key, in_frontier=in_frontier, in_reach=in_reach
                    )
                )
            print(*brick_strings)


def test():
    test_rows_from()
    test_print()


def test_rows_from():
    layout = Layout.rows_from_stretcher_bond(width=WALL.dx, height=WALL.dy)
    assert layout
    assert len(layout) == 32
    for row in layout:
        assert len(row) == 11


def test_print():
    layout = Layout(Layout.rows_from_stretcher_bond(width=WALL.dx, height=WALL.dy))
    robot = Robot(box_dx=ROBOT.dx, box_dy=ROBOT.dy)
    st0 = State(layout=layout, robot=robot)
    st0.print()


if __name__ == "__main__":
    test_print()

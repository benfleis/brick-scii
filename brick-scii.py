#!/usr/bin/env python3

##
# NOTE: also to see in `README.md`
# - units in integer micrometers (avoid FP for now, but accommodate half mms)
# - strong pref immutable/dataclass for most things, but leverage OO-ish funcs
# - constants >> magic strings
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
class Item:
    """Item is a Brick or Mortar Joint. Questionable name, less important right now."""

    name: str
    key: str  # single char rep'ing item type, could later fancy for e.g. dynamic brick sizes
    dx: int
    dy: int
    # dz: int # unmodeled


class Position(typing.NamedTuple):
    """Logical Position for item/row indices within a layout."""

    item: int  # analogue: Coordinate.x
    row: int  # analogue: Coordinate.y


class Coordinate(typing.NamedTuple):
    """Coordinate is classic cartesian on 2d space."""

    x: int  # analogue: Position.item
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

# NOTE: units are micrometers so we can avoid FP hassles for now

BRICK_DX = 210_000
BRICK_DY = 50_000

HEAD_JOINT_DX = 10_000
BED_JOINT_DY = 12_500

COURSE_DY = BRICK_DY + BED_JOINT_DY

# These defs honor the "front face" nature, ignore actual 3d (cut) bricks
HEAD_JOINT = Item("head joint", key="|", dx=HEAD_JOINT_DX, dy=BRICK_DY)
STRETCHER = Item("stretcher", key="S", dx=BRICK_DX, dy=BRICK_DY)
HEADER = Item("header", key="H", dx=(BRICK_DX - HEAD_JOINT.dx) // 2, dy=BRICK_DY)
QUEEN_CLOSER = Item(
    "queen closer", key="Q", dx=(HEADER.dx - HEAD_JOINT.dx) // 2, dy=BRICK_DY
)

ITEMS = [HEAD_JOINT, STRETCHER, HEADER, QUEEN_CLOSER]
ITEMS_BY_KEY = {b.key: b for b in ITEMS}
ITEM_KEYS = list(ITEMS_BY_KEY.keys())

assert (STRETCHER.dx - HEAD_JOINT_DX) // 2 == HEADER.dx

ORIGIN = Coordinate(0, 0)

# Specifics of the test
WALL_2320 = _BBox(ORIGIN, _CC(x=2300_000, y=2000_000))
ROBOT_813 = _BBox(ORIGIN, _CC(x=800_000, y=1300_000))


@dataclass(frozen=True)
class PositionedItem:
    item: Item
    pos: Position
    bbox: BoundingBox


@dataclass(frozen=True)
class Row:
    pos_items: list[PositionedItem]

    @classmethod
    def make(cls, row_idx: int, row_str: str) -> typing.Self:
        y0 = row_idx * STRETCHER.dy
        y1 = y0 + STRETCHER.dy
        row: list[PositionedItem] = []
        x0 = 0
        for item_idx, item_key in enumerate(row_str):
            item = ITEMS_BY_KEY[item_key]
            pb = PositionedItem(
                item=item,
                pos=_Pos(item=item_idx, row=row_idx),
                bbox=_BBox(_CC(x0, y0), _CC(x0 + item.dx, y1)),
            )
            row.append(pb)
            x0 += item.dx
        return cls(row)

    def __str__(self) -> str:
        return self.format()

    __repr__ = __str__

    def format(self, to_lower: bool = False) -> str:
        out = "".join(map(lambda pb: pb.item.key, self.pos_items))
        return out if not to_lower else out.lower()

    def overlaps_x(self, bbox: BoundingBox) -> list[PositionedItem]:
        """Return sequence of bricks overlapping _in x axis_ of `bbox`."""
        bbox = _BBox(
            _CC(bbox.lower_left.x, self.pos_items[0].bbox.lower_left.y),
            _CC(bbox.upper_right.x, self.pos_items[0].bbox.upper_right.y),
        )
        it = iter(self.pos_items)
        it = dropwhile(lambda pb: not bbox.overlaps(pb.bbox), it)
        return list(takewhile(lambda pb: bbox.overlaps(pb.bbox), it))

    def dx(self, first: int = 0, last: int = -1) -> int:
        return (
            self.pos_items[last].bbox.upper_right.x
            - self.pos_items[first].bbox.lower_left.x
        )


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
            sum_x = sum((pb.item.dx for pb in row.pos_items))
            dx = (
                row.pos_items[-1].bbox.upper_right.x
                - row.pos_items[0].bbox.lower_left.x
            )
            dy = (
                row.pos_items[-1].bbox.upper_right.y
                - row.pos_items[0].bbox.lower_left.y
            )
            assert sum_x == dx and dx == wall.dx()
            assert STRETCHER.dy == dy
        assert wall.dy() == len(rows) * COURSE_DY

        return cls(wall, rows)

    @classmethod
    def make_stretcher_bond(cls, wall: BoundingBox) -> typing.Self:
        # require that width satisfies HALF + N * (HEAD+WHOLE)
        # could also support whole || double-half ends
        dx = wall.dx()
        stretcher_cnt = (dx - HEADER.dx) // (HEAD_JOINT.dx + STRETCHER.dx)
        pattern = HEAD_JOINT.key.join(HEADER.key + (STRETCHER.key * stretcher_cnt))
        assert dx == Row.make(0, pattern).dx(), "pattern DX incorrect: " + pattern

        dy = wall.dy()
        row_cnt = dy // COURSE_DY
        assert dy % COURSE_DY == 0

        rows = list(islice(cycle([pattern, "".join(reversed(pattern))]), row_cnt))
        return cls.make(wall, rows)

    @classmethod
    def make_english_cross_bond(cls, wall: BoundingBox) -> typing.Self:
        # forms:
        # - S*
        # - HQ(H*)QH
        dx, dy = wall.dx(), wall.dy()
        stretcher_cnt = (dx + HEAD_JOINT.dx) // (HEAD_JOINT.dx + STRETCHER.dx)
        header_cnt = (stretcher_cnt * 2) - 3
        patterns = [
            # S*
            HEAD_JOINT.key.join(STRETCHER.key * stretcher_cnt),
            # HQ(H*)QH
            HEAD_JOINT.key.join(
                (HEADER.key + QUEEN_CLOSER.key)
                + (HEADER.key * header_cnt)
                + (QUEEN_CLOSER.key + HEADER.key)
            ),
        ]
        for pattern in patterns:
            assert dx == Row.make(0, pattern).dx(), "pattern DX incorrect: " + pattern

        row_cnt = dy // COURSE_DY
        assert dy % COURSE_DY == 0

        rows = list(islice(cycle(patterns), row_cnt))
        return cls.make(wall, rows)


ITEM_FORMATS_BY_KEY: dict[str, tuple[str, str]] = {
    STRETCHER.key: ("[⊠⊠⊠⊠⊠⊠⊠⊠⊠⊠]", "<==========>"),
    HEADER.key: ("[⊞⊞⊞⊞]", "<---->"),
    QUEEN_CLOSER.key: ("[⊡]", "<->"),
    HEAD_JOINT.key: ("", ""),
}

# Quick magic strings avoid

INITIAL = " "
FRONTIER = "f"
COMPLETE = "C"

STATUSES = [INITIAL, FRONTIER, COMPLETE]


def format_item(item: Item, status: str, reachable: bool) -> str:
    complete, incomplete = ITEM_FORMATS_BY_KEY[item.key]
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
    - is_reachable tells whether the robot can reach a positioned item.
    - is_supported tells whether a positioned item may be built (ie, the things underneath are complete)

    Main access point is the `steps()` function, which iterates through all steps until completion.

    Each step attempts to place a reachable frontier brick/mortar. If none available, consider a
    robot stride (x axis). As last resort consider a robot raise (y axis).
    """

    layout: Layout
    robot: BoundingBox
    status: list[str]

    @classmethod
    def make(cls, layout: Layout, robot: BoundingBox) -> typing.Self:
        assert robot.contains(_BBox(ORIGIN, _CC(STRETCHER.dx, STRETCHER.dy))), (
            "robot smaller than brick, probably expressed in mm instead of µm"
        )
        status: list[str] = [INITIAL * len(row.pos_items) for row in layout.rows]
        status[0] = FRONTIER * len(layout.rows[0].pos_items)
        return cls(layout=layout, robot=robot, status=status)

    def print(self):
        for row_idx in range(len(self.layout.rows) - 1, -1, -1):
            item_row = self.layout.rows[row_idx]
            item_strings = []
            for bp in item_row.pos_items:
                item_strings.append(
                    format_item(
                        bp.item,
                        status=self.status[bp.pos.row][bp.pos.item],
                        reachable=self.is_reachable(bp.bbox),
                    )
                )
            print(*item_strings, sep="", end=Style.reset + "\n")

    def set_frontier(self, pos: Position) -> typing.Self:
        item_idx, row_idx = pos
        row = self.status[row_idx]
        item_status = row[item_idx]
        assert not item_status.isupper(), "set_frontier called on completed item"
        if item_status == INITIAL:
            updated_row = row[:item_idx] + FRONTIER + row[item_idx + 1 :]
            updated_rows = copy.copy(self.status)
            updated_rows[row_idx] = updated_row
            return copy.replace(self, status=updated_rows)
        return self  # unmodified

    def is_frontier(self, pos: Position) -> bool:
        return self.status[pos.row][pos.item].islower()

    def set_complete(self, pos: Position) -> typing.Self:
        item_idx, row_idx = pos
        row = self.status[row_idx]
        item_status = row[item_idx]
        assert item_status != INITIAL, "set_complete called on non frontier item"
        if item_status.islower():
            updated_row = row[:item_idx] + COMPLETE + row[item_idx + 1 :]
            updated_rows = copy.copy(self.status)
            updated_rows[row_idx] = updated_row
            return copy.replace(self, status=updated_rows)
        return self  # unmodified

    def is_complete(self, pos: Position) -> bool:
        return self.status[pos.row][pos.item].isupper()

    def is_reachable(self, bbox: BoundingBox) -> bool:
        return self.robot.contains(bbox)

    def step(self) -> typing.Self | None:
        # lay brick in reachable frontier
        if to_install := self.reachable_frontier_head():
            return self.install_item(to_install)

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
            target_x = self.layout.rows[row_idx].pos_items[first].bbox.lower_left.x
            target_dx = self.layout.rows[row_idx].dx(first, last)
            if margin := self.robot.dx() - target_dx:
                target_x -= (margin // 10) * 10

            stride = target_x - self.robot.lower_left.x
            if stride:
                return copy.replace(self, robot=self.robot.stride(stride))

        # raise robot to next unreachable row
        robot_course_cnt = self.robot.dy() // COURSE_DY
        rise = robot_course_cnt * COURSE_DY
        risen_robot = self.robot.raise_(rise)
        if risen_robot.lower_left.y < self.layout.wall.dy():
            return copy.replace(self, robot=risen_robot)

        for row_status in self.status:
            assert row_status.replace(COMPLETE, "") == "", (
                "steps() halted, but build incomplete"
            )

    def reachable_frontier_head(self) -> PositionedItem | None:
        return next(self.reachable_frontier(), None)

    def reachable_frontier(self) -> typing.Generator[PositionedItem]:
        # bottom to top, left to right
        for pb_row, status_row in zip(self.layout.rows, self.status):
            for pb, status in zip(pb_row.pos_items, status_row):
                if status == FRONTIER and self.is_reachable(pb.bbox):
                    yield pb

    def install_item(self, pb: PositionedItem) -> typing.Self:
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

    def is_supported(self, pb: PositionedItem) -> bool:
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
        assert len(row.pos_items) == 11


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
    rHSS = Row.make(0, "H|S|S")
    rSSH = Row.make(0, "S|S|H")
    r_dx = rHSS.dx()

    ols = rHSS.overlaps_x(_t_bbox(0, r_dx))
    assert len(ols) == 5
    assert ols == rHSS.pos_items

    ols = rHSS.overlaps_x(_t_bbox(1, r_dx - 1))
    assert len(ols) == 5
    assert ols == rHSS.pos_items

    ols = rHSS.overlaps_x(_t_bbox(HEADER.dx - 1, r_dx - 1))
    assert len(ols) == 5
    assert ols == rHSS.pos_items

    ols = rHSS.overlaps_x(_t_bbox(HEADER.dx, r_dx))
    assert len(ols) == 4
    assert ols == rHSS.pos_items[1:]


patterns = [
    ["H"],
    ["S"],
    ["S", "HH"],
    ["HS", "SH"],
    ["HSHS", "SHSH"],
    ["HSSS", "SHSS", "SSHS", "SSSH"],
]


def pattern_to_layout(pattern: str, row_cnt: int) -> tuple[BoundingBox, list[str]]:
    row = Row.make(0, pattern)
    dx = row.pos_items[-1].bbox.upper_right.x - row.pos_items[0].bbox.lower_left.x
    dy = row_cnt * COURSE_DY
    wall = _BBox(ORIGIN, _CC(dx, dy))
    row_strs = ([pattern, "".join(reversed(pattern))] * (1 + row_cnt // 2))[:row_cnt]
    return wall, row_strs


def test_make_stretcher():
    layout = Layout.make_stretcher_bond(WALL_2320)
    robot = ROBOT_813
    list(enumerate(State.make(layout, robot).steps()))


def test_make_english_cross():
    wall = _BBox(ORIGIN, _CC(2190_000, 2000_000))
    layout = Layout.make_english_cross_bond(wall)
    list(enumerate(State.make(layout, ROBOT_813).steps()))


def main(args):
    # stretcher
    layout = Layout.make_stretcher_bond(WALL_2320)
    robot = ROBOT_813

    # english cross
    # wall = _BBox(ORIGIN, _CC(2190_000, 2000_000))
    # layout = Layout.make_english_cross_bond(wall)

    # NOTE: tweak here for variations
    # wall, row_strs = pattern_to_layout("S|S|S|S|S|S|S|S|S|S", 32)
    # layout = Layout.make(wall, row_strs)
    # robot = _BBox(ORIGIN, _CC(400_000, 2000_000))

    s0 = State.make(layout, robot)
    for step, state in enumerate(s0.steps()):
        print("step =", step)
        print("robot =", state.robot)
        state.print()
        print()


if __name__ == "__main__":
    main(sys.argv[:])

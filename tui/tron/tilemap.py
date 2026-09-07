"""Level parsing, and the collision the whole game stands on.

A direct port of ``web/js/tilemap.js``. It imports nothing outside the standard
library and knows nothing about terminals: everything here is world pixels.

The one structural difference from the JavaScript is that boxes are a real
type (:class:`Box`) rather than object literals, because :meth:`Tilemap.move_x`
and :meth:`Tilemap.move_y` mutate the thing they are handed and a dataclass
says so.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from . import config as C

TILE_AIR = "."
TILE_SOLID = "#"
TILE_PLATFORM = "="
TILE_WATER = "~"
TILE_UPDRAFT = "^"
TILE_RAIL = "-"

#: Characters lifted out of the grid at parse time. Their cells become air, so
#: collision never has to know what a gargoyle is.
ENTITY_CHARS = frozenset("SEoTRONgfsbc")


def is_solid_tile(ch: str) -> bool:
    return ch == TILE_SOLID


def is_platform_tile(ch: str) -> bool:
    return ch in (TILE_PLATFORM, TILE_RAIL)


def is_rail_tile(ch: str) -> bool:
    return ch == TILE_RAIL


def is_water_tile(ch: str) -> bool:
    return ch == TILE_WATER


def is_updraft_tile(ch: str) -> bool:
    return ch == TILE_UPDRAFT


def sign(n: float) -> float:
    """JavaScript's ``Math.sign``: -1, 0 or 1, and 0 stays 0."""
    if n > 0:
        return 1.0
    if n < 0:
        return -1.0
    return 0.0


@dataclass
class Box:
    """An axis-aligned body in world pixels. Mutated in place by the movers."""

    x: float
    y: float
    w: float
    h: float


@dataclass
class Pickup:
    """A note or a letter. ``taken`` is cleared on retry rather than reparsed."""

    x: float
    y: float
    w: float
    h: float
    ch: str = ""
    taken: bool = False


@dataclass
class Landing:
    """Which surface stopped a vertical move, if any."""

    ground: bool = False
    ceiling: bool = False
    platform: bool = False


@dataclass
class Marker:
    """Where something starts. Kind is only meaningful for enemies."""

    x: float
    y: float
    kind: str = ""


@dataclass
class Rect:
    x: float
    y: float
    w: float
    h: float


class Tilemap:
    """A parsed level: terrain, plus the things that were sitting in it."""

    def __init__(self, level: dict) -> None:
        self.name: str = str(level["name"])
        self.subtitle: str = str(level.get("subtitle", ""))

        rows = list(level["rows"])
        width = max(len(r) for r in rows)
        self.cols = width
        self.rows = len(rows)
        self.w = self.cols * C.TILE
        self.h = self.rows * C.TILE

        self.spawn = Marker(C.TILE, C.TILE)
        self.exit: Rect | None = None
        self.notes: list[Pickup] = []
        self.letters: list[Pickup] = []
        self.enemies: list[Marker] = []
        self.bells: list[Marker] = []
        self.trolleys: list[Marker] = []

        self.grid: list[list[str]] = []
        for ty, raw in enumerate(rows):
            # Short rows are padded rather than rejected: trimming trailing air
            # from a line should not shift the rest of the level sideways.
            row = list(raw.ljust(width, TILE_AIR))
            for tx in range(width):
                ch = row[tx]
                if ch not in ENTITY_CHARS:
                    continue
                self._place(ch, tx * C.TILE, ty * C.TILE)
                row[tx] = TILE_AIR
            self.grid.append(row)

    def _place(self, ch: str, px: float, py: float) -> None:
        if ch == "S":
            # Bottom-aligned in its tile, so a spawn marker drawn sitting on the
            # ground puts his feet on that ground.
            self.spawn = Marker(px + 1, py + C.TILE - C.PLAYER_H)
        elif ch == "E":
            self.exit = Rect(px, py - C.TILE, C.TILE, C.TILE * 2)
        elif ch == "o":
            self.notes.append(Pickup(px + 4, py + 4, 8, 8))
        elif ch in "TRON":
            self.letters.append(
                Pickup(px + 2, py + 2, C.TILE - 4, C.TILE - 4, ch=ch)
            )
        elif ch == "g":
            self.enemies.append(
                Marker(px, py + C.TILE - C.GARGOYLE_H, "gargoyle")
            )
        elif ch == "f":
            self.enemies.append(Marker(px, py, "flyer"))
        elif ch == "s":
            self.enemies.append(Marker(px, py + C.TILE - C.GARGOYLE_H, "statue"))
        elif ch == "b":
            self.bells.append(
                Marker(px + (C.TILE - C.BELL_W) / 2, py + (C.TILE - C.BELL_H) / 2)
            )
        elif ch == "c":
            self.trolleys.append(Marker(px, py + C.TILE - C.TROLLEY_H))

    # ── Reading the grid ────────────────────────────────────────────

    def tile_at(self, tx: int, ty: int) -> str:
        """The character at a tile.

        Off the left and right edges reads as solid, so a level is walled
        rather than open to an endless sideways fall. Above and below read as
        air: dropping out of the bottom is how a pit kills you.
        """
        if tx < 0 or tx >= self.cols:
            return TILE_SOLID
        if ty < 0 or ty >= self.rows:
            return TILE_AIR
        return self.grid[ty][tx]

    def tile_range(
        self, x: float, y: float, w: float, h: float
    ) -> tuple[int, int, int, int]:
        """Every tile a pixel-space box touches, as (tx0, ty0, tx1, ty1)."""
        return (
            math.floor(x / C.TILE),
            math.floor(y / C.TILE),
            math.floor((x + w - 1) / C.TILE),
            math.floor((y + h - 1) / C.TILE),
        )

    def overlaps(self, x: float, y: float, w: float, h: float, test) -> bool:
        tx0, ty0, tx1, ty1 = self.tile_range(x, y, w, h)
        for ty in range(ty0, ty1 + 1):
            for tx in range(tx0, tx1 + 1):
                if test(self.tile_at(tx, ty)):
                    return True
        return False

    def overlaps_solid(self, x: float, y: float, w: float, h: float) -> bool:
        """Does this box overlap brick? One-way platforms are not solid here."""
        return self.overlaps(x, y, w, h, is_solid_tile)

    def overlaps_water(self, x: float, y: float, w: float, h: float) -> bool:
        return self.overlaps(x, y, w, h, is_water_tile)

    def overlaps_updraft(self, x: float, y: float, w: float, h: float) -> bool:
        """Is any part of this box in rising air? Updraft tiles are not solid."""
        return self.overlaps(x, y, w, h, is_updraft_tile)

    def overlaps_rail(self, x: float, y: float, w: float, h: float) -> bool:
        """Is this box over rail? The trolley only rolls where there is track."""
        return self.overlaps(x, y, w, h, is_rail_tile)

    def has_footing(self, x: float, y: float, w: float, h: float) -> bool:
        """Is there footing directly under this box? Used by ledge-turning."""
        return self.overlaps_solid(x, y + h, w, 1) or self.overlaps(
            x, y + h, w, 1, is_platform_tile
        )

    def updraft_centre(self, x: float, y: float, w: float, h: float) -> float | None:
        """Horizontal centre of the updraft column this box is in, or None."""
        tx0, ty0, tx1, ty1 = self.tile_range(x, y, w, h)
        for ty in range(ty0, ty1 + 1):
            for tx in range(tx0, tx1 + 1):
                if is_updraft_tile(self.tile_at(tx, ty)):
                    return tx * C.TILE + C.TILE / 2
        return None

    def platform_top(
        self, x: float, y: float, w: float, h: float, prev_bottom: float
    ) -> float | None:
        """Top of the highest one-way platform this box has just landed on.

        ``prev_bottom`` is the whole of what makes it one-way: a platform only
        stops a body that was already above it, so you rise through the same
        tile you later stand on.
        """
        tx0, ty0, tx1, ty1 = self.tile_range(x, y, w, h)
        # Scan one row further down than the body occupies. tile_range stops at
        # (y + h - 1), so a body resting EXACTLY on a platform -- bottom flush
        # with the tile top -- never sees the tile holding it up, and sinks: the
        # first frame the tile is out of range, and by the second the playhead
        # has passed it and the came-from-above guard rejects it. Landing from a
        # height hides this, because a fast step crosses the boundary in one
        # move.
        bottom_row = math.floor((y + h) / C.TILE)
        best: float | None = None
        for ty in range(ty0, max(ty1, bottom_row) + 1):
            top = ty * C.TILE
            if prev_bottom > top + 0.001:
                continue  # came from below, or inside
            for tx in range(tx0, tx1 + 1):
                if is_platform_tile(self.tile_at(tx, ty)) and (
                    best is None or top < best
                ):
                    best = top
        return best

    # ── Moving through it ───────────────────────────────────────────

    def move_x(self, box: Box, dx: float) -> bool:
        """Move a body horizontally, stopping flush against brick.

        Stepped under a tile at a time so nothing can tunnel through a wall.
        Normal running never needs it -- 4.2px a frame at most -- but a stomp
        bounce plus knockback can exceed a tile in one step, and passing
        through a wall is the one bug that makes a platformer feel broken
        rather than merely hard.
        """
        if not dx:
            return False
        cap = C.TILE - 1
        step = sign(dx) * min(abs(dx), cap)
        remaining = dx
        hit = False

        while abs(remaining) > 0.0001:
            move = remaining if abs(remaining) < abs(step) else step
            nxt = box.x + move
            if self.overlaps_solid(nxt, box.y, box.w, box.h):
                box.x = (
                    math.floor((nxt + box.w) / C.TILE) * C.TILE - box.w
                    if move > 0
                    else (math.floor(nxt / C.TILE) + 1) * C.TILE
                )
                hit = True
                break
            box.x = nxt
            remaining -= move
        return hit

    def move_y(self, box: Box, dy: float, dropping: bool = False) -> Landing:
        """Move a body vertically. Reports which surface stopped it.

        ``dropping`` suppresses one-way platforms, for a body deliberately
        dropping through one.
        """
        result = Landing()
        if not dy:
            return result

        cap = C.TILE - 1
        step = sign(dy) * min(abs(dy), cap)
        remaining = dy

        while abs(remaining) > 0.0001:
            move = remaining if abs(remaining) < abs(step) else step
            prev_bottom = box.y + box.h
            nxt = box.y + move

            if self.overlaps_solid(box.x, nxt, box.w, box.h):
                if move > 0:
                    box.y = math.floor((nxt + box.h) / C.TILE) * C.TILE - box.h
                    result.ground = True
                else:
                    box.y = (math.floor(nxt / C.TILE) + 1) * C.TILE
                    result.ceiling = True
                break

            if move > 0 and not dropping:
                top = self.platform_top(box.x, nxt, box.w, box.h, prev_bottom)
                if top is not None:
                    box.y = top - box.h
                    result.ground = True
                    result.platform = True
                    break

            box.y = nxt
            remaining -= move
        return result


def overlap(
    ax: float, ay: float, aw: float, ah: float,
    bx: float, by: float, bw: float, bh: float,
) -> bool:
    """Axis-aligned box intersection, as ``entities.js`` defines it."""
    return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by

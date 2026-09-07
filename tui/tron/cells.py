"""World pixels onto character cells, and the camera that chooses the window.

This is the only module in the rules layer that knows a terminal exists, which
is the same split ``drift`` and ``jovian`` keep: :mod:`tron.config` names world
units and nothing else, and mixing the two is what produces a game that plays
differently at two window sizes.

**Two cells per tile.** A terminal cell is about twice as tall as it is wide,
so a 16px tile drawn 2 cells wide by 1 cell tall comes out square. That fixes
the scale: the web build's 30-tile viewport is 60 columns, and the playfield
fits inside the 80x24 the engine calls "the terminal that always exists".

The resolution is therefore 8 world pixels per column and 16 per row -- finer
horizontally than vertically, which is the wrong way round for a platformer,
where the question is usually whether you are above a ledge. Half-block glyphs
would halve the row to 8px and even the two up; :data:`CELL_H` is the one
number that changes if that is ever done, so it is named rather than inlined.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import config as C
from .tilemap import Tilemap

#: Character columns per tile. Two makes a tile square at a terminal's aspect.
CELLS_PER_TILE = 2

#: World pixels spanned by one character column.
CELL_W = C.TILE // CELLS_PER_TILE

#: World pixels spanned by one character row. Whole tiles today; halving this
#: to 8 is what a half-block renderer would do, and nothing else would change.
CELL_H = C.TILE

#: The web build's viewport, in tiles. 30 x 16.9 -- the second is not whole,
#: which is why the terminal's own row count is what actually decides height.
VIEW_TILES_X = C.CANVAS_W / C.TILE
VIEW_TILES_Y = C.CANVAS_H / C.TILE


def playfield_size(cols: int, rows: int) -> tuple[int, int]:
    """World pixels visible in a playfield of ``cols`` x ``rows`` cells."""
    return cols * CELL_W, rows * CELL_H


def min_cols_for(tiles: float = VIEW_TILES_X) -> int:
    """Columns needed to show ``tiles`` tiles. 60 for the web build's window."""
    return int(tiles * CELLS_PER_TILE)


@dataclass
class Camera:
    """Where the window sits in the level, in world pixels.

    A port of ``world.js``'s Camera, with one change: the web build hard-codes
    the 480x270 canvas as the view size, and here the view is whatever the
    terminal gives us. Everything else -- the dead zone, the look-ahead, the
    lerp, the clamp -- is the web build's, so the camera behaves the same way
    at the sizes the two happen to share.

    A dead zone stops small hops shoving the view around, and the look-ahead
    leads in the direction of travel, which is what buys reaction time at speed.
    """

    map: Tilemap
    view_w: float = C.CANVAS_W
    view_h: float = C.CANVAS_H
    x: float = 0.0
    y: float = 0.0

    def resize(self, view_w: float, view_h: float) -> None:
        self.view_w = view_w
        self.view_h = view_h
        self.clamp()

    def snap_to(self, player) -> None:
        self.x = player.box.x - self.view_w / 2
        self.y = player.box.y - self.view_h / 2
        self.clamp()

    def update(self, player, dt: float) -> None:
        px = player.box.x + player.box.w / 2 + player.facing * C.CAM_LOOKAHEAD
        py = player.box.y + player.box.h / 2

        want_x = px - self.view_w / 2
        want_y = py - self.view_h / 2

        if abs(want_x - self.x) > C.CAM_DEADZONE_X:
            target = want_x - _sign(want_x - self.x) * C.CAM_DEADZONE_X
            self.x += (target - self.x) * min(1.0, C.CAM_LERP * dt)
        if abs(want_y - self.y) > C.CAM_DEADZONE_Y:
            target = want_y - _sign(want_y - self.y) * C.CAM_DEADZONE_Y
            self.y += (target - self.y) * min(1.0, C.CAM_LERP * dt)
        self.clamp()

    def clamp(self) -> None:
        """Never show past the edges of the level."""
        self.x = max(0.0, min(self.map.w - self.view_w, self.x))
        self.y = max(0.0, min(self.map.h - self.view_h, self.y))
        # A level smaller than the window pins to the origin rather than going
        # negative, which is what the max/min above would otherwise produce.
        if self.map.w < self.view_w:
            self.x = 0.0
        if self.map.h < self.view_h:
            self.y = 0.0

    # ── Projection ──────────────────────────────────────────────────

    def to_cell(self, x: float, y: float) -> tuple[int, int]:
        """A world point as (col, row) in the playfield. May be off-screen."""
        return int((x - self.x) // CELL_W), int((y - self.y) // CELL_H)

    def tile_window(self, cols: int, rows: int) -> tuple[int, int, int, int]:
        """The tile range this camera shows, as (tx0, ty0, tx1, ty1).

        Inclusive, and clipped to the level. One tile of bleed either side, so
        a body straddling the edge is drawn rather than popping in.
        """
        tx0 = max(0, int(self.x // C.TILE) - 1)
        ty0 = max(0, int(self.y // C.TILE) - 1)
        tx1 = min(self.map.cols - 1, int((self.x + cols * CELL_W) // C.TILE) + 1)
        ty1 = min(self.map.rows - 1, int((self.y + rows * CELL_H) // C.TILE) + 1)
        return tx0, ty0, tx1, ty1


def _sign(n: float) -> float:
    if n > 0:
        return 1.0
    if n < 0:
        return -1.0
    return 0.0

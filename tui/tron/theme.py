"""Palette, layout and glyphs — everything in character cells.

Split out so :mod:`tron.scenes` and :mod:`tron.app` can share it without
importing each other. Nothing here imports the engine.

The palette is the web build's ``CONFIG.COLORS`` from ``js/config.js``: an
1810s Dutch city at night. **Every measurement here is cells, not world
pixels.** The 480x270 world lives in :mod:`tron.config` and :mod:`tron.cells`
maps between them; the two spaces stay in separate modules on purpose.

── The glyphs ──

Two rules, and both are about what survives a terminal that cannot encode
Unicode. Every non-ASCII character below is in the engine's fallback table
(:mod:`magmacrunch.engine.ui.glyphs`), and ``tests/test_ascii.py`` is what
keeps that true rather than the intention.

The second rule is the more interesting one: **entities are drawn as their
own level-file legend characters**. A gargoyle is ``g`` because ``g`` is what
it is in ``levels.js``. That is not a shortage of imagination -- the level art
and the terminal render are the same grid, which is the whole reason this
port was worth doing, and a reader with the level file open sees the screen
they are editing. It also means the entity set needs no fallbacks at all,
because it is already ASCII.

Terrain gets the same treatment by accident, and it is worth noticing: the
fallback for ``█`` is ``#`` and the fallback for ``↑`` is ``^``, which are
exactly the characters those tiles have in the level file. A terminal with no
Unicode does not degrade to something approximate here. It degrades to the
source.
"""

from __future__ import annotations

# ── Palette ─────────────────────────────────────────────────────────
# Transcribed from web/js/config.js.

SKY = "#1a1028"
SKY_HORIZON = "#3a1830"
CANAL = "#0d2a4a"

BRICK = "#6a2820"
BRICK_DARK = "#4a1810"
BRICK_LIT = "#8a3a2c"
ROOF_TILE = "#8a4020"
GABLE_STONE = "#7a5a48"
WINDOW_LIT = "#ffcf6a"
GAS_LAMP = "#ffe03a"

ROBOT_CYAN = "#00f5ff"
ROBOT_STEEL = "#8899aa"
MUTTON_CHOPS = "#cc6620"

GARGOYLE_STONE = "#6a6a80"
GARGOYLE_EYE = "#ff3d6e"
FLYER_WING = "#3a3a52"
STATUE_STONE = "#8a8a9c"

NOTE_WHITE = "#f0ead8"
LETTER_GOLD = "#ffd24a"
BIRD_BRASS = "#c8a24a"

HUD_TEXT = "#f0ead8"
HUD_DIM = "#7a6e84"
LIFE_HEART = "#ff3d6e"
EXIT_GLOW = "#7affc8"
WARN = "#ff3d6e"

BELL_BRASS = "#c9a227"
UPDRAFT = "#ffe0a0"
RAIL_IRON = "#5b5f70"
TROLLEY_BODY = "#4a3428"
TROLLEY_IRON = "#8892a4"

TITLE = "#ffcf6a"
SUBTITLE = "#00f5ff"
MENU_BOX = "#1a1028"
MENU_SELECTED = "#ffcf6a"
MENU_SELECTION_BG = "#3a1830"

# ── Layout ──────────────────────────────────────────────────────────

#: Level name, score, notes and lives.
HEADER_ROWS = 1
#: The key hints.
FOOTER_ROWS = 1

#: Smallest terminal the game draws in.
#:
#: **The widest floor of any cabinet here**, and it is not arbitrary: the web
#: viewport is 30 tiles, a tile is two cells wide so that it comes out square
#: at a terminal's aspect, and 30 x 2 is 60. Below that the camera would show
#: less of the level than the browser does, and the levels were authored
#: against what the browser shows -- a gap you cannot see the far side of is a
#: leap of faith rather than a jump.
#:
#: The too-small screen names this number, because a player who is told
#: "60x16" can fix it and a player who is told "too small" cannot.
MIN_COLS = 60
MIN_PLAYFIELD_ROWS = 14
MIN_ROWS = HEADER_ROWS + MIN_PLAYFIELD_ROWS + FOOTER_ROWS

MENU_MIN_COLS = 40
MENU_MIN_ROWS = 16

# Menu geometry in cells, passed to the engine's Menu widget in place of its
# pixel defaults, which would sit entirely off-screen.
MENU_W = 30
MENU_ITEM_H = 1
MENU_TITLE_H = 0
MENU_PAD = 1
MENU_BORDER = 1

BANNER = "RODERICK TRON"
TAGLINE = "a clockwork gentleman on the rooftops"

#: How the name is set, best first. Every rung spells the whole name.
TITLE_LADDER = (
    ("RODERICK\nTRON", ""),
    ("RODERICK", "TRON"),
    ("TRON", "RODERICK"),
)

# ── Terrain glyphs ──────────────────────────────────────────────────
#
# All four have fallbacks, and three of the four fall back to the character
# the level file already uses for that tile.

#: Solid brick. Falls back to ``#``.
SOLID = "█"
#: A one-way platform: you rise through it and stand on it. The upper half
#: block sits in the top half of the cell, which is where the surface is.
#: Falls back to ``"``, still a thin mark high in the cell.
PLATFORM = "▀"
#: Rail. Falls back to ``-``, which is its level-file character.
RAIL = "─"
#: A column of rising air. Falls back to ``^``, its level-file character.
UPDRAFT_GLYPH = "↑"
#: Canal water, fatal. Already ASCII and already the level-file character.
WATER = "~"

# ── Entity glyphs ───────────────────────────────────────────────────
#
# The level file's own legend, so the screen and the source agree. All ASCII.

GARGOYLE = "g"
FLYER = "f"
STATUE = "s"
BELL = "b"
TROLLEY_GLYPH = "[o]"
NOTE = "."
#: The letters spell the game's name, and they are their own glyphs.
LETTERS = "TRON"

#: Roderick. Not ``S`` -- that is the spawn marker in the level file, and this
#: is the one thing on screen that is not terrain. ``@`` is what a terminal
#: game has always called the player, and it needs no fallback.
PLAYER = "@"
#: Tucked into a ball. One cell tall as well as one wide, which is the point
#: of a roll: it fits a gap standing up does not.
PLAYER_ROLLING = "o"
#: A fired note.
SHOT = "*"
#: The clockwork bird, trailing behind him.
BIRD = "v"

#: The exit, drawn as a door two rows tall. Both halves are in the engine's
#: box group, which degrades as a unit -- so the door is never half ASCII.
EXIT_TOP = "┌┐"
EXIT_BOTTOM = "││"

#: Lives. In the engine's suits group, falling back to ``H``.
LIFE = "♥"

__all__ = [
    "BANNER", "BELL", "BELL_BRASS", "BIRD", "BIRD_BRASS", "BRICK",
    "BRICK_DARK", "BRICK_LIT", "CANAL", "EXIT_BOTTOM", "EXIT_GLOW",
    "EXIT_TOP", "FLYER", "FLYER_WING", "FOOTER_ROWS", "GABLE_STONE",
    "GARGOYLE", "GARGOYLE_EYE", "GARGOYLE_STONE", "GAS_LAMP", "HEADER_ROWS",
    "HUD_DIM", "HUD_TEXT", "LETTERS", "LETTER_GOLD", "LIFE", "LIFE_HEART",
    "MENU_BORDER", "MENU_BOX", "MENU_ITEM_H", "MENU_MIN_COLS",
    "MENU_MIN_ROWS", "MENU_PAD", "MENU_SELECTED", "MENU_SELECTION_BG",
    "MENU_TITLE_H", "MENU_W", "MIN_COLS", "MIN_PLAYFIELD_ROWS", "MIN_ROWS",
    "MUTTON_CHOPS", "NOTE", "NOTE_WHITE", "PLATFORM", "PLAYER",
    "PLAYER_ROLLING", "RAIL", "RAIL_IRON", "ROBOT_CYAN", "ROBOT_STEEL",
    "ROOF_TILE", "SHOT", "SKY", "SKY_HORIZON", "SOLID", "STATUE",
    "STATUE_STONE", "SUBTITLE", "TAGLINE", "TITLE", "TITLE_LADDER",
    "TROLLEY_BODY", "TROLLEY_GLYPH", "TROLLEY_IRON", "UPDRAFT",
    "UPDRAFT_GLYPH", "WARN", "WATER", "WINDOW_LIT",
]

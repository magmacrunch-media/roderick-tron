"""The game on a terminal that can encode nothing.

The engine substitutes in the renderer, so this game asks the question of
nobody — but it can still *draw* a character the engine's table has never
heard of, and then the substitution has nothing to substitute. That is not
hypothetical: Jovian shipped its transponder as a heavy cross first, which is
exactly the glyph with no fallback, and the transponder was the channel its
whole fairness guarantee was written against.

The sweep below is the guard. It is worth more in this cabinet than in the
others, because here the *terrain* is glyphs — a playfield of sixty columns
drawn out of block and box characters every frame, rather than a few markers
on a mostly-text screen.
"""

from __future__ import annotations

import ast
import pathlib
import unicodedata

import pytest

pytest.importorskip("textual", reason='needs: pip install -e ".[dev]"')

from magmacrunch.engine.ui.glyphs import FALLBACKS, GROUPS, Glyphs  # noqa: E402

from tron import theme  # noqa: E402

PACKAGE = pathlib.Path(__file__).resolve().parent.parent / "tron"


def _drawn_literals(path):
    """Every string literal that is not a docstring.

    Comments fall out for free — they are not literals — and docstrings are
    excluded because prose *about* a glyph is not a glyph being drawn.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docs = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                docs.add(doc)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value not in docs
        ):
            yield node.value


def test_every_glyph_this_game_draws_has_a_fallback():
    """The engine's own sweep covers the launcher, not the cabinets."""
    missing: dict[str, set[str]] = {}
    for path in sorted(PACKAGE.glob("*.py")):
        for literal in _drawn_literals(path):
            for char in literal:
                if ord(char) > 126 and char not in FALLBACKS:
                    missing.setdefault(char, set()).add(path.name)

    assert not missing, "glyphs drawn with no fallback: " + ", ".join(
        f"U+{ord(c):04X} {unicodedata.name(c, '?')} in {sorted(w)}"
        for c, w in sorted(missing.items())
    )


def test_terrain_degrades_to_the_level_files_own_characters():
    """The nicest accident in the port, kept honest.

    ``█`` falls back to ``#`` and ``↑`` to ``^`` — which are exactly what
    those tiles are called in ``levels.js``. On a terminal with no Unicode the
    playfield does not degrade to something approximate; it degrades to the
    source. This is worth a test because it is the sort of pleasing property
    that gets broken by an innocent-looking glyph swap.
    """
    assert FALLBACKS[theme.SOLID] == "#"
    assert FALLBACKS[theme.UPDRAFT_GLYPH] == "^"
    assert FALLBACKS[theme.RAIL] == "-"
    # Water needs no fallback: it is already its own level-file character.
    assert theme.WATER == "~"


def test_the_door_degrades_as_one_piece():
    """Both halves of the exit are in the same group, so it is never half ASCII.

    The engine's ``box`` group exists because 0.7.0 shipped a card with ASCII
    sides and Unicode corners. A door drawn from two groups would fail the
    same way, one row at a time.
    """
    chars = set(theme.EXIT_TOP + theme.EXIT_BOTTOM)
    groups = {
        name for name, table in GROUPS.items() if chars & set(table)
    }
    assert groups == {"box"}, f"the door spans {sorted(groups)}"


def test_entities_need_no_fallback_at_all():
    """They are their own level-file legend characters, so they are ASCII."""
    for glyph in (
        theme.GARGOYLE, theme.FLYER, theme.STATUE, theme.BELL,
        theme.TROLLEY_GLYPH, theme.NOTE, theme.PLAYER,
        theme.PLAYER_ROLLING, theme.SHOT, theme.BIRD, theme.LETTERS,
    ):
        assert all(ord(c) <= 126 for c in glyph), f"{glyph!r} is not ASCII"


def test_every_substitute_is_one_cell():
    """A stand-in of a different width moves everything drawn after it.

    In a text screen that is untidy. In a playfield drawn cell by cell it is a
    level that no longer lines up with its own collision.
    """
    for fancy, plain in FALLBACKS.items():
        assert len(plain) == 1, f"{fancy!r} -> {plain!r} is not one cell"


def test_the_ascii_face_of_a_tile_row_keeps_its_width():
    """A row of terrain must measure the same either way.

    Two cells per tile is what makes a tile square, and every column after a
    mis-sized glyph would be off by one — the collision would be right and the
    picture wrong, which is the worst way for this to fail.
    """
    plain = Glyphs.detect(ascii_only=True)
    for glyph in (theme.SOLID, theme.PLATFORM, theme.RAIL, theme.UPDRAFT_GLYPH):
        row = glyph * 30
        assert len(plain.translate(row, FALLBACKS)) == len(row)

"""What the arcade needs to know to launch this game.

The entry point a launcher resolves. Kept tiny and free of imports that cost
anything: a menu listing several games loads one of these per installed game
just to draw a row, and it should not pay for the game's rules or its screens
to do that.
"""

from __future__ import annotations

from typing import Any

from magmacrunch.engine.arcade import GameInfo

from tron import theme

INFO = GameInfo(
    key="roderick-tron",
    title="Roderick Tron",
    blurb="A clockwork gentleman on the rooftops. Mind the seven-tile gap.",
    # 60 rather than 30, and this is the one cabinet that needs it. The
    # constants are all per-60fps-frame and the conversion in scenes.py makes
    # the simulation frame-rate independent either way -- but a jump is 33
    # frames of arc quantised to five cell rows, and sampling that at 30fps
    # halves the number of distinct positions the eye gets to see. A platformer
    # is judged on whether you can read an arc well enough to land on a tile.
    fps=60,
    # **Short on purpose, and the short side of a real bind.**
    #
    # A keyboard sends one press then goes quiet for its repeat delay -- about
    # 500ms -- before repeating. TuiInput approximates a held key by keeping
    # the button set for hold_ms, so a value under the delay leaves a gap in
    # the middle of a held direction, and a value over it leaves a tail after a
    # genuine release: 550ms of tail is nearly six tiles of coasting past where
    # the player let go.
    #
    # Over a pit the tail is fatal and the gap is merely ugly, so this takes
    # the gap. 260ms of tail is about 2.8 tiles at a full run, which coyote
    # time and a jump can still recover from.
    #
    # What makes the gap survivable is that it does not cost the run-up:
    # tron.config.CHARGE_GRACE_FRAMES lets the earned-speed ramp ride out the
    # silence even though the movement does not. Movement and momentum wanted
    # opposite answers, so they were given separate ones.
    hold_ms=260,
    min_cols=theme.MIN_COLS,
    min_rows=theme.MIN_ROWS,
)


class TronGame:
    """Satisfies :class:`magmacrunch.engine.arcade.ArcadeGame`."""

    info = INFO

    def start(self, host: Any) -> Any:
        """The title screen, ready to be pushed.

        Imported here rather than at module scope so that listing this game in
        an arcade menu does not drag in its rules, its screens, or Textual.
        """
        from tron.app import TronApp

        return TronApp(host).root_scene


#: What the entry point resolves to. Stateless — a run's state belongs to the
#: TronApp that :meth:`TronGame.start` creates, so replaying makes a new one.
GAME = TronGame()

__all__ = ["GAME", "INFO", "TronGame"]

"""The web build's 480x270 world, and the only coordinate space the rules know.

Every constant here is transcribed from ``web/js/config.js``, which stays the
source of truth for rules and tuning. ``tests/test_physics.py`` reads that file
and compares the two, so a number changed in one place and not the other is a
test failure rather than a divergence somebody notices in a year.

**The terminal's own size is deliberately not named in this module**, the same
rule ``drift.config`` and ``jovian.config`` follow: the moment world units and
character cells have constants in the same file they get mixed, and the bug
that produces is a game that plays differently at two window sizes. Cells live
in :mod:`tron.cells`.

**Per-frame convention, inherited from the web build.** Every rate here is
expressed in units per 60fps frame and is multiplied by ``dt`` at the point of
use, so the simulation runs identically at 30fps in a terminal and at 144Hz in
a browser. Anything measured in frames -- a cooldown, a coyote window -- is
likewise a count of 60fps frames and is decremented by ``dt``, not by 1. The
engine's loop defaults to 30fps and hands out ``dt`` in *seconds*, so the
caller multiplies by :data:`FRAMES_PER_SECOND` exactly once, at the top of
:meth:`tron.player.Player.update`. Jovian shipped without that conversion and
ran sixty times too slow.

Two constants from the web build are deliberately absent, because the terminal
cannot deliver the input they read. Both are argued in full in the docstrings
that replace them -- see :data:`RUN_CHARGE_FRAMES` and
:meth:`tron.player.Player.update`.
"""

from __future__ import annotations

#: Frames per second the constants below are written against. The engine passes
#: ``dt`` in seconds; multiplying by this converts it to the web build's units.
FRAMES_PER_SECOND = 60.0

CANVAS_W = 480
CANVAS_H = 270
TILE = 16  # 30 x 16.9 tiles on screen

# ── Player body ─────────────────────────────────────────────────────
#
# 14 wide fits a one-tile gap with room to spare; 22 tall is taller than a tile
# and shorter than two, so a two-tile opening is passable and a one-tile one is
# not. Every level's geometry reads off that.
PLAYER_W = 14
PLAYER_H = 22

# ── Ground movement ─────────────────────────────────────────────────
#
# Acceleration and friction rather than instant velocity: the weight is most of
# what separates this from the runner it replaced.
WALK_MAX = 1.55
RUN_MAX = 2.85
ROLL_MAX = 4.20
ACCEL = 0.30
AIR_ACCEL = 0.17  # less authority in the air, so commitment matters
FRICTION = 0.34
AIR_FRICTION = 0.06
TURN_BOOST = 1.7  # reversing bites harder than accelerating

#: Frames of sustained travel that take the speed cap from :data:`WALK_MAX` to
#: :data:`RUN_MAX`.
#:
#: **This constant exists because a terminal cannot report a held modifier.**
#: The web build runs while SHIFT is down, and a terminal delivers SHIFT only
#: as a modifier on some *other* key -- there is no bare shift-is-down event to
#: read. Dropping the verb outright was not an option: the levels are built on
#: three distinct jump distances (walk 3.08, run 5.67, roll 8.35 tiles) against
#: authored gaps of 3, 4, 6 and 7 tiles, so collapsing run into walk makes two
#: gaps in ROOFTOP REQUIEM uncrossable.
#:
#: So speed is earned by holding a direction instead of by holding a modifier.
#: The cap ramps while he travels one way on the ground and resets when he
#: turns or stops, which turns "hold shift" into "commit to a run-up" -- the
#: thing the level geometry was already asking for, since every gap has one.
#:
#: 44 frames rather than a rounder number because of what it has to fit inside.
#: Ramping linearly from 1.55 to 2.85 averages 2.2px a frame, so full speed
#: arrives about 97px along -- six tiles. The tightest run-up in any level is
#: the nine tiles before ROOFTOP REQUIEM's seven-tile gap, which leaves three
#: tiles of margin. ``test_earned_speed_fits_the_tightest_runup`` pins it.
RUN_CHARGE_FRAMES = 44

# ── Jump ────────────────────────────────────────────────────────────
#
# Airtime is 2*|v|/g frames and height v^2/(2g) px. Height is what the level's
# vertical geometry reads off; AIRTIME is what its gaps read off, and it is the
# one worth tuning for.
#
# The web build's JUMP_CUT is absent: it multiplies upward velocity by 0.45
# when the jump key is *released*, and a terminal never reports a release. That
# costs expression rather than clearance -- walking every standable tile in all
# three levels finds no place where a full jump hits a ceiling, so nothing
# authored needs a clipped one. ``test_no_level_needs_a_clipped_jump`` is that
# measurement, kept as a test so a fourth level cannot quietly break it.
GRAVITY = 0.44
JUMP_FORCE = -7.0
MAX_FALL = 7.2
COYOTE_FRAMES = 6
JUMP_BUFFER_FRAMES = 8
STOMP_BOUNCE = -5.6  # the hop you get off a flattened enemy
STOMP_BOUNCE_HELD = -7.4  # ...higher if you were holding jump, as in DKC

#: Airtime of a full jump, in 60fps frames.
JUMP_AIRTIME = 2 * abs(JUMP_FORCE) / GRAVITY

#: Apex of a full jump, in world pixels. 59.2 -- three and a half tiles.
JUMP_HEIGHT = (JUMP_FORCE * JUMP_FORCE) / (2 * GRAVITY)

# ── Roll ────────────────────────────────────────────────────────────
#
# The skill move. It kills on contact, and rolling off a ledge carries the
# speed into the jump -- which is how the longest gaps are meant to be crossed,
# and the reason a roll has to be committal rather than free.
ROLL_FRAMES = 34
ROLL_COOLDOWN = 14
ROLL_H = 14  # shorter while rolling: fits a one-tile gap

# ── Bell cannon ─────────────────────────────────────────────────────
#
# It catches you, swings through an arc overhead, and fires along whatever
# angle it is pointing when you press jump -- so the timing is the skill, and
# no extra level syntax is needed to encode an aim.
BELL_W = 20
BELL_H = 20
BELL_SWING_FROM = -155.0  # degrees; -90 is straight up
BELL_SWING_TO = -25.0
BELL_SWING_RATE = 0.030  # radians of phase per frame
BELL_LAUNCH = 10.0  # px/frame; at 45 degrees that flies v^2/g = 227px
BELL_RECAPTURE = 26  # frames before the same bell can catch you again

# ── Chimney updraft ─────────────────────────────────────────────────
#
# Warm air off a chimney. Not a jump: a sustained climb, which is how a level
# gets to reach upward at all when a jump only clears 59px. Must exceed
# GRAVITY, or the column pushes DOWN.
UPDRAFT_LIFT = 0.98
UPDRAFT_MAX_RISE = 2.6  # terminal upward speed inside a column
UPDRAFT_DRIFT = 0.06  # gentle sideways settling toward the centre

# ── Coal trolley ────────────────────────────────────────────────────
#
# A sub-mode rather than a device: while you are aboard, the only verb is jump,
# and the level is a rail with holes in it. Speed is constant on purpose -- a
# cart you can slow down is a cart you can wait out.
TROLLEY_W = 22
TROLLEY_H = 14
TROLLEY_SPEED = 3.4
TROLLEY_JUMP = -7.6  # a shade stronger than his own: it carries load
TROLLEY_DECEL = 0.10  # once off the rails, it rolls to a halt
TROLLEY_DISMOUNT = 1.0  # ...and below this speed he steps off

# ── Combat ──────────────────────────────────────────────────────────
NOTE_SPEED = 4.4
NOTE_W = 6
NOTE_H = 8
NOTE_LIFE = 70
FIRE_RATE = 14
NOTE_AMMO_START = 5
NOTE_AMMO_MAX = 20
# Collecting is what reloads you, so exploring for notes and fighting are the
# same activity rather than two unrelated ones.
AMMO_PER_PICKUP = 1

# ── Enemies ─────────────────────────────────────────────────────────
GARGOYLE_W = 14
GARGOYLE_H = 14
GARGOYLE_SPEED = 0.42
GARGOYLE_HP = 1
FLYER_SPEED = 0.55
FLYER_BOB_AMP = 18
FLYER_BOB_RATE = 0.045
FLYER_HP = 1
STATUE_HP = 3  # the heavy one: stomp bounces off, notes needed

# ── Damage ──────────────────────────────────────────────────────────
INVINCIBLE_FRAMES = 96
KNOCKBACK_X = 2.2
KNOCKBACK_Y = -3.4
MAX_LIVES = 3
FALL_KILL_MARGIN = 40  # px below the level before it counts as a fall

# ── Companion ───────────────────────────────────────────────────────
#
# Having it is one free hit; losing it is visible and recoverable, which is a
# gentler failure curve than spending a life.
BIRD_FOLLOW_LAG = 0.12
BIRD_BOB_RATE = 0.09
BIRD_BOB_AMP = 3

# ── Collectibles ────────────────────────────────────────────────────
NOTES_PER_LIFE = 100
NOTE_POINTS = 10
LETTER_POINTS = 200
KILL_POINTS = 50
EXIT_POINTS = 500

# ── Camera ──────────────────────────────────────────────────────────
#
# A dead zone, so small hops do not shove the view around. It leads in the
# direction of travel, which is what buys reaction time at speed.
CAM_DEADZONE_X = 40
CAM_DEADZONE_Y = 28
CAM_LOOKAHEAD = 46
CAM_LERP = 0.10

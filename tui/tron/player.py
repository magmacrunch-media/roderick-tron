"""Roderick: momentum, roll, stomp, damage.

A port of ``web/js/player.js``, with the two changes the terminal forces. Both
are argued where they happen rather than here, and both are pinned by tests:

* the jump is fixed-height, because ``JUMP_CUT`` reads a key *release*;
* the run is earned by travelling, because SHIFT is not deliverable as a held
  key.

Every per-frame quantity is multiplied by ``dt``, which is 1.0 at 60fps. The
runner this replaced applied dt to gravity but not to the position step and ran
at double speed on a 120Hz display; keeping the discipline is cheaper than
rediscovering that.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import config as C
from .tilemap import Box, Tilemap, sign


@dataclass
class Intent:
    """One frame of input, already reduced to what the rules care about.

    Deliberately not the engine's ``InputState``: :mod:`tron.player` imports
    nothing outside the standard library, and a test proves it. The adapter
    that fills this in from a terminal lives with the scenes.

    ``left``/``right``/``down`` are *held* (a terminal approximates that by
    decay); ``jump``/``roll``/``fire`` are *edges*, true only on the frame the
    key went down.
    """

    left: bool = False
    right: bool = False
    down: bool = False
    jump: bool = False
    roll: bool = False
    fire: bool = False

    @property
    def dir(self) -> int:
        """-1, 0 or 1. Both directions at once cancels, as in the web build."""
        return (1 if self.right else 0) - (1 if self.left else 0)


NEUTRAL = Intent()


@dataclass
class Player:
    """Roderick. Owns his body and his timers; the map owns the geometry."""

    map: Tilemap
    box: Box = field(init=False)

    def __post_init__(self) -> None:
        self.reset(self.map.spawn)
        self.lives = C.MAX_LIVES
        self.notes = 0
        self.ammo = C.NOTE_AMMO_START

    def reset(self, spawn) -> None:
        self.box = Box(spawn.x, spawn.y, C.PLAYER_W, C.PLAYER_H)
        self.vx = 0.0
        self.vy = 0.0
        self.facing = 1
        self.grounded = False
        self.coyote = 0.0
        self.jump_buffer = 0.0
        self.jumping = False
        self.rolling = False
        self.roll_timer = 0.0
        self.roll_cooldown = 0.0
        self.invincible = 0.0
        self.shoot_cooldown = 0.0
        self.alive = True
        self.has_bird = True
        self.anim_timer = 0.0
        self.run_frame = 0
        self.shake_frames = 0.0
        self.exiting = False
        self.in_updraft = False
        #: Frames of sustained travel in :attr:`charge_dir`. See
        #: :data:`tron.config.RUN_CHARGE_FRAMES`.
        self.charge = 0.0
        self.charge_dir = 0
        #: Set while a bell holds him. Normal physics is suspended: the bell
        #: owns his position until it fires.
        self.captured = None
        #: Set while a trolley carries him. Like capture, normal physics is
        #: suspended, but unlike capture jump still does something, because
        #: jump is the whole of the sub-mode.
        self.riding = None
        #: Cues raised this frame. The web build calls ``Sfx.play`` here; a
        #: terminal has no audio, so they are collected for whatever wants
        #: them and cleared at the top of every update.
        self.cues: list[str] = []

    # ── Stance ──────────────────────────────────────────────────────

    def target_height(self) -> float:
        """Height depends on stance: rolling tucks him into a one-tile gap."""
        return C.ROLL_H if self.rolling else C.PLAYER_H

    def can_stand(self) -> bool:
        """Is there room to stand up out of a roll where he is?"""
        if not self.rolling:
            return True
        grow = C.PLAYER_H - C.ROLL_H
        return not self.map.overlaps_solid(
            self.box.x, self.box.y - grow, self.box.w, C.PLAYER_H
        )

    def headroom_adjust(self) -> None:
        """Resize the body around its feet when the stance changes."""
        bottom = self.box.y + self.box.h
        self.box.h = self.target_height()
        self.box.y = bottom - self.box.h

    def _stop_rolling(self) -> None:
        self.rolling = False
        self.roll_cooldown = C.ROLL_COOLDOWN
        self.headroom_adjust()

    # ── Earned speed ────────────────────────────────────────────────

    def max_speed(self) -> float:
        """The horizontal cap, which a roll overrides and travel raises.

        The web build reads SHIFT here. A terminal cannot report a held
        modifier, so the cap ramps from :data:`~tron.config.WALK_MAX` to
        :data:`~tron.config.RUN_MAX` across
        :data:`~tron.config.RUN_CHARGE_FRAMES` of sustained travel instead.
        Turning or stopping drops it back to a walk, which is what makes a
        run-up a decision rather than a formality.
        """
        if self.rolling:
            return C.ROLL_MAX
        t = min(1.0, self.charge / C.RUN_CHARGE_FRAMES)
        return C.WALK_MAX + (C.RUN_MAX - C.WALK_MAX) * t

    def _accrue_charge(self, direction: int, dt: float) -> None:
        if direction == 0 or direction != self.charge_dir:
            # Stopping or turning spends it. Reversing especially: TURN_BOOST
            # already makes a direction change bite, and letting the charge
            # survive one would make a run something you switch on once and
            # never lose.
            self.charge = 0.0
            self.charge_dir = direction
            return
        # Only the ground builds speed. Airborne it is held rather than reset,
        # so a running jump lands still running instead of touching down at a
        # walk with the momentum it earned still in vx.
        #
        # Read through `coyote`, not `grounded`. A body at rest on flat brick
        # alternates grounded True/False every single frame: gravity sinks it
        # 0.44px, which is not enough for the bottom-1 row of tile_range to
        # cross into the floor tile, so the next step snaps it back. The web
        # build does exactly the same thing -- it is sub-pixel and invisible
        # there because nothing counts grounded frames. Here it would halve
        # every run-up. `coyote` is refreshed on each of those landings and so
        # stays positive throughout, which is what "on the ground, or only
        # just off it" actually means.
        if self.grounded or self.coyote > 0:
            self.charge = min(C.RUN_CHARGE_FRAMES, self.charge + dt)

    # ── Per-frame ───────────────────────────────────────────────────

    def update(self, intent: Intent, dt: float) -> None:
        self.cues.clear()
        if not self.alive:
            return

        # Carried. Timers still run; position belongs to the carrier.
        if self.riding is not None:
            self._tick_carried_timers(dt)
            self.anim_timer += dt
            return

        # Held by a bell. Timers still run -- invincibility should not pause
        # while he waits for the swing -- but nothing else does; the bell
        # places him.
        if self.captured is not None:
            self._tick_carried_timers(dt)
            self.vx = 0.0
            self.vy = 0.0
            return

        direction = intent.dir

        # ── Timers ──────────────────────────────────────────────────
        if self.coyote > 0:
            self.coyote -= dt
        if self.jump_buffer > 0:
            self.jump_buffer -= dt
        if self.roll_cooldown > 0:
            self.roll_cooldown -= dt
        if self.invincible > 0:
            self.invincible -= dt
        if self.shoot_cooldown > 0:
            self.shoot_cooldown -= dt
        if self.shake_frames > 0:
            self.shake_frames -= dt
        if intent.jump:
            self.jump_buffer = C.JUMP_BUFFER_FRAMES

        # ── Roll ────────────────────────────────────────────────────
        # Committal on purpose: it locks facing and steering for its duration,
        # so the reward for the extra distance is that you had to mean it.
        if (intent.roll and not self.rolling
                and self.roll_cooldown <= 0 and self.grounded):
            self.rolling = True
            self.roll_timer = C.ROLL_FRAMES
            if direction != 0:
                self.facing = direction
            self.vx = self.facing * C.ROLL_MAX
            self.headroom_adjust()
            self.cues.append("roll")

        if self.rolling:
            self.roll_timer -= dt
            direction = self.facing  # no steering mid-roll
            if self.roll_timer <= 0 and self.can_stand():
                self._stop_rolling()

        self._accrue_charge(direction, dt)

        # ── Horizontal ──────────────────────────────────────────────
        max_speed = self.max_speed()
        accel = C.ACCEL if self.grounded else C.AIR_ACCEL

        if direction != 0:
            if not self.rolling:
                self.facing = direction
            # Turning bites harder than accelerating, which is what stops a
            # direction change feeling like a slow drift through zero.
            turning = sign(self.vx) != 0 and sign(self.vx) != direction
            a = accel * (C.TURN_BOOST if turning else 1)
            nxt = self.vx + direction * a * dt

            if abs(nxt) < abs(self.vx) or abs(nxt) <= max_speed:
                # Slowing down, or still inside the cap.
                self.vx = nxt
            elif abs(self.vx) <= max_speed:
                self.vx = sign(nxt) * max_speed
            else:
                # Already over the cap, which only a roll can do. Holding the
                # stick must NOT add to it -- an earlier version let it, and
                # since AIR_ACCEL (0.17) is larger than AIR_FRICTION (0.06) a
                # held direction accelerated without limit: 10.8px a frame
                # against a 2.85 cap, straight through the level. Overspeed
                # decays toward the cap and nothing pushes it back up.
                #
                # Bleeds on the ground only. In the air the speed a roll earned
                # is kept for the whole arc, which is what makes a roll-jump a
                # technique rather than a marginal gain.
                bleed = C.FRICTION * dt if self.grounded else 0.0
                self.vx = sign(self.vx) * max(max_speed, abs(self.vx) - bleed)
        else:
            f = (C.FRICTION if self.grounded else C.AIR_FRICTION) * dt
            if abs(self.vx) <= f:
                self.vx = 0.0
            else:
                self.vx -= sign(self.vx) * f

        # ── Jump ────────────────────────────────────────────────────
        #
        # Fixed height. The web build multiplies vy by JUMP_CUT when the key is
        # released, and a terminal never reports a release -- so there is no
        # moment at which a cut could be applied, and inventing one (a timer, a
        # second key) would be a different control rather than the same one
        # degraded. Measured against the levels this costs nothing: no
        # standable tile in any of the three has a ceiling inside jump height.
        if self.jump_buffer > 0 and self.coyote > 0:
            self.vy = C.JUMP_FORCE
            self.grounded = False
            self.jumping = True
            self.jump_buffer = 0.0
            self.coyote = 0.0
            self.cues.append("jump")
            # A roll converted into a jump keeps its speed: this is the
            # long-gap technique the levels are built around.
            if self.rolling and self.can_stand():
                self._stop_rolling()

        # ── Gravity and movement ────────────────────────────────────
        self.vy += C.GRAVITY * dt
        if self.vy > C.MAX_FALL:
            self.vy = C.MAX_FALL

        # Rising air off a chimney. Not a jump -- a sustained climb, which is
        # the only way a level reaches upward at all when a jump clears 59px.
        # Applied after gravity so it wins, and capped so it lifts rather than
        # flings.
        if self.map.overlaps_updraft(self.box.x, self.box.y, self.box.w, self.box.h):
            self.vy = max(self.vy - C.UPDRAFT_LIFT * dt, -C.UPDRAFT_MAX_RISE)
            centre = self.map.updraft_centre(
                self.box.x, self.box.y, self.box.w, self.box.h
            )
            if centre is not None:
                # Settles him toward the middle, so a column is a place you
                # ride rather than one you keep sliding out of.
                mid = self.box.x + self.box.w / 2
                self.box.x += sign(centre - mid) * min(
                    abs(centre - mid), C.UPDRAFT_DRIFT * dt
                )
            self.in_updraft = True
        else:
            self.in_updraft = False

        self.map.move_x(self.box, self.vx * dt)

        was_grounded = self.grounded
        dropping = intent.down and intent.jump
        land = self.map.move_y(self.box, self.vy * dt, dropping)

        if land.ground:
            # Only a real fall thumps; resting on the ground re-lands every
            # frame.
            if not was_grounded and self.vy > 1.5:
                self.cues.append("land")
            self.vy = 0.0
            self.grounded = True
            self.jumping = False
            self.coyote = C.COYOTE_FRAMES
        else:
            if land.ceiling:
                self.vy = 0.0
            self.grounded = False
            if was_grounded:
                self.coyote = max(self.coyote, C.COYOTE_FRAMES)

        # Run cycle speed tracks actual speed, so the legs match the ground.
        if self.grounded and abs(self.vx) > 0.1:
            self.anim_timer += dt * (0.6 + abs(self.vx) * 0.5)
            if self.anim_timer >= 5:
                self.anim_timer = 0.0
                self.run_frame = (self.run_frame + 1) % 4
        elif self.grounded:
            self.run_frame = 0

    def _tick_carried_timers(self, dt: float) -> None:
        if self.invincible > 0:
            self.invincible -= dt
        if self.shake_frames > 0:
            self.shake_frames -= dt

    # ── Being moved by something else ───────────────────────────────

    def board(self, trolley) -> None:
        """Climbed aboard a trolley."""
        self.riding = trolley
        self.vx = 0.0
        self.vy = 0.0
        self.grounded = True
        self.jumping = False
        self.charge = 0.0
        if self.rolling:
            self._stop_rolling()

    def dismount(self, vx: float, vy: float) -> None:
        """Stepped off, with whatever the trolley was doing carried into him."""
        self.riding = None
        self.vx = vx
        self.vy = vy
        self.grounded = False
        self.coyote = C.COYOTE_FRAMES

    def capture(self, bell) -> None:
        """Caught by a bell. It owns him until it fires."""
        self.captured = bell
        self.vx = 0.0
        self.vy = 0.0
        self.grounded = False
        self.jumping = False
        self.charge = 0.0
        if self.rolling:
            self._stop_rolling()

    def launch(self, angle: float) -> None:
        """Fired out of a bell along ``angle`` radians."""
        self.captured = None
        self.vx = math.cos(angle) * C.BELL_LAUNCH
        self.vy = math.sin(angle) * C.BELL_LAUNCH
        self.grounded = False
        self.coyote = 0.0
        self.jumping = True
        if self.vx != 0:
            self.facing = int(sign(self.vx))

    def stomp_bounce(self) -> None:
        """A stomp landed: bounce, higher if he is asking to go up.

        The web build reads whether jump is *held* at the moment of contact.
        A terminal has no held state, so the live jump buffer stands in for it:
        press jump as you come down on an enemy and you get the taller bounce.
        That turns a holding skill into a timing one, which is the closest
        honest equivalent -- and the buffer is 8 frames, so the window is
        forgiving rather than frame-perfect.
        """
        self.vy = C.STOMP_BOUNCE_HELD if self.jump_buffer > 0 else C.STOMP_BOUNCE
        self.grounded = False
        self.jumping = True

    # ── Score and damage ────────────────────────────────────────────

    def hurt(self, from_x: float) -> str | None:
        """Take a hit.

        The bird is the first thing spent -- losing a companion is visible and
        recoverable where losing a life is neither. Returns ``'bird'``,
        ``'life'``, or None if the hit was refused because he is still flashing
        from the last one.
        """
        if self.invincible > 0 or not self.alive:
            return None
        self.invincible = C.INVINCIBLE_FRAMES
        self.shake_frames = 10
        away = -1 if self.box.x + self.box.w / 2 < from_x else 1
        self.vx = away * C.KNOCKBACK_X
        self.vy = C.KNOCKBACK_Y
        self.grounded = False
        self.charge = 0.0
        if self.rolling:
            self._stop_rolling()
        if self.has_bird:
            self.has_bird = False
            return "bird"
        self.lives -= 1
        return "life"

    def collect(self, n: int) -> bool:
        """Bank notes. True when that bought an extra life."""
        self.notes += n
        self.ammo = min(C.NOTE_AMMO_MAX, self.ammo + C.AMMO_PER_PICKUP)
        if self.notes >= C.NOTES_PER_LIFE:
            self.notes -= C.NOTES_PER_LIFE
            self.lives += 1
            return True
        return False

    def can_shoot(self) -> bool:
        return (
            self.alive
            and self.ammo > 0
            and self.shoot_cooldown <= 0
            and not self.rolling
        )

    def spend_shot(self) -> None:
        self.ammo -= 1
        self.shoot_cooldown = C.FIRE_RATE

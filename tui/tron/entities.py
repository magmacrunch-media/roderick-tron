"""Enemies, projectiles, pickups, the companion, and the set pieces.

A port of the simulation half of ``web/js/entities.js``; the drawing half stays
in the browser. Everything here is in WORLD pixels. The runner this replaced
kept entities in screen space and hand-scrolled them, which only held while the
camera moved at one fixed rate.

Particles and popups are decorative and are driven by an injected
:class:`random.Random`, so a run is reproducible. Nothing else in this module
consults the generator, which is what lets the phase-02 oracle compare two
implementations without having to match a JavaScript PRNG.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from . import config as C
from .player import Intent, Player
from .tilemap import Box, Tilemap, overlap


@dataclass
class Enemy:
    kind: str
    x: float
    y: float
    home_y: float
    w: float = C.GARGOYLE_W
    h: float = C.GARGOYLE_H
    dir: int = -1
    phase: float = 0.0
    hp: int = 1
    flash: float = 0.0
    dead: bool = False


@dataclass
class Shot:
    x: float
    y: float
    vx: float
    life: float


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    max: float
    colour: str


@dataclass
class Popup:
    x: float
    y: float
    text: str
    colour: str
    life: float = 44.0
    max: float = 44.0


@dataclass
class Trolley:
    x: float
    y: float
    w: float = C.TROLLEY_W
    h: float = C.TROLLEY_H
    vx: float = 0.0
    vy: float = 0.0
    riding: bool = False
    grounded: bool = False
    spent: bool = False


@dataclass
class Bell:
    x: float
    y: float
    w: float = C.BELL_W
    h: float = C.BELL_H
    phase: float = 0.0
    angle: float = 0.0
    cooldown: float = 0.0
    holding: bool = False


@dataclass
class Bird:
    x: float
    y: float
    phase: float = 0.0


class Entities:
    """Everything in the level that is not terrain and is not Roderick."""

    def __init__(self, tilemap: Tilemap, rng: random.Random | None = None) -> None:
        self.map = tilemap
        # Seeded rather than system-entropy so an unseeded run is still
        # reproducible; 1810 is the century the rooftops are from.
        self.rng = rng if rng is not None else random.Random(1810)
        self.reset()

    def reset(self) -> None:
        self.enemies: list[Enemy] = [
            Enemy(
                kind=m.kind,
                x=m.x,
                y=m.y,
                home_y=m.y,
                phase=(m.x * 0.07) % (math.pi * 2),
                hp=(
                    C.STATUE_HP
                    if m.kind == "statue"
                    else C.FLYER_HP
                    if m.kind == "flyer"
                    else C.GARGOYLE_HP
                ),
            )
            for m in self.map.enemies
        ]
        # Pickups live on the map, so a retry restores them by clearing the
        # flags rather than by reparsing the level.
        for n in self.map.notes:
            n.taken = False
        for letter in self.map.letters:
            letter.taken = False

        self.shots: list[Shot] = []
        self.particles: list[Particle] = []
        self.popups: list[Popup] = []
        self.bird: Bird | None = None
        self.events: list[dict] = []
        self.trolleys = [Trolley(t.x, t.y) for t in self.map.trolleys]
        # A bell per marker, each swinging from its own phase so a row of them
        # does not beat in unison.
        self.bells = [
            Bell(b.x, b.y, phase=i * 0.9) for i, b in enumerate(self.map.bells)
        ]

    # ── Projectiles ─────────────────────────────────────────────────

    def fire(self, player: Player) -> None:
        self.shots.append(
            Shot(
                x=player.box.x + (player.box.w if player.facing > 0 else -C.NOTE_W),
                y=player.box.y + 6,
                vx=player.facing * C.NOTE_SPEED,
                life=C.NOTE_LIFE,
            )
        )

    # ── Per-frame ───────────────────────────────────────────────────

    def update(self, player: Player, intent: Intent, dt: float) -> None:
        self.events.clear()
        self.update_shots(dt)
        self.update_trolleys(player, intent, dt)
        self.update_bells(player, intent, dt)
        self.update_enemies(player, dt)
        self.update_pickups(player)
        self.update_bird(player, dt)
        self.update_particles(dt)
        self.update_popups(dt)

    def update_trolleys(self, player: Player, intent: Intent, dt: float) -> None:
        """The coal trolleys.

        Board by touching one. From then on the trolley is the thing being
        simulated and the player is a passenger: it rolls right at a constant
        speed and the only input that reaches him is jump, which leaps the
        whole cart.

        Constant speed is the design. A cart you can slow down is a cart you
        can wait out, and then a rail with holes in it stops being about
        commitment and becomes about patience.
        """
        for t in self.trolleys:
            if t.spent:
                continue

            if not t.riding:
                # Sitting on its rail, waiting. It does not roll until boarded,
                # so a trolley placed in a level stays where the level put it.
                if (player.riding or player.captured
                        or not player.alive or player.exiting):
                    continue
                if not overlap(
                    player.box.x, player.box.y, player.box.w, player.box.h,
                    t.x, t.y, t.w, t.h,
                ):
                    continue
                t.riding = True
                t.vx = C.TROLLEY_SPEED
                player.board(t)
                self.events.append({"type": "board", "x": t.x, "y": t.y})
                continue

            # ── The ride ────────────────────────────────────────────
            on_rail = self.map.overlaps_rail(t.x, t.y + t.h, t.w, 2)
            if on_rail:
                # Back up to speed as soon as there is track under the wheels.
                t.vx += (C.TROLLEY_SPEED - t.vx) * min(1, 0.2 * dt)
            elif t.grounded:
                t.vx = max(0.0, t.vx - C.TROLLEY_DECEL * dt)

            if intent.jump and t.grounded:
                t.vy = C.TROLLEY_JUMP
                t.grounded = False
                self.events.append({"type": "trolleyJump", "x": t.x, "y": t.y})

            t.vy += C.GRAVITY * dt
            if t.vy > C.MAX_FALL:
                t.vy = C.MAX_FALL

            box = Box(t.x, t.y, t.w, t.h)
            blocked = self.map.move_x(box, t.vx * dt)
            land = self.map.move_y(box, t.vy * dt, False)
            t.x, t.y = box.x, box.y
            t.grounded = land.ground
            if land.ground or land.ceiling:
                t.vy = 0.0

            # The passenger rides on top of it.
            player.box.x = t.x + (t.w - player.box.w) / 2
            player.box.y = t.y - player.box.h + 2

            if blocked:
                # Hit something head on. He is thrown clear; the trolley is done.
                t.spent = True
                player.dismount(-1.6, -4.2)
                self.events.append({"type": "crash", "x": t.x + t.w / 2})
                continue

            if t.y > self.map.h + C.FALL_KILL_MARGIN:
                # Went into a hole. Nothing to do here; the scene sees him fall.
                t.spent = True
                player.dismount(0.0, C.MAX_FALL)
                continue

            if t.grounded and not on_rail and t.vx <= C.TROLLEY_DISMOUNT:
                t.spent = True
                t.riding = False
                player.dismount(t.vx, 0.0)
                self.events.append({"type": "dismount", "x": t.x, "y": t.y})

    def update_bells(self, player: Player, intent: Intent, dt: float) -> None:
        """The bell cannons.

        A bell catches you, swings through an arc overhead, and fires along
        whatever angle it is pointing when jump is pressed. Making the aim a
        moving thing rather than a fixed property is what lets the level file
        stay a grid of characters: there is no angle to encode, because the
        timing IS the aim.
        """
        frm = math.radians(C.BELL_SWING_FROM)
        to = math.radians(C.BELL_SWING_TO)

        for b in self.bells:
            b.phase += C.BELL_SWING_RATE * dt
            # A sine rather than a sawtooth, so it eases at the extremes and
            # hangs longest where the aim is most useful.
            b.angle = frm + (to - frm) * (0.5 - 0.5 * math.cos(b.phase))
            if b.cooldown > 0:
                b.cooldown -= dt

            if player.captured is b:
                # The bell owns his position while it holds him.
                player.box.x = b.x + (b.w - player.box.w) / 2
                player.box.y = b.y + (b.h - player.box.h) / 2
                b.holding = True
                if intent.jump:
                    player.launch(b.angle)
                    b.cooldown = C.BELL_RECAPTURE
                    b.holding = False
                    self.events.append({"type": "launch", "x": b.x, "y": b.y})
                continue
            b.holding = False

            if player.captured or not player.alive or player.exiting:
                continue
            if b.cooldown > 0:
                continue
            if not overlap(
                player.box.x, player.box.y, player.box.w, player.box.h,
                b.x, b.y, b.w, b.h,
            ):
                continue

            player.capture(b)
            self.events.append({"type": "caught", "x": b.x, "y": b.y})

    def update_shots(self, dt: float) -> None:
        for i in range(len(self.shots) - 1, -1, -1):
            s = self.shots[i]
            s.x += s.vx * dt
            s.life -= dt
            # A note that hits masonry stops there rather than sailing through.
            if s.life <= 0 or self.map.overlaps_solid(s.x, s.y, C.NOTE_W, C.NOTE_H):
                self.spawn_particles(s.x, s.y, 3, "robotCyan", 10)
                del self.shots[i]
                continue
            for e in self.enemies:
                if e.dead:
                    continue
                if not overlap(s.x, s.y, C.NOTE_W, C.NOTE_H, e.x, e.y, e.w, e.h):
                    continue
                self.damage(e, 1)
                del self.shots[i]
                break

    def damage(self, e: Enemy, n: int) -> bool:
        e.hp -= n
        e.flash = 6
        cx = e.x + e.w / 2
        cy = e.y + e.h / 2
        if e.hp > 0:
            self.spawn_particles(cx, cy, 4, "robotCyan", 12)
            return False
        e.dead = True
        self.spawn_particles(cx, cy, 9, "particleStone", 22)
        self.events.append({"type": "kill", "kind": e.kind, "x": cx, "y": cy})
        return True

    def update_enemies(self, player: Player, dt: float) -> None:
        p = player.box

        for i in range(len(self.enemies) - 1, -1, -1):
            e = self.enemies[i]
            if e.flash > 0:
                e.flash -= dt
            if e.dead:
                del self.enemies[i]
                continue

            if e.kind == "gargoyle":
                # Walks, and turns at a wall or a ledge. Checking for footing
                # one step ahead is what keeps them on their own rooftop
                # instead of marching off it within seconds of the level
                # starting.
                step = e.dir * C.GARGOYLE_SPEED * dt
                ahead = e.x + step + (e.w if e.dir > 0 else -1)
                if self.map.overlaps_solid(
                    e.x + step, e.y, e.w, e.h
                ) or not self.map.has_footing(ahead, e.y, 1, e.h):
                    e.dir *= -1
                else:
                    e.x += step
            elif e.kind == "flyer":
                e.phase += C.FLYER_BOB_RATE * dt
                e.y = e.home_y + math.sin(e.phase) * C.FLYER_BOB_AMP
                step = e.dir * C.FLYER_SPEED * dt
                if self.map.overlaps_solid(e.x + step, e.y, e.w, e.h):
                    e.dir *= -1
                else:
                    e.x += step
            # A statue does nothing. That is the point of it.

            if not player.alive or player.exiting:
                continue
            if not overlap(p.x, p.y, p.w, p.h, e.x, e.y, e.w, e.h):
                continue

            # ── Contact ────────────────────────────────────────────
            # A roll goes straight through anything soft.
            if player.rolling and e.kind != "statue":
                self.damage(e, 99)
                continue

            # Coming down on it counts as a stomp. Requiring downward motion
            # and feet above its middle is what stops a walk into the side of
            # one from reading as a stomp.
            falling = player.vy > 0
            above = p.y + p.h - player.vy <= e.y + e.h * 0.6
            if falling and above:
                if e.kind == "statue":
                    # Too heavy to flatten: you bounce, it does not care.
                    player.stomp_bounce()
                    self.spawn_particles(e.x + e.w / 2, e.y, 4, "particleStone", 10)
                    self.events.append({"type": "shrug", "x": e.x + e.w / 2})
                    continue
                self.damage(e, 99)
                player.stomp_bounce()
                self.events.append({"type": "stomp", "x": e.x + e.w / 2})
                continue

            self.events.append({"type": "hurt", "x": e.x + e.w / 2})

    def update_pickups(self, player: Player) -> None:
        if not player.alive:
            return
        p = player.box

        for n in self.map.notes:
            if n.taken or not overlap(p.x, p.y, p.w, p.h, n.x, n.y, n.w, n.h):
                continue
            n.taken = True
            self.spawn_particles(n.x + 4, n.y + 4, 3, "noteWhite", 12)
            self.events.append({"type": "note", "x": n.x, "y": n.y})

        for letter in self.map.letters:
            if letter.taken or not overlap(
                p.x, p.y, p.w, p.h, letter.x, letter.y, letter.w, letter.h
            ):
                continue
            letter.taken = True
            self.spawn_particles(letter.x + 6, letter.y + 6, 6, "letterGold", 20)
            self.events.append(
                {"type": "letter", "ch": letter.ch, "x": letter.x, "y": letter.y}
            )

    def update_bird(self, player: Player, dt: float) -> None:
        """The clockwork bird.

        It trails rather than tracks, so it reads as following him rather than
        being welded on.
        """
        if not player.has_bird:
            self.bird = None
            return
        tx = player.box.x - player.facing * 13
        ty = player.box.y - 9
        if self.bird is None:
            self.bird = Bird(tx, ty)
            return
        k = min(1.0, C.BIRD_FOLLOW_LAG * dt)
        self.bird.x += (tx - self.bird.x) * k
        self.bird.y += (ty - self.bird.y) * k
        self.bird.phase += C.BIRD_BOB_RATE * dt

    def update_particles(self, dt: float) -> None:
        for i in range(len(self.particles) - 1, -1, -1):
            p = self.particles[i]
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.vy += 0.16 * dt
            p.life -= dt
            if p.life <= 0:
                del self.particles[i]

    def update_popups(self, dt: float) -> None:
        for i in range(len(self.popups) - 1, -1, -1):
            p = self.popups[i]
            p.y -= 0.32 * dt
            p.life -= dt
            if p.life <= 0:
                del self.popups[i]

    def spawn_particles(
        self, x: float, y: float, n: int, colour: str, life: float
    ) -> None:
        for _ in range(n):
            self.particles.append(
                Particle(
                    x=x,
                    y=y,
                    vx=(self.rng.random() - 0.5) * 3.2,
                    vy=(self.rng.random() - 1) * 2.4,
                    life=life,
                    max=life,
                    colour=colour,
                )
            )

    def add_popup(self, x: float, y: float, text: str, colour: str) -> None:
        self.popups.append(Popup(x, y, text, colour))

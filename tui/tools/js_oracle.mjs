/**
 * js_oracle.mjs — run the shipped JavaScript and record what it did.
 *
 *   node tools/js_oracle.mjs [outfile]        (default: -, meaning stdout)
 *
 * ── What this is for ──
 *
 * tui/ claims to be the same game as web/. The only way to keep that true is to
 * run the real browser modules and compare, rather than to read both and be
 * satisfied. So this loads config.js, levels.js, tilemap.js, player.js and
 * entities.js into a vm context with a scripted Input, drives them from a
 * seeded input script, and emits every frame as JSON. tests/test_oracle.py
 * replays the identical script against the Python port and compares.
 *
 * ── The two rules that deliberately differ ──
 *
 * The port drops JUMP_CUT (it reads a key release, which a terminal never
 * reports) and replaces the SHIFT run modifier with speed earned by sustained
 * travel. A naive comparison would therefore diverge on purpose, which would
 * make the oracle useless — it would be red whether or not anything was wrong.
 *
 * The answer is to compare under conditions where those two rules agree:
 *
 *   JUMP is HELD for the whole run, so `jumping && !jumpHeld()` never fires
 *   and the browser's jump is full height, which is the only height the port
 *   has. Edges still come from `pressed.JUMP`, so jumps happen where the
 *   script says.
 *
 *   RUN is HELD for the whole run, so the browser's cap is RUN_MAX. The Python
 *   side pins its earned charge to full for the same reason. Both then run at
 *   the same cap and the ramp — the thing that differs — is held out of the
 *   comparison.
 *
 * Everything else is in scope, which is most of the game: collision, one-way
 * platforms, coyote time, the jump buffer, roll commitment and the roll-jump
 * momentum rule, updraft lift and drift, friction and the overspeed bleed,
 * gargoyle ledge-turning, flyer bob, bell swing, and the trolley.
 *
 * That the two differences are held out here is not a gap: test_physics.py
 * asserts each of them behaves as designed, from the other direction.
 */

import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

const HERE = path.dirname(fileURLToPath(import.meta.url));
const JS_DIR = path.join(HERE, "..", "..", "web", "js");
const FILES = [
    "config.js", "levels.js", "tilemap.js", "sfx.js",
    "renderer.js", "player.js", "entities.js", "world.js",
];

/** mulberry32 — small, seeded, and identical wherever it is implemented. */
function mulberry32(a) {
    return function () {
        a |= 0;
        a = (a + 0x6d2b79f5) | 0;
        let t = Math.imul(a ^ (a >>> 15), 1 | a);
        t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
}

/** The controllable Input the game reads through, as test-simulation.js has. */
function makeInput() {
    return {
        held: {}, pressed: {},
        isDown(c) { return !!this.held[c]; },
        wasPressed(c) { const v = !!this.pressed[c]; this.pressed[c] = false; return v; },
        clearJustPressed() { this.pressed = {}; },
        left() { return this.isDown("L"); },
        right() { return this.isDown("R"); },
        down() { return this.isDown("D"); },
        run() { return this.isDown("RUN"); },
        jump() { return this.wasPressed("JUMP"); },
        jumpHeld() { return this.isDown("JUMP"); },
        roll() { return this.wasPressed("ROLL"); },
        shoot() { return this.wasPressed("SHOOT"); },
        allOff() { this.held = {}; this.pressed = {}; },
    };
}

function makeGame(levelIndex) {
    const input = makeInput();
    const sandbox = { Math, console, Input: input };
    const ctx = vm.createContext(sandbox);
    for (const f of FILES) {
        vm.runInContext(fs.readFileSync(path.join(JS_DIR, f), "utf8"), ctx, { filename: f });
    }
    const CONFIG = vm.runInContext("CONFIG", ctx);
    const map = vm.runInContext(`new Tilemap(LEVELS[${levelIndex}])`, ctx);
    sandbox.__map = map;
    const player = vm.runInContext("new Player(__map)", ctx);
    const entities = vm.runInContext("new Entities(__map)", ctx);
    return { CONFIG, map, player, entities, input, ctx };
}

// ── Trace 1: collision ──────────────────────────────────────────────
//
// The part that has to be identical to the pixel, exercised directly rather
// than through the player. Random bodies, random deltas, including deltas
// larger than a tile so the stepped movers' anti-tunnelling path is covered.

function traceCollision(levelIndex, count) {
    const { map, CONFIG } = makeGame(levelIndex);
    const rand = mulberry32(0x51ed + levelIndex);
    const probes = [];

    for (let i = 0; i < count; i++) {
        const w = i % 3 === 0 ? CONFIG.PLAYER_W : i % 3 === 1 ? CONFIG.TROLLEY_W : 8;
        const h = i % 3 === 0 ? CONFIG.PLAYER_H : i % 3 === 1 ? CONFIG.TROLLEY_H : CONFIG.ROLL_H;
        const x = Math.floor(rand() * (map.w - w));
        const y = Math.floor(rand() * (map.h - h));
        // Deltas up to +-40px: well past a tile, which is the case that
        // matters, since a body moving more than TILE in one step is what the
        // stepped movers exist to stop tunnelling.
        const dx = (rand() - 0.5) * 80;
        const dy = (rand() - 0.5) * 80;
        const dropping = rand() < 0.25;

        const bx = { x, y, w, h };
        const hit = map.moveX(bx, dx);
        const land = map.moveY(bx, dy, dropping);

        probes.push({
            in: { x, y, w, h, dx, dy, dropping },
            out: {
                x: bx.x, y: bx.y, hit,
                ground: land.ground, ceiling: land.ceiling, platform: land.platform,
            },
        });
    }
    return probes;
}

// ── The input script ────────────────────────────────────────────────
//
// Seeded, and emitted with the trace so the Python side replays exactly this
// and not merely something statistically similar. Weighted toward holding a
// direction, because that is what play looks like; the rest is enough
// jumping, rolling and dropping to reach every branch.

function inputScript(seed, frames) {
    const rand = mulberry32(seed);
    const script = [];
    let dir = 1;
    for (let i = 0; i < frames; i++) {
        if (rand() < 0.06) dir = rand() < 0.7 ? 1 : -1;
        if (rand() < 0.03) dir = 0;
        script.push({
            left: dir < 0,
            right: dir > 0,
            down: rand() < 0.10,
            jump: rand() < 0.09,
            roll: rand() < 0.04,
        });
    }
    return script;
}

// ── Trace 2: the player ─────────────────────────────────────────────

function tracePlayer(levelIndex, script) {
    const { player, input } = makeGame(levelIndex);
    const frames = [];

    input.allOff();
    for (const f of script) {
        input.held.L = f.left;
        input.held.R = f.right;
        input.held.D = f.down;
        // Held for the whole run — see the header. These two are what put the
        // browser and the port on the same rules.
        input.held.RUN = true;
        input.held.JUMP = true;
        input.pressed.JUMP = f.jump;
        input.pressed.ROLL = f.roll;

        player.update(1.0);

        frames.push([
            player.box.x, player.box.y, player.box.w, player.box.h,
            player.vx, player.vy,
            player.grounded ? 1 : 0, player.rolling ? 1 : 0,
            player.facing, player.coyote, player.jumpBuffer, player.rollTimer,
        ]);
    }
    return frames;
}

// ── Trace 3: entities ───────────────────────────────────────────────
//
// Enemies, bells and trolleys, driven by the real Entities beside the real
// Player. Enemy positions are the interesting part: gargoyle ledge-turning is
// the one piece of enemy logic with a geometry test in it, and a port that got
// the probe offset wrong would walk them off the roof within seconds.

function traceEntities(levelIndex, script) {
    const { player, entities, input } = makeGame(levelIndex);
    const frames = [];

    input.allOff();
    for (const f of script) {
        input.held.L = f.left;
        input.held.R = f.right;
        input.held.D = f.down;
        input.held.RUN = true;
        input.held.JUMP = true;
        input.pressed.JUMP = f.jump;
        input.pressed.ROLL = f.roll;

        player.update(1.0);
        // Entities reads the jump edge too, for the trolley and the bell. It
        // has already been consumed by player.update, exactly as in the game,
        // so re-arm it here to match what main.js does by calling them in this
        // order within one frame.
        input.pressed.JUMP = f.jump;
        entities.update(player, 1.0);

        frames.push({
            enemies: entities.enemies.map((e) => [e.kind, e.x, e.y, e.dir, e.hp]),
            bells: entities.bells.map((b) => [b.angle, b.cooldown, b.holding ? 1 : 0]),
            trolleys: entities.trolleys.map((t) => [t.x, t.y, t.vx, t.riding ? 1 : 0, t.spent ? 1 : 0]),
            notesTaken: entities.map.notes.filter((n) => n.taken).length,
            lettersTaken: entities.map.letters.filter((l) => l.taken).length,
        });
    }
    return frames;
}

// ── Trace 4: dropping through one-way platforms ─────────────────────
//
// A dedicated trace, because the random script never once reached this and a
// mutation run proved it: disabling drop-through entirely left every other
// comparison passing. It needs the player falling onto a platform while
// holding down and pressing jump, and the odds of the script arranging that
// on its own are negligible.
//
// The setup is deliberately mid-fall rather than standing. Pressing jump while
// grounded jumps -- the jump block runs before the move, so it wins -- which
// means `dropping` can only take effect on the way DOWN, after a jump has
// already spent the coyote window. That is subtle enough to be worth pinning
// rather than trusting to a comment.

function traceDrops(levelIndex, count) {
    const { map, player, input, CONFIG } = makeGame(levelIndex);
    // Rails as well as platforms: isPlatformTile() treats both as one-way, and
    // THE COAL RUN has no '=' at all — its whole surface is rail, so a trace
    // that only looked for platforms would silently skip that level.
    const spots = [];
    for (let ty = 0; ty < map.rows && spots.length < count; ty++) {
        for (let tx = 0; tx < map.cols && spots.length < count; tx++) {
            const ch = map.tileAt(tx, ty);
            if (ch === "=" || ch === "-") spots.push([tx, ty]);
        }
    }

    const runs = [];
    for (const [tx, ty] of spots) {
        for (const holdDown of [true, false]) {
            player.reset(map.spawn);
            player.box.x = tx * CONFIG.TILE;
            player.box.y = ty * CONFIG.TILE - player.box.h - 10;
            player.vx = 0;
            player.vy = 2.0;            // already falling toward it
            player.grounded = false;
            player.coyote = 0;          // spent, so a press cannot become a jump
            input.allOff();

            const frames = [];
            for (let i = 0; i < 30; i++) {
                input.held.D = holdDown;
                input.held.JUMP = true;
                input.held.RUN = true;
                input.pressed.JUMP = true;
                player.update(1.0);
                frames.push([player.box.x, player.box.y, player.vy, player.grounded ? 1 : 0]);
            }
            runs.push({ tx, ty, holdDown, frames });
        }
    }
    return runs;
}

// ── Trace 5: the browser's own reachability verdict ─────────────────
//
// web/tests/reachability.js searches the level graph with the browser's move
// set — which includes a short hop made by releasing the jump key, and a run
// modifier selectable at any instant. The terminal has neither.
//
// Emitting its verdict lets tests/test_reachable.py compare like for like: the
// Python search uses the smaller vocabulary, and if the two agree on which
// surfaces are reachable then losing those two verbs cost nothing. That is a
// far better answer than pinning today's numbers as literals, which would go
// stale the first time a level was edited.

function traceReach(levelIndex) {
    const { map, CONFIG, input, ctx } = makeGame(levelIndex);
    const { findSurfaces, analyse } = require(
        path.join(HERE, "..", "..", "web", "tests", "reachability.js")
    );

    const sandbox = ctx;
    sandbox.__map = map;
    const env = {
        CONFIG,
        input,
        map,
        exit: map.exit,
        surfaces: findSurfaces(map),
        newPlayer: () => vm.runInContext("new Player(__map)", ctx),
        newGame: () => ({
            player: vm.runInContext("new Player(__map)", ctx),
            entities: vm.runInContext("new Entities(__map)", ctx),
        }),
    };
    const r = analyse(env);
    return {
        start: r.start,
        surfaces: r.surfaces.map((s) => [s.ty, s.tx0, s.tx1]),
        reached: [...r.reached].sort((a, b) => a - b),
        exitReached: r.exitReached,
        survivableRides: r.survivableRides !== false,
        unreachablePickups: r.unreachablePickups,
    };
}

// ── Emit ────────────────────────────────────────────────────────────

const FRAMES = 300;
const PROBES = 300;

const { CONFIG } = makeGame(0);
const out = {
    generated_by: "tools/js_oracle.mjs",
    frames: FRAMES,
    config: Object.fromEntries(
        Object.entries(CONFIG).filter(([, v]) => typeof v === "number")
    ),
    levels: [],
};

for (let i = 0; i < 3; i++) {
    const script = inputScript(0x0d + i, FRAMES);
    out.levels.push({
        index: i,
        script,
        collision: traceCollision(i, PROBES),
        player: tracePlayer(i, script),
        entities: traceEntities(i, script),
        drops: traceDrops(i, 6),
        reach: traceReach(i),
    });
}

const dest = process.argv[2] || "-";
const json = JSON.stringify(out);
if (dest === "-") process.stdout.write(json);
else fs.writeFileSync(dest, json);

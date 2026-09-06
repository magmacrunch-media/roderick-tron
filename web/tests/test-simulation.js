/**
 * test-simulation.js — Roderick Tron headless tests.
 *
 * The game's modules are plain scripts that assign globals and touch no DOM
 * outside their draw() methods, so the shipped files are loaded into a vm
 * context and run. Nothing here reimplements game logic; a test that did could
 * pass while the game was broken.
 *
 * The game was an endless auto-runner and is now a hand-authored platformer.
 * That moved what is worth proving:
 *
 *   Then — the terrain generator is fair, sampled across the difficulty curve.
 *   Now  — THIS level is completable, exhaustively, with the real physics.
 *
 * The second is a stronger guarantee, because authored levels are finite. An
 * unclearable gap in a generator is a probability; an unclearable gap in a
 * level is a wall, and every player meets it.
 *
 * Run: node test-simulation.js
 */

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { findSurfaces, analyse } = require('./reachability.js');

const JS_DIR = path.join(__dirname, '..', 'js');
const FILES = ['config.js', 'levels.js', 'tilemap.js', 'sfx.js', 'renderer.js', 'player.js', 'entities.js', 'world.js'];

let passed = 0, failed = 0;

function ok(cond, name, detail) {
    if (cond) { passed++; console.log('  PASS  ' + name); }
    else { failed++; console.log('  FAIL  ' + name + (detail ? '\n          ' + detail : '')); }
}

function near(a, b, tol, name) {
    ok(Math.abs(a - b) <= tol, name, 'got ' + a + ', expected ' + b + ' +/- ' + tol);
}

/** A recording no-op 2D context — enough for every draw() to run. */
function stubCtx() {
    const calls = [];
    const noop = (n) => function () { calls.push(n); };
    return {
        calls,
        fillStyle: '', globalAlpha: 1, font: '', textAlign: 'left',
        fillRect: noop('fillRect'), clearRect: noop('clearRect'), fillText: noop('fillText'),
        beginPath: noop('beginPath'), arc: noop('arc'), fill: noop('fill'),
        save: noop('save'), restore: noop('restore'), translate: noop('translate'),
        createLinearGradient: () => ({ addColorStop() {} }),
        createRadialGradient: () => ({ addColorStop() {} }),
    };
}

/**
 * A controllable Input. The game reads held state and edge presses through
 * this, so a test drives the real controller exactly as a player does.
 */
function makeInput() {
    return {
        held: {}, pressed: {},
        isDown(c) { return !!this.held[c]; },
        wasPressed(c) { const v = !!this.pressed[c]; this.pressed[c] = false; return v; },
        clearJustPressed() { this.pressed = {}; },
        left()     { return this.isDown('L'); },
        right()    { return this.isDown('R'); },
        down()     { return this.isDown('D'); },
        run()      { return this.isDown('RUN'); },
        jump()     { return this.wasPressed('JUMP'); },
        jumpHeld() { return this.isDown('JUMP'); },
        roll()     { return this.wasPressed('ROLL'); },
        shoot()    { return this.wasPressed('SHOOT'); },
        // helpers
        hold(c)    { this.held[c] = true; },
        release(c) { this.held[c] = false; },
        tap(c)     { this.pressed[c] = true; this.held[c] = true; },
        allOff()   { this.held = {}; this.pressed = {}; },
    };
}

/** A fresh game in its own vm context. */
function makeGame(levelIndex) {
    const input = makeInput();
    const sandbox = { Math: Math, console, Input: input };
    const ctx = vm.createContext(sandbox);
    for (const f of FILES) {
        vm.runInContext(fs.readFileSync(path.join(JS_DIR, f), 'utf8'), ctx, { filename: f });
    }
    const CONFIG = vm.runInContext('CONFIG', ctx);
    const LEVELS = vm.runInContext('LEVELS', ctx);
    const map = vm.runInContext('new Tilemap(LEVELS[' + (levelIndex || 0) + '])', ctx);
    sandbox.__map = map;
    const player = vm.runInContext('new Player(__map)', ctx);
    const entities = vm.runInContext('new Entities(__map)', ctx);
    const world = vm.runInContext('new World(__map)', ctx);
    const cam = vm.runInContext('new Camera(__map)', ctx);
    const Sfx = vm.runInContext('Sfx', ctx);
    return { CONFIG, LEVELS, map, player, entities, world, cam, input, ctx, Sfx };
}

// ── Parsing ───────────────────────────────────────────────────────────────────

console.log('\nlevel parsing:');
{
    const g = makeGame(0);
    const { map, CONFIG } = g;

    ok(map.cols > 0 && map.rows > 0, 'level has dimensions (' + map.cols + ' x ' + map.rows + ' tiles)');
    ok(map.spawn && map.exit, 'a spawn and an exit were found');
    ok(map.notes.length > 0, map.notes.length + ' notes placed');
    ok(map.letters.length === 4, 'exactly four letters');
    ok(map.letters.map((l) => l.ch).sort().join('') === 'NORT', 'and they are T R O N');
    ok(map.enemies.length > 0, map.enemies.length + ' enemies placed');

    // Every marker must have been lifted out of the terrain, or the player
    // would collide with the tile a gargoyle was standing on.
    const leftovers = [];
    for (let ty = 0; ty < map.rows; ty++) {
        for (let tx = 0; tx < map.cols; tx++) {
            const ch = map.tileAt(tx, ty);
            if ('.#=~'.indexOf(ch) === -1) leftovers.push(ch + '@' + tx + ',' + ty);
        }
    }
    ok(leftovers.length === 0, 'no entity markers left in the terrain grid', leftovers.slice(0, 5).join(' '));

    // Rows are padded, so every row is addressable to the full width.
    let ragged = false;
    for (let ty = 0; ty < map.rows; ty++) if (map.grid[ty].length !== map.cols) ragged = true;
    ok(!ragged, 'short rows are padded to the level width');

    ok(map.tileAt(-1, 5) === '#' && map.tileAt(map.cols, 5) === '#', 'off the sides reads as solid');
    ok(map.tileAt(5, map.rows) === '.', 'below the level reads as air, so pits kill');
    void CONFIG;
}

// ── Collision ─────────────────────────────────────────────────────────────────

console.log('\ncollision:');
{
    const g = makeGame(0);
    const { map, CONFIG } = g;

    // Find a floor tile to test against.
    let floorTx = -1, floorTy = -1;
    for (let ty = 0; ty < map.rows && floorTy < 0; ty++) {
        for (let tx = 0; tx < map.cols; tx++) {
            if (map.tileAt(tx, ty) === '#' && map.tileAt(tx, ty - 1) === '.') { floorTx = tx; floorTy = ty; break; }
        }
    }
    ok(floorTy >= 0, 'found an exposed floor tile to test against');

    const floorY = floorTy * CONFIG.TILE;

    // Landing snaps flush to the surface, not one pixel into or above it.
    const box = { x: floorTx * CONFIG.TILE + 1, y: floorY - 60, w: CONFIG.PLAYER_W, h: CONFIG.PLAYER_H };
    const land = map.moveY(box, 80, false);
    ok(land.ground, 'a fall onto floor reports ground');
    near(box.y + box.h, floorY, 0.001, 'and stops exactly on the surface');

    // Tunnelling: a single step far larger than a tile must still be stopped.
    const fast = { x: floorTx * CONFIG.TILE + 1, y: floorY - 200, w: CONFIG.PLAYER_W, h: CONFIG.PLAYER_H };
    map.moveY(fast, 400, false);
    near(fast.y + fast.h, floorY, 0.001, 'a 400px step does not tunnel through the floor');

    // Horizontal into a wall.
    let wallTx = -1, wallTy = -1;
    for (let ty = 0; ty < map.rows && wallTx < 0; ty++) {
        for (let tx = 1; tx < map.cols; tx++) {
            if (map.tileAt(tx, ty) === '#' && map.tileAt(tx - 1, ty) === '.') { wallTx = tx; wallTy = ty; break; }
        }
    }
    if (wallTx > 0) {
        const w = { x: (wallTx - 1) * CONFIG.TILE, y: wallTy * CONFIG.TILE, w: CONFIG.PLAYER_W, h: CONFIG.PLAYER_H };
        const hit = map.moveX(w, 300);
        ok(hit, 'a 300px horizontal step into a wall is stopped');
        near(w.x + w.w, wallTx * CONFIG.TILE, 0.001, 'and stops flush against it');
    }

    // One-way platforms.
    let pTx = -1, pTy = -1;
    for (let ty = 0; ty < map.rows && pTy < 0; ty++) {
        for (let tx = 0; tx < map.cols; tx++) {
            if (map.tileAt(tx, ty) === '=') { pTx = tx; pTy = ty; break; }
        }
    }
    ok(pTy >= 0, 'the level has one-way platforms');
    if (pTy >= 0) {
        const top = pTy * CONFIG.TILE;
        const down = { x: pTx * CONFIG.TILE + 1, y: top - 30, w: CONFIG.PLAYER_W, h: CONFIG.PLAYER_H };
        const r1 = map.moveY(down, 60, false);
        ok(r1.platform, 'falling onto a platform lands on it');
        near(down.y + down.h, top, 0.001, 'flush with its surface');

        const up = { x: pTx * CONFIG.TILE + 1, y: top + 20, w: CONFIG.PLAYER_W, h: CONFIG.PLAYER_H };
        const r2 = map.moveY(up, -40, false);
        ok(!r2.ground, 'rising through the same platform is not blocked');

        const thru = { x: pTx * CONFIG.TILE + 1, y: top - 30, w: CONFIG.PLAYER_W, h: CONFIG.PLAYER_H };
        const r3 = map.moveY(thru, 60, true);
        ok(!r3.platform, 'and a deliberate drop passes through it');

        // Resting, not landing. A body already flush with a platform must stay
        // on it — and did not: tileRange stops at (y + h - 1), so the tile
        // holding it up was out of range on the first frame and rejected as
        // "came from below" on the second, and it sank straight through. The
        // landing case above hides this, because a fast step crosses the
        // boundary in a single move.
        const rest = { x: pTx * CONFIG.TILE + 1, y: top - CONFIG.PLAYER_H, w: CONFIG.PLAYER_W, h: CONFIG.PLAYER_H };
        let sank = false;
        for (let i = 0; i < 120; i++) {
            const rr = map.moveY(rest, CONFIG.GRAVITY, false);
            if (!rr.ground) { sank = true; break; }
            rest.y = top - CONFIG.PLAYER_H;          // as a grounded body is re-placed
        }
        ok(!sank, 'a body resting flush on a platform stays on it');
    }
}

// ── Physics characterisation ──────────────────────────────────────────────────

console.log('\nmovement:');
{
    // A flat corridor, so the numbers describe the physics and not the level.
    const g = makeGame(0);
    const { CONFIG, input, ctx } = g;
    const flat = { name: 'flat', rows: ['S' + '.'.repeat(60)].concat(['#'.repeat(61)]) };
    ctx.__flat = flat;
    const map = vm.runInContext('new Tilemap(__flat)', ctx);
    ctx.__fmap = map;
    const mk = () => vm.runInContext('new Player(__fmap)', ctx);

    // Peak height of a fully held jump.
    const p = mk();
    input.allOff();
    p.grounded = true; p.coyote = CONFIG.COYOTE_FRAMES;
    input.tap('JUMP');
    let top = p.box.y;
    for (let i = 0; i < 80; i++) { p.update(1.0); top = Math.min(top, p.box.y); if (p.grounded && i > 3) break; }
    const height = (map.rows - 1) * CONFIG.TILE - CONFIG.PLAYER_H - top;
    near(height, CONFIG.JUMP_HEIGHT, 6, 'a held jump reaches its configured height');
    ok(height > CONFIG.TILE * 3, 'which clears three tiles (' + height.toFixed(0) + 'px)');

    // Tapping is meaningfully shorter than holding.
    const q = mk();
    input.allOff();
    q.grounded = true; q.coyote = CONFIG.COYOTE_FRAMES;
    input.tap('JUMP');
    let top2 = q.box.y;
    for (let i = 0; i < 80; i++) {
        if (i === 3) input.release('JUMP');
        q.update(1.0); top2 = Math.min(top2, q.box.y);
        if (q.grounded && i > 3) break;
    }
    const shortHeight = (map.rows - 1) * CONFIG.TILE - CONFIG.PLAYER_H - top2;
    ok(shortHeight < height - 12, 'a tapped jump is markedly shorter (' + shortHeight.toFixed(0) + ' vs ' + height.toFixed(0) + ')');

    // Top speeds separate cleanly: walk < run < roll.
    const topSpeed = (keys, frames) => {
        const s = mk();
        input.allOff();
        s.grounded = true; s.coyote = CONFIG.COYOTE_FRAMES;
        for (const k of keys) input.tap(k);
        let best = 0;
        for (let i = 0; i < frames; i++) { s.update(1.0); best = Math.max(best, Math.abs(s.vx)); }
        return best;
    };
    const walk = topSpeed(['R'], 90);
    const run = topSpeed(['R', 'RUN'], 90);
    const roll = topSpeed(['R', 'ROLL'], 20);
    near(walk, CONFIG.WALK_MAX, 0.05, 'walk tops out at WALK_MAX');
    near(run, CONFIG.RUN_MAX, 0.05, 'run tops out at RUN_MAX');
    near(roll, CONFIG.ROLL_MAX, 0.05, 'roll tops out at ROLL_MAX');
    ok(walk < run && run < roll, 'and the three are strictly ordered');
}

// ── dt invariance ─────────────────────────────────────────────────────────────
// The runner this replaced applied dt to gravity but not to the position step,
// and ran at double speed on a 120Hz display.

console.log('\ndt invariance:');
{
    // On flat ground, deliberately. Run this along the real level and the
    // player falls into the first pit, so the comparison becomes free-fall
    // depth, where first-order Euler drift grows without bound and the test
    // ends up measuring the integrator instead of the game.
    const runAt = (dt, steps) => {
        const g = makeGame(0);
        const { CONFIG, input, ctx } = g;
        ctx.__flat2 = { name: 'flat', rows: ['S' + '.'.repeat(240), '#'.repeat(241)] };
        const fmap = vm.runInContext('new Tilemap(__flat2)', ctx);
        ctx.__fmap2 = fmap;
        const p = vm.runInContext('new Player(__fmap2)', ctx);
        input.allOff();
        input.hold('R'); input.hold('RUN');
        p.grounded = true; p.coyote = CONFIG.COYOTE_FRAMES;
        input.tap('JUMP'); input.hold('JUMP');
        for (let i = 0; i < steps; i++) p.update(dt);
        return { x: p.box.x, y: p.box.y };
    };
    const a = runAt(1.0, 120);
    const b = runAt(0.5, 240);
    const c = runAt(2.0, 60);
    // Semi-implicit Euler is first order, so a coarser step drifts a little.
    // The bug this guards against was a factor of two, not a few pixels.
    near(b.x, a.x, 6, '120Hz horizontal matches 60Hz');
    near(c.x, a.x, 6, '30Hz horizontal matches 60Hz');
    near(b.y, a.y, 1, '120Hz vertical matches 60Hz');
    near(c.y, a.y, 1, '30Hz vertical matches 60Hz');

    // Asserted directly, because the failure mode was not drift but a speed
    // that grew every airborne frame until he crossed the level in a second.
    const topAt = (dt, steps) => {
        const g = makeGame(0);
        const { CONFIG, input, ctx } = g;
        ctx.__flat3 = { name: 'flat', rows: ['S' + '.'.repeat(240), '#'.repeat(241)] };
        const fmap = vm.runInContext('new Tilemap(__flat3)', ctx);
        ctx.__fmap3 = fmap;
        const p = vm.runInContext('new Player(__fmap3)', ctx);
        input.allOff(); input.hold('R'); input.hold('RUN');
        p.grounded = true; p.coyote = CONFIG.COYOTE_FRAMES;
        input.tap('JUMP'); input.hold('JUMP');
        let top = 0;
        for (let i = 0; i < steps; i++) { p.update(dt); top = Math.max(top, Math.abs(p.vx)); }
        return { top: top, cap: CONFIG.RUN_MAX };
    };
    for (const dt of [1.0, 0.5, 2.0]) {
        const r = topAt(dt, Math.round(120 / dt));
        ok(r.top <= r.cap + 0.001,
           'holding a direction never exceeds RUN_MAX at dt=' + dt,
           'reached ' + r.top.toFixed(2) + ' against a cap of ' + r.cap);
    }
}

// ── Every gap is clearable ────────────────────────────────────────────────────
// The platformer equivalent of the runner's fairness test, and stronger: a
// level is finite, so this is exhaustive rather than sampled.

console.log('\nevery gap is clearable:');
{
    const g = makeGame(0);
    const { map, CONFIG, input, ctx } = g;
    ctx.__m = map;

    // Ground rows are the ones with terrain; a pit is a run of columns where a
    // ground row has no floor.
    const floorRow = (() => {
        let best = -1, count = 0;
        for (let ty = 0; ty < map.rows; ty++) {
            let n = 0;
            for (let tx = 0; tx < map.cols; tx++) if (map.tileAt(tx, ty) === '#') n++;
            if (n > count) { count = n; best = ty; }
        }
        return best;
    })();
    ok(floorRow >= 0, 'identified the main floor row (row ' + floorRow + ')');

    const pits = [];
    let run = null;
    for (let tx = 0; tx < map.cols; tx++) {
        const solid = map.tileAt(tx, floorRow) === '#';
        if (!solid && run === null) run = { from: tx, to: tx };
        else if (!solid) run.to = tx;
        else if (run !== null) { pits.push(run); run = null; }
    }
    ok(pits.length > 0, pits.length + ' pits to cross');

    /**
     * Try to cross a pit with a given technique, jumping as late as possible.
     * Returns true if he lands on the far lip rather than in the hole.
     */
    function cross(pit, technique) {
        const p = vm.runInContext('new Player(__m)', ctx);
        const lipX = pit.from * CONFIG.TILE;
        const startX = Math.max(0, lipX - 90);
        p.box.x = startX;
        p.box.y = floorRow * CONFIG.TILE - CONFIG.PLAYER_H;
        p.grounded = true;
        p.coyote = CONFIG.COYOTE_FRAMES;

        input.allOff();
        input.hold('R');
        if (technique !== 'walk') input.hold('RUN');
        if (technique === 'roll') input.tap('ROLL');

        let jumped = false;
        for (let i = 0; i < 400; i++) {
            // Commit at the last frame there is still ground under his front foot.
            if (!jumped && p.grounded) {
                const frontTx = Math.floor((p.box.x + p.box.w) / CONFIG.TILE);
                if (frontTx >= pit.from - 1) { input.tap('JUMP'); input.hold('JUMP'); jumped = true; }
            }
            p.update(1.0);
            if (p.box.y > map.h + 40) return false;                  // fell in
            if (jumped && p.grounded && p.box.x > pit.to * CONFIG.TILE) return true;
        }
        return false;
    }

    let unclearable = 0;
    const report = [];
    for (const pit of pits) {
        const width = pit.to - pit.from + 1;
        const techniques = ['walk', 'run', 'roll'].filter((t) => cross(pit, t));
        if (techniques.length === 0) {
            unclearable++;
            report.push('pit at tile ' + pit.from + ' (' + width + ' wide) cleared by nothing');
        } else {
            report.push('  tiles ' + String(pit.from).padStart(3) + '-' + String(pit.to).padEnd(3)
                + ' (' + width + ' wide, ' + (width * CONFIG.TILE) + 'px): ' + techniques.join(', '));
        }
    }
    ok(unclearable === 0, 'all ' + pits.length + ' pits can be crossed',
       report.filter((r) => r.indexOf('nothing') >= 0).join('\n          '));
    for (const line of report) if (line.indexOf('nothing') < 0) console.log('      ' + line.trim());

    // The widest pit should need the roll — that is what makes it the level's
    // technique gate rather than decoration.
    const widest = pits.reduce((a, b) => ((b.to - b.from) > (a.to - a.from) ? b : a), pits[0]);
    ok(!cross(widest, 'run') && cross(widest, 'roll'),
       'the widest pit needs a roll-jump, so the roll is load-bearing');
}

// ── The level can actually be finished ────────────────────────────────────────

console.log('\nevery level is completable:');
{
    const probe = makeGame(0);
    const levelCount = probe.LEVELS.length;
    ok(levelCount > 0, levelCount + ' level(s) to check');

    for (let i = 0; i < levelCount; i++) {
        const g = makeGame(i);
        const surfaces = findSurfaces(g.map);
        const env = {
            CONFIG: g.CONFIG, input: g.input, map: g.map, surfaces: surfaces,
            exit: g.map.exit,
            newPlayer: () => vm.runInContext('new Player(__map)', g.ctx),
            // A trolley ride is driven by the real Entities, so it needs a
            // matched pair rather than a lone player.
            newGame: () => ({
                player: vm.runInContext('new Player(__map)', g.ctx),
                entities: vm.runInContext('new Entities(__map)', g.ctx),
            }),
        };
        const r = analyse(env);
        const name = 'level ' + (i + 1) + ' (' + g.map.name + ')';

        ok(r.start >= 0, name + ': the spawn lands on a real surface');
        ok(r.exitReached, name + ': the exit is reachable from the spawn',
           'reached ' + r.reached.size + ' of ' + surfaces.length + ' surfaces');
        ok(r.unreachablePickups.length === 0,
           name + ': every note and letter is reachable',
           r.unreachablePickups.slice(0, 6).join('; '));
        ok(r.survivableRides !== false,
           name + ': every trolley run can be survived',
           'a trolley ends in a hole under every jump timing tried');
        console.log('      ' + surfaces.length + ' surfaces, '
            + r.reached.size + ' reachable, ' + r.edges.length + ' connections');

        // An island of scenery is fine; an island holding something you need
        // is not, and the pickup check above is what tells the two apart.
        if (r.reached.size < surfaces.length) {
            console.log('      (' + (surfaces.length - r.reached.size)
                + ' surface(s) unreached — decorative unless a pickup sits there)');
        }
    }
}

// ── Sound effects ──
// Synthesised rather than sampled, so the decisions — which pitch, when a run
// resets, what each voice is — are pure and testable with no audio hardware.

console.log('\nsound effects:');
{
    const { Sfx } = makeGame(0);

    // Nothing may throw where Web Audio does not exist, which is here and in
    // any browser that refuses an AudioContext.
    let threw = null;
    try { for (const n of Object.keys(Sfx.VOICES)) Sfx.play(n, 0); } catch (e) { threw = e; }
    ok(!threw, 'every voice plays without an AudioContext present', threw && threw.message);
    ok(Sfx.play('jump', 0) === false, 'and reports that it produced nothing');
    ok(Sfx.ensureCtx() === null, 'no context is conjured headlessly');

    // Voice table sanity: a typo here is silence, which is hard to notice.
    let bad = [];
    for (const [name, v] of Object.entries(Sfx.VOICES)) {
        if (!(v.dur > 0 && v.dur < 2)) bad.push(name + '.dur');
        if (!(v.gain > 0 && v.gain <= 1)) bad.push(name + '.gain');
        if (!(v.f0 >= 20 && v.f0 <= 20000)) bad.push(name + '.f0');
        if (!(v.f1 >= 20 && v.f1 <= 20000)) bad.push(name + '.f1');
        if (['sine','square','triangle','sawtooth','noise'].indexOf(v.type) < 0) bad.push(name + '.type');
    }
    ok(bad.length === 0, Object.keys(Sfx.VOICES).length + ' voices are all in range', bad.join(' '));

    // Every arpeggio step must land on a real scale degree.
    let offScale = [];
    for (const [name, arp] of Object.entries(Sfx.ARPS)) {
        for (const step of arp) if (step < 0 || step >= Sfx.SCALE.length) offScale.push(name + ':' + step);
    }
    ok(offScale.length === 0, 'every arpeggio step is on the scale', offScale.join(' '));

    ok(Sfx.stepFrequency(-5) === Sfx.SCALE[0], 'pitch clamps at the bottom of the scale');
    ok(Sfx.stepFrequency(999) === Sfx.SCALE[Sfx.SCALE.length - 1], 'and at the top');

    // A run of pickups climbs; a pause starts a new phrase. Without the reset
    // every trail after the first would play at the top of the scale.
    Sfx.resetRun();
    const climb = [];
    for (let i = 0; i < 6; i++) climb.push(Sfx.advanceRun(1000 + i * 100));
    ok(climb.join(',') === '0,1,2,3,4,5', 'a run of pickups walks up the scale', climb.join(','));

    const after = Sfx.advanceRun(1000 + 5 * 100 + Sfx.RUN_RESET_MS + 1);
    ok(after === 0, 'and a pause longer than RUN_RESET_MS starts again from the bottom');

    Sfx.resetRun();
    const capped = [];
    for (let i = 0; i < Sfx.SCALE.length + 4; i++) capped.push(Sfx.advanceRun(2000 + i * 10));
    ok(Math.max.apply(null, capped) === Sfx.SCALE.length - 1,
       'a long run tops out at the scale rather than running off it');

    Sfx.setMuted(true);
    ok(Sfx.play('stomp', 0) === false, 'muted plays nothing');
    Sfx.setMuted(false);
}

// ── Summary ───────────────────────────────────────────────────────────────────

console.log('\n=== Results: ' + passed + ' passed, ' + failed + ' failed ===');
process.exit(failed > 0 ? 1 : 0);

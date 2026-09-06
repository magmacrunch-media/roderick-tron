/**
 * reachability.js — can this level actually be played?
 *
 * Used by test-simulation.js. Not named test-*.js on purpose: run-tests.mjs
 * collects those, and this is a library rather than a suite.
 *
 * ── Why this replaced a bot ──
 *
 * The first version of the completability check was a scripted bot: hold right,
 * measure the gap ahead, jump or roll. It proved level 1 finishable and would
 * have gone on proving it forever, because level 1 is a straight line along the
 * ground. Give it a level that goes upward, or one where the route doubles
 * back, and it fails — not because the level is broken but because the bot only
 * knows one shape. A guarantee that quietly stops applying as the content grows
 * is worse than no guarantee, since nobody notices it lapsing.
 *
 * So this searches instead of playing. It builds the graph of standable
 * surfaces, works out which ones can be reached from which by actually flying
 * the real Player.update between them, and asks whether the exit is in the
 * connected component containing the spawn.
 *
 * ── The abstraction ──
 *
 * A state is a SURFACE, not a position. Walking from one end of a rooftop to
 * the other is free and uninteresting; what matters is which rooftops connect
 * to which. That collapses a level of ~1500 pixel positions into a few dozen
 * surfaces and makes an exhaustive search cheap.
 *
 * Enemies are ignored deliberately. Reachability is a question about geometry;
 * whether a gargoyle is in the way is a question about difficulty, and the two
 * should not fail together.
 */

const SOLID = '#';
const PLATFORM = '=';
const RAIL = '-';

/**
 * Every horizontally contiguous run of standable tile-tops, as one surface.
 *
 * A surface is (ty, tx0..tx1): the row of the SURFACE, not of the tile beneath
 * it, so a player standing on it has his feet at ty * TILE.
 */
function findSurfaces(map) {
    const surfaces = [];
    for (let ty = 0; ty < map.rows; ty++) {
        let run = null;
        for (let tx = 0; tx < map.cols; tx++) {
            const here = map.tileAt(tx, ty);
            const above = map.tileAt(tx, ty - 1);
            // Standable if this tile is footing and there is room to stand.
            // Rail is standable too: you can walk a rail as well as ride it.
            const standable = (here === SOLID || here === PLATFORM || here === RAIL) && above !== SOLID;
            if (standable) {
                if (run) run.tx1 = tx;
                else { run = { ty: ty, tx0: tx, tx1: tx }; surfaces.push(run); }
            } else {
                run = null;
            }
        }
    }
    return surfaces.map((s, i) => Object.assign(s, { id: i }));
}

/** Which surface is this box standing on, or -1. */
function surfaceUnder(surfaces, box, TILE) {
    const feetY = box.y + box.h;
    for (let i = 0; i < surfaces.length; i++) {
        const s = surfaces[i];
        if (Math.abs(feetY - s.ty * TILE) > 1.5) continue;
        const left = s.tx0 * TILE;
        const right = (s.tx1 + 1) * TILE;
        if (box.x + box.w > left && box.x < right) return s.id;
    }
    return -1;
}

function overlaps(box, r) {
    return box.x < r.x + r.w && box.x + box.w > r.x
        && box.y < r.y + r.h && box.y + box.h > r.y;
}

/**
 * Fly one attempt with the real physics and report where it ends up.
 *
 * `plan` is what a player would do: which way, how fast, whether to roll, and
 * how long to hold the jump. Everything else — collision, coyote time, the
 * roll-jump momentum rule — is the shipped code.
 */
function attempt(env, startX, startTy, plan) {
    const { CONFIG, input, newPlayer, map, surfaces, exit } = env;
    const p = newPlayer();
    p.box.x = startX;
    p.box.y = startTy * CONFIG.TILE - p.box.h;
    p.vx = 0; p.vy = 0;
    p.grounded = true;
    p.coyote = CONFIG.COYOTE_FRAMES;

    input.allOff();
    const steer = () => {
        input.held.L = false; input.held.R = false;
        input.held[plan.dir > 0 ? 'R' : 'L'] = true;
    };
    // `ride` frames of no horizontal input first: that is how a player takes a
    // chimney draught, and holding a direction crosses a two-tile column in
    // eleven frames, long before it has lifted anybody.
    if (!plan.ride) steer();
    if (plan.speed !== 'walk') input.held.RUN = true;

    const from = surfaceUnder(surfaces, p.box, CONFIG.TILE);
    const touched = [];
    const bells = map.bells || [];
    const trolleys = map.trolleys || [];
    let hitExit = false;
    let rolled = false;
    let jumped = false;

    for (let i = 0; i < 200; i++) {
        if (plan.ride && i === plan.ride) steer();
        if (plan.speed === 'roll' && !rolled && i >= plan.runUp - 12 && p.grounded) {
            input.pressed.ROLL = true; input.held.ROLL = true; rolled = true;
        }
        if (!jumped && i >= plan.runUp) {
            if (plan.hold > 0) { input.pressed.JUMP = true; input.held.JUMP = true; }
            jumped = true;
        }
        if (jumped && plan.hold > 0 && i >= plan.runUp + plan.hold) input.held.JUMP = false;

        p.update(1.0);

        if (exit && overlaps(p.box, exit)) hitExit = true;

        for (let k = 0; k < trolleys.length; k++) {
            const t = trolleys[k];
            if (overlaps(p.box, { x: t.x, y: t.y, w: CONFIG.TROLLEY_W, h: CONFIG.TROLLEY_H })) {
                return { to: -1, hitExit: hitExit, fell: false, touched: touched, bell: -1, trolley: k };
            }
        }

        // A bell ends the attempt: it catches you, and where you go next is a
        // question about the bell rather than about this jump.
        for (let k = 0; k < bells.length; k++) {
            const b = bells[k];
            if (overlaps(p.box, { x: b.x, y: b.y, w: CONFIG.BELL_W, h: CONFIG.BELL_H })) {
                return { to: -1, hitExit: hitExit, fell: false, touched: touched, bell: k, trolley: -1 };
            }
        }
        // Pickups are swept, not stood next to: the letter over the roll gap
        // is taken in mid-air, and only flying the arc can show that.
        for (let k = 0; k < env.pickups.length; k++) {
            if (touched.indexOf(k) < 0 && overlaps(p.box, env.pickups[k].item)) touched.push(k);
        }
        if (p.box.y > map.h + CONFIG.FALL_KILL_MARGIN) {
            return { to: -1, hitExit: hitExit, fell: true, touched: touched, bell: -1, trolley: -1 };
        }
        // Settled somewhere new.
        if (p.grounded && i > plan.runUp + 2) {
            const to = surfaceUnder(surfaces, p.box, CONFIG.TILE);
            if (to >= 0 && (to !== from || i > plan.runUp + 20)) {
                return { to: to, hitExit: hitExit, fell: false, touched: touched, bell: -1, trolley: -1 };
            }
        }
    }
    return { to: surfaceUnder(surfaces, p.box, CONFIG.TILE), hitExit: hitExit, fell: false, touched: touched, bell: -1, trolley: -1 };
}

/**
 * Fly out of a bell at one angle.
 *
 * The bell's aim sweeps, so the player chooses the angle by choosing when to
 * press. Sampling across the whole arc is therefore the honest question: is
 * there ANY moment at which firing gets you somewhere useful?
 */
function fire(env, bellIndex, angle) {
    const { CONFIG, input, newPlayer, map, surfaces, exit } = env;
    const b = map.bells[bellIndex];
    const p = newPlayer();
    input.allOff();
    p.box.x = b.x + (CONFIG.BELL_W - p.box.w) / 2;
    p.box.y = b.y + (CONFIG.BELL_H - p.box.h) / 2;
    p.launch(angle);

    // Held forward, as a player steering the arc would.
    input.held[p.vx >= 0 ? 'R' : 'L'] = true;
    input.held.RUN = true;
    input.held.JUMP = true;

    const touched = [];
    let hitExit = false;
    for (let i = 0; i < 260; i++) {
        p.update(1.0);
        if (exit && overlaps(p.box, exit)) hitExit = true;
        for (let k = 0; k < env.pickups.length; k++) {
            if (touched.indexOf(k) < 0 && overlaps(p.box, env.pickups[k].item)) touched.push(k);
        }
        if (p.box.y > map.h + CONFIG.FALL_KILL_MARGIN) {
            return { to: -1, hitExit: hitExit, fell: true, touched: touched };
        }
        if (p.grounded && i > 3) {
            return { to: surfaceUnder(surfaces, p.box, CONFIG.TILE), hitExit, fell: false, touched };
        }
    }
    return { to: -1, hitExit: hitExit, fell: false, touched: touched };
}

/**
 * Ride a trolley to wherever it ends up, under one jump policy.
 *
 * The real Entities drives it, so this is the shipped trolley rather than a
 * model of one. `lookahead` is the whole policy: jump when the rail runs out
 * within that many pixels. Sweeping it from 0 upward sweeps the jump from as
 * late as possible to as early as possible, and for a cart at constant speed
 * the timing of each jump is the only degree of freedom there is — so the sweep
 * covers the ride, even though it is not a search over every frame.
 */
function ride(env, trolleyIndex, lookahead) {
    const { CONFIG, input, map, surfaces, exit, newGame } = env;
    const sim = newGame();
    const p = sim.player;
    const ents = sim.entities;
    const t0 = map.trolleys[trolleyIndex];

    input.allOff();
    // Put him on the trolley by standing him in it.
    p.box.x = t0.x + (CONFIG.TROLLEY_W - p.box.w) / 2;
    p.box.y = t0.y - p.box.h;
    p.grounded = true;

    const touched = [];
    let hitExit = false;
    let crashed = false;

    for (let i = 0; i < 900; i++) {
        const t = ents.trolleys[trolleyIndex];
        if (t && t.riding && t.grounded) {
            // Distance to the first missing footing ahead — the hole, not the
            // track. Scanning for track instead finds it under the wheels at
            // distance zero and jumps every single frame.
            let gapAt = lookahead + 8;
            for (let d = 0; d <= lookahead; d += 2) {
                const probeX = t.x + t.w + d;
                const footing = map.overlapsRail(probeX, t.y + t.h, 2, 4)
                    || map.overlapsSolid(probeX, t.y + t.h, 2, 4);
                if (!footing) { gapAt = d; break; }
            }
            if (gapAt <= lookahead) { input.pressed.JUMP = true; input.held.JUMP = true; }
            else input.held.JUMP = false;
        }

        p.update(1.0);
        ents.update(p, 1.0);
        for (const ev of ents.events) if (ev.type === 'crash') crashed = true;

        if (exit && overlaps(p.box, exit)) hitExit = true;
        for (let k = 0; k < env.pickups.length; k++) {
            if (touched.indexOf(k) < 0 && overlaps(p.box, env.pickups[k].item)) touched.push(k);
        }
        if (p.box.y > map.h + CONFIG.FALL_KILL_MARGIN) {
            return { to: -1, hitExit, fell: true, touched, crashed };
        }
        if (!p.riding && p.grounded && i > 5) {
            return { to: surfaceUnder(surfaces, p.box, CONFIG.TILE), hitExit, fell: false, touched, crashed };
        }
    }
    return { to: -1, hitExit, fell: false, touched, crashed };
}

/** Angles the swing actually passes through, sampled evenly. */
function swingAngles(CONFIG, n) {
    const from = CONFIG.BELL_SWING_FROM * Math.PI / 180;
    const to = CONFIG.BELL_SWING_TO * Math.PI / 180;
    const out = [];
    for (let i = 0; i < n; i++) out.push(from + (to - from) * (i / (n - 1)));
    return out;
}

/**
 * The moves worth trying from a launch point.
 *
 * Deliberately small. Every extra technique multiplies the search, and these
 * five cover the level vocabulary: step off an edge, hop, jump, jump running,
 * and the roll-jump the long gaps are built around.
 */
function plans(dir, runUp) {
    return [
        { dir, speed: 'run',  hold: 0,  runUp },        // walk off the edge
        { dir, speed: 'walk', hold: 5,  runUp },        // short hop
        { dir, speed: 'walk', hold: 30, runUp },
        { dir, speed: 'run',  hold: 30, runUp },
        { dir, speed: 'roll', hold: 30, runUp },
        // Ride a draught up, then steer off the top. The two ride lengths are
        // a short column and a tall one.
        { dir, speed: 'walk', hold: 0, runUp, ride: 45 },
        { dir, speed: 'walk', hold: 0, runUp, ride: 90 },
    ];
}

/**
 * Search outward from the spawn.
 *
 * Returns which surfaces are reachable, whether the exit is among them, and —
 * because a letter you cannot get to is as much a bug as an exit you cannot
 * get to — which pickups sit out of reach.
 */
function analyse(env) {
    const { CONFIG, map } = env;
    if (!env.pickups) {
        const TILE0 = CONFIG.TILE;
        env.pickups = []
            .concat(map.letters.map((l) => ({
                item: l, label: 'letter ' + l.ch + ' at tile '
                    + Math.round(l.x / TILE0) + ',' + Math.round(l.y / TILE0),
            })))
            .concat(map.notes.map((n) => ({
                item: n, label: 'note at tile '
                    + Math.round(n.x / TILE0) + ',' + Math.round(n.y / TILE0),
            })));
    }
    const TILE = CONFIG.TILE;
    const surfaces = env.surfaces;

    // Where the spawn settles. A spawn drawn a little above its rooftop should
    // not count as its own island.
    const start = (function () {
        const p = env.newPlayer();
        env.input.allOff();
        p.box.x = map.spawn.x; p.box.y = map.spawn.y;
        p.vx = 0; p.vy = 0; p.grounded = false;
        for (let i = 0; i < 200 && !p.grounded; i++) p.update(1.0);
        return surfaceUnder(surfaces, p.box, TILE);
    })();

    const reached = new Set();
    const collected = new Set();
    const edges = [];
    let exitReached = false;
    let survivableRides = true;
    if (start < 0) return { start, reached, exitReached, surfaces, edges, unreachablePickups: [] };

    reached.add(start);
    const queue = [start];
    const bellsSeen = new Set();
    const bells = map.bells || [];
    const trolleys = map.trolleys || [];
    const angles = swingAngles(CONFIG, 13);

    const trolleysSeen = new Set();

    /**
     * Ride a trolley under every jump timing, and take the best outcome.
     *
     * "Best" is deliberately generous: a ride that survives under ANY timing
     * counts as passable, because a player gets to choose. What it must not do
     * is count a ride that only ends in a hole.
     */
    const expandTrolley = (k) => {
        if (trolleysSeen.has(k)) return;
        trolleysSeen.add(k);
        let anySurvived = false;
        for (let look = 0; look <= 70; look += 5) {
            const r = ride(env, k, look);
            if (r.fell) continue;
            anySurvived = true;
            if (r.hitExit) exitReached = true;
            for (const t of r.touched) collected.add(t);
            if (r.to >= 0 && !reached.has(r.to)) {
                reached.add(r.to);
                edges.push(['trolley' + k, r.to]);
                queue.push(r.to);
            }
        }
        if (!anySurvived) survivableRides = false;
    };

    /** Fire out of a bell at every angle its swing reaches. */
    const expandBell = (k) => {
        if (bellsSeen.has(k)) return;
        bellsSeen.add(k);
        for (const angle of angles) {
            const r = fire(env, k, angle);
            if (r.hitExit) exitReached = true;
            if (!r.fell) for (const t of r.touched) collected.add(t);
            if (r.to >= 0 && !reached.has(r.to)) {
                reached.add(r.to);
                edges.push(['bell' + k, r.to]);
                queue.push(r.to);
            }
        }
    };

    while (queue.length) {
        const id = queue.shift();
        const s = surfaces[id];

        // Launch from both ends and a few points between: where you leave a
        // rooftop from changes what you can reach off it.
        const points = new Set([s.tx0, s.tx1]);
        for (let tx = s.tx0; tx <= s.tx1; tx += 3) points.add(tx);

        for (const tx of points) {
            for (const dir of [1, -1]) {
                // Run-up is capped by how much of the surface lies behind you.
                const room = dir > 0 ? (tx - s.tx0) : (s.tx1 - tx);
                for (const runUp of [0, Math.min(40, room * 6)]) {
                    for (const plan of plans(dir, runUp)) {
                        const r = attempt(env, tx * TILE, s.ty, plan);
                        if (r.hitExit) exitReached = true;
                        // Only a survived attempt counts. Grabbing a letter on
                        // the way into a pit is not a way of getting it.
                        if (!r.fell) for (const k of r.touched) collected.add(k);
                        if (r.bell >= 0) { edges.push([id, 'bell' + r.bell]); expandBell(r.bell); }
                        if (r.trolley >= 0) { edges.push([id, 'trolley' + r.trolley]); expandTrolley(r.trolley); }
                        if (r.to >= 0 && !reached.has(r.to)) {
                            reached.add(r.to);
                            edges.push([id, r.to]);
                            queue.push(r.to);
                        }
                    }
                }
            }
        }
    }

    // Exact, not estimated: a pickup is reachable if some survivable attempt
    // actually swept it. An earlier version asked whether one lay within a
    // jump's apex of a reachable surface, which is a decent guess on flat
    // ground and wrong everywhere interesting — it called the letter over the
    // roll gap unreachable precisely because reaching it means being in the
    // air, a long way from any surface.
    const unreachablePickups = env.pickups
        .map((e, k) => (collected.has(k) ? null : e.label))
        .filter(Boolean);

    return { start, reached, exitReached, surfaces, edges, unreachablePickups, survivableRides };
}

module.exports = { findSurfaces, surfaceUnder, analyse, swingAngles };

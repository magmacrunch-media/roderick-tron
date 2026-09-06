// entities.js — Roderick Tron | MagmaCrunch Media © 2026
// Enemies, projectiles, pickups, the companion, and the effects for all of it.
//
// Everything here is in WORLD pixels and converted at draw time. The runner
// this replaced kept entities in screen space and hand-scrolled them, which
// only held while the camera moved at one fixed rate.

function Entities(tilemap) {
    this.map = tilemap;
    this.reset();
}

Entities.prototype.reset = function () {
    const map = this.map;
    this.enemies = map.enemies.map(function (e) {
        return {
            kind: e.kind,
            x: e.x, y: e.y,
            homeY: e.y,
            w: CONFIG.GARGOYLE_W, h: CONFIG.GARGOYLE_H,
            dir: -1,
            phase: (e.x * 0.07) % (Math.PI * 2),
            hp: e.kind === 'statue' ? CONFIG.STATUE_HP
                : e.kind === 'flyer' ? CONFIG.FLYER_HP
                : CONFIG.GARGOYLE_HP,
            flash: 0,
            dead: false,
        };
    });
    // Pickups live on the map, so a retry restores them by clearing the flags
    // rather than by reparsing the level.
    map.notes.forEach(function (n) { n.taken = false; });
    map.letters.forEach(function (l) { l.taken = false; });

    this.shots = [];
    this.particles = [];
    this.popups = [];
    this.bird = null;
    this.events = [];
    // A bell per marker, each swinging from its own phase so a row of them
    // does not beat in unison.
    this.trolleys = map.trolleys.map(function (t) {
        return { x: t.x, y: t.y, w: CONFIG.TROLLEY_W, h: CONFIG.TROLLEY_H,
                 vx: 0, vy: 0, riding: false, rolling: false, spent: false };
    });
    this.bells = map.bells.map(function (b, i) {
        return { x: b.x, y: b.y, w: CONFIG.BELL_W, h: CONFIG.BELL_H,
                 phase: i * 0.9, cooldown: 0, holding: false };
    });
};

// ── Projectiles ───────────────────────────────────────────

Entities.prototype.fire = function (player) {
    this.shots.push({
        x: player.box.x + (player.facing > 0 ? player.box.w : -CONFIG.NOTE_W),
        y: player.box.y + 6,
        vx: player.facing * CONFIG.NOTE_SPEED,
        life: CONFIG.NOTE_LIFE,
    });
};

// ── Per-frame ─────────────────────────────────────────────

Entities.prototype.update = function (player, dt) {
    this.events.length = 0;
    this.updateShots(dt);
    this.updateTrolleys(player, dt);
    this.updateBells(player, dt);
    this.updateEnemies(player, dt);
    this.updatePickups(player);
    this.updateBird(player, dt);
    this.updateParticles(dt);
    this.updatePopups(dt);
};

/**
 * The coal trolleys.
 *
 * Board by touching one. From then on the trolley is the thing being simulated
 * and the player is a passenger: it rolls right at a constant speed and the
 * only input that reaches him is jump, which leaps the whole cart.
 *
 * Constant speed is the design. A cart you can slow down is a cart you can wait
 * out, and then a rail with holes in it stops being about commitment and
 * becomes about patience.
 *
 * The ride ends the way a real one would: off the rails the cart rolls to a
 * halt and he steps off. Into a wall it stops hard and throws him. Into a hole
 * it goes down with him, which is a fall like any other.
 */
Entities.prototype.updateTrolleys = function (player, dt) {
    for (let i = 0; i < this.trolleys.length; i++) {
        const t = this.trolleys[i];
        if (t.spent) continue;

        if (!t.riding) {
            // Sitting on its rail, waiting. It does not roll until boarded, so
            // a trolley placed in a level stays where the level put it.
            if (player.riding || player.captured || !player.alive || player.exiting) continue;
            if (!overlap(player.box.x, player.box.y, player.box.w, player.box.h,
                         t.x, t.y, t.w, t.h)) continue;
            t.riding = true;
            t.vx = CONFIG.TROLLEY_SPEED;
            player.board(t);
            this.events.push({ type: 'board', x: t.x, y: t.y });
            continue;
        }

        // ── The ride ──────────────────────────────────────
        const onRail = this.map.overlapsRail(t.x, t.y + t.h, t.w, 2);
        if (onRail) {
            // Back up to speed as soon as there is track under the wheels.
            t.vx += (CONFIG.TROLLEY_SPEED - t.vx) * Math.min(1, 0.2 * dt);
        } else if (t.grounded) {
            t.vx = Math.max(0, t.vx - CONFIG.TROLLEY_DECEL * dt);
        }

        if (Input.jump() && t.grounded) {
            t.vy = CONFIG.TROLLEY_JUMP;
            t.grounded = false;
            this.events.push({ type: 'trolleyJump', x: t.x, y: t.y });
        }

        t.vy += CONFIG.GRAVITY * dt;
        if (t.vy > CONFIG.MAX_FALL) t.vy = CONFIG.MAX_FALL;

        const box = { x: t.x, y: t.y, w: t.w, h: t.h };
        const blocked = this.map.moveX(box, t.vx * dt);
        const land = this.map.moveY(box, t.vy * dt, false);
        t.x = box.x; t.y = box.y;
        t.grounded = land.ground;
        if (land.ground) t.vy = 0;
        if (land.ceiling) t.vy = 0;

        // The passenger rides on top of it.
        player.box.x = t.x + (t.w - player.box.w) / 2;
        player.box.y = t.y - player.box.h + 2;

        if (blocked) {
            // Hit something head on. He is thrown clear; the trolley is done.
            t.spent = true;
            player.dismount(-1.6, -4.2);
            this.events.push({ type: 'crash', x: t.x + t.w / 2 });
            continue;
        }

        if (t.y > this.map.h + CONFIG.FALL_KILL_MARGIN) {
            // Went into a hole. Nothing to do here; main.js sees him fall.
            t.spent = true;
            player.dismount(0, CONFIG.MAX_FALL);
            continue;
        }

        if (t.grounded && !onRail && t.vx <= CONFIG.TROLLEY_DISMOUNT) {
            t.spent = true;
            t.riding = false;
            player.dismount(t.vx, 0);
            this.events.push({ type: 'dismount', x: t.x, y: t.y });
        }
    }
};

/**
 * The bell cannons.
 *
 * A bell catches you, swings through an arc overhead, and fires along whatever
 * angle it is pointing when jump is pressed. Making the aim a moving thing
 * rather than a fixed property is what lets the level file stay a grid of
 * characters: there is no angle to encode, because the timing IS the aim.
 */
Entities.prototype.updateBells = function (player, dt) {
    const from = CONFIG.BELL_SWING_FROM * Math.PI / 180;
    const to = CONFIG.BELL_SWING_TO * Math.PI / 180;

    for (let i = 0; i < this.bells.length; i++) {
        const b = this.bells[i];
        b.phase += CONFIG.BELL_SWING_RATE * dt;
        // A sine rather than a sawtooth, so it eases at the extremes and hangs
        // longest where the aim is most useful.
        b.angle = from + (to - from) * (0.5 - 0.5 * Math.cos(b.phase));
        if (b.cooldown > 0) b.cooldown -= dt;

        if (player.captured === b) {
            // The bell owns his position while it holds him.
            player.box.x = b.x + (b.w - player.box.w) / 2;
            player.box.y = b.y + (b.h - player.box.h) / 2;
            b.holding = true;
            if (Input.jump()) {
                player.launch(b.angle);
                b.cooldown = CONFIG.BELL_RECAPTURE;
                b.holding = false;
                this.events.push({ type: 'launch', x: b.x, y: b.y });
            }
            continue;
        }
        b.holding = false;

        if (player.captured || !player.alive || player.exiting) continue;
        if (b.cooldown > 0) continue;
        if (!overlap(player.box.x, player.box.y, player.box.w, player.box.h, b.x, b.y, b.w, b.h)) continue;

        player.capture(b);
        this.events.push({ type: 'caught', x: b.x, y: b.y });
    }
};

Entities.prototype.updateShots = function (dt) {
    for (let i = this.shots.length - 1; i >= 0; i--) {
        const s = this.shots[i];
        s.x += s.vx * dt;
        s.life -= dt;
        // A note that hits masonry stops there rather than sailing through it.
        if (s.life <= 0 || this.map.overlapsSolid(s.x, s.y, CONFIG.NOTE_W, CONFIG.NOTE_H)) {
            this.spawnParticles(s.x, s.y, 3, CONFIG.COLORS.robotCyan, 10);
            this.shots.splice(i, 1);
            continue;
        }
        for (let j = 0; j < this.enemies.length; j++) {
            const e = this.enemies[j];
            if (e.dead) continue;
            if (!overlap(s.x, s.y, CONFIG.NOTE_W, CONFIG.NOTE_H, e.x, e.y, e.w, e.h)) continue;
            this.damage(e, 1);
            this.shots.splice(i, 1);
            break;
        }
    }
};

Entities.prototype.damage = function (e, n) {
    e.hp -= n;
    e.flash = 6;
    const cx = e.x + e.w / 2;
    const cy = e.y + e.h / 2;
    if (e.hp > 0) {
        this.spawnParticles(cx, cy, 4, CONFIG.COLORS.robotCyan, 12);
        return false;
    }
    e.dead = true;
    this.spawnParticles(cx, cy, 9, CONFIG.COLORS.particleStone, 22);
    this.events.push({ type: 'kill', kind: e.kind, x: cx, y: cy });
    return true;
};

Entities.prototype.updateEnemies = function (player, dt) {
    const p = player.box;

    for (let i = this.enemies.length - 1; i >= 0; i--) {
        const e = this.enemies[i];
        if (e.flash > 0) e.flash -= dt;
        if (e.dead) { this.enemies.splice(i, 1); continue; }

        if (e.kind === 'gargoyle') {
            // Walks, and turns at a wall or a ledge. Checking for footing one
            // step ahead is what keeps them on their own rooftop instead of
            // marching off it within seconds of the level starting.
            const step = e.dir * CONFIG.GARGOYLE_SPEED * dt;
            const ahead = e.x + step + (e.dir > 0 ? e.w : -1);
            if (this.map.overlapsSolid(e.x + step, e.y, e.w, e.h)
                || !this.map.hasFooting(ahead, e.y, 1, e.h)) {
                e.dir *= -1;
            } else {
                e.x += step;
            }
        } else if (e.kind === 'flyer') {
            e.phase += CONFIG.FLYER_BOB_RATE * dt;
            e.y = e.homeY + Math.sin(e.phase) * CONFIG.FLYER_BOB_AMP;
            const step = e.dir * CONFIG.FLYER_SPEED * dt;
            if (this.map.overlapsSolid(e.x + step, e.y, e.w, e.h)) e.dir *= -1;
            else e.x += step;
        }
        // A statue does nothing. That is the point of it.

        if (!player.alive || player.exiting) continue;

        if (!overlap(p.x, p.y, p.w, p.h, e.x, e.y, e.w, e.h)) continue;

        // ── Contact ───────────────────────────────────────
        // A roll goes straight through anything soft.
        if (player.rolling && e.kind !== 'statue') {
            this.damage(e, 99);
            continue;
        }

        // Coming down on it counts as a stomp. Requiring downward motion and
        // feet above its middle is what stops a walk into the side of one from
        // reading as a stomp.
        const falling = player.vy > 0;
        const above = p.y + p.h - player.vy <= e.y + e.h * 0.6;
        if (falling && above) {
            if (e.kind === 'statue') {
                // Too heavy to flatten: you bounce, it does not care.
                player.stompBounce();
                this.spawnParticles(e.x + e.w / 2, e.y, 4, CONFIG.COLORS.particleStone, 10);
                Sfx.play('land');           // it shrugs the stomp off
                continue;
            }
            this.damage(e, 99);
            player.stompBounce();
            Sfx.play('stomp');
            continue;
        }

        this.events.push({ type: 'hurt', x: e.x + e.w / 2 });
    }
};

Entities.prototype.updatePickups = function (player) {
    if (!player.alive) return;
    const p = player.box;

    for (let i = 0; i < this.map.notes.length; i++) {
        const n = this.map.notes[i];
        if (n.taken || !overlap(p.x, p.y, p.w, p.h, n.x, n.y, n.w, n.h)) continue;
        n.taken = true;
        this.spawnParticles(n.x + 4, n.y + 4, 3, CONFIG.COLORS.noteWhite, 12);
        this.events.push({ type: 'note', x: n.x, y: n.y });
    }

    for (let i = 0; i < this.map.letters.length; i++) {
        const l = this.map.letters[i];
        if (l.taken || !overlap(p.x, p.y, p.w, p.h, l.x, l.y, l.w, l.h)) continue;
        l.taken = true;
        this.spawnParticles(l.x + 6, l.y + 6, 6, CONFIG.COLORS.letterGold, 20);
        this.events.push({ type: 'letter', ch: l.ch, x: l.x, y: l.y });
    }
};

/**
 * The clockwork bird.
 *
 * It trails rather than tracks, so it reads as following him rather than being
 * welded on, and it is drawn behind so it never hides the thing you are aiming.
 */
Entities.prototype.updateBird = function (player, dt) {
    if (!player.hasBird) { this.bird = null; return; }
    const tx = player.box.x - player.facing * 13;
    const ty = player.box.y - 9;
    if (!this.bird) { this.bird = { x: tx, y: ty, phase: 0 }; return; }
    const k = Math.min(1, CONFIG.BIRD_FOLLOW_LAG * dt);
    this.bird.x += (tx - this.bird.x) * k;
    this.bird.y += (ty - this.bird.y) * k;
    this.bird.phase += CONFIG.BIRD_BOB_RATE * dt;
};

Entities.prototype.updateParticles = function (dt) {
    for (let i = this.particles.length - 1; i >= 0; i--) {
        const p = this.particles[i];
        p.x += p.vx * dt;
        p.y += p.vy * dt;
        p.vy += 0.16 * dt;
        p.life -= dt;
        if (p.life <= 0) this.particles.splice(i, 1);
    }
};

Entities.prototype.updatePopups = function (dt) {
    for (let i = this.popups.length - 1; i >= 0; i--) {
        const p = this.popups[i];
        p.y -= 0.32 * dt;
        p.life -= dt;
        if (p.life <= 0) this.popups.splice(i, 1);
    }
};

Entities.prototype.spawnParticles = function (x, y, n, color, life) {
    for (let i = 0; i < n; i++) {
        this.particles.push({
            x: x, y: y,
            vx: (Math.random() - 0.5) * 3.2,
            vy: (Math.random() - 1) * 2.4,
            life: life, max: life, color: color,
        });
    }
};

Entities.prototype.addPopup = function (x, y, text, color) {
    this.popups.push({ x: x, y: y, text: text, color: color, life: 44, max: 44 });
};

// ── Drawing ───────────────────────────────────────────────

Entities.prototype.draw = function (ctx, camX, camY, frame) {
    for (let i = 0; i < this.trolleys.length; i++) this.drawTrolley(ctx, this.trolleys[i], camX, camY);
    for (let i = 0; i < this.bells.length; i++) this.drawBell(ctx, this.bells[i], camX, camY);
    for (let i = 0; i < this.enemies.length; i++) this.drawEnemy(ctx, this.enemies[i], camX, camY);
    for (let i = 0; i < this.shots.length; i++) this.drawShot(ctx, this.shots[i], camX, camY);
    for (let i = 0; i < this.particles.length; i++) {
        const p = this.particles[i];
        ctx.globalAlpha = Math.max(0, Math.min(1, p.life / p.max));
        ctx.fillStyle = p.color;
        ctx.fillRect(Math.round(p.x - camX), Math.round(p.y - camY), 2, 2);
        ctx.globalAlpha = 1;
    }
    for (let i = 0; i < this.popups.length; i++) {
        const p = this.popups[i];
        ctx.globalAlpha = Math.max(0, Math.min(1, p.life / p.max));
        ctx.fillStyle = p.color;
        ctx.font = '6px "Press Start 2P", monospace';
        ctx.textAlign = 'center';
        ctx.fillText(p.text, Math.round(p.x - camX), Math.round(p.y - camY));
        ctx.textAlign = 'left';
        ctx.globalAlpha = 1;
    }
    void frame;
};

Entities.prototype.drawBird = function (ctx, camX, camY) {
    if (!this.bird) return;
    const x = Math.round(this.bird.x - camX);
    const y = Math.round(this.bird.y - camY + Math.sin(this.bird.phase) * CONFIG.BIRD_BOB_AMP);
    const C = CONFIG.COLORS;
    const flap = Math.sin(this.bird.phase * 3) > 0 ? 1 : -1;
    ctx.fillStyle = C.birdBrass;
    ctx.fillRect(x + 2, y + 2, 6, 4);
    ctx.fillRect(x + 7, y + 1, 3, 3);
    ctx.fillStyle = C.gargoyleDark;
    ctx.fillRect(x + 9, y + 2, 2, 1);
    ctx.fillStyle = C.birdBrass;
    ctx.fillRect(x + 1, y + 2 - flap * 2, 5, 2);
    ctx.fillStyle = C.robotCyan;
    ctx.fillRect(x + 8, y + 2, 1, 1);
};

Entities.prototype.drawTrolley = function (ctx, t, camX, camY) {
    if (t.spent) return;
    const x = Math.round(t.x - camX);
    const y = Math.round(t.y - camY);
    const C = CONFIG.COLORS;

    // Wheels turn with distance travelled, so a stopped cart has still wheels.
    const spin = Math.floor(t.x / 5) % 2;

    ctx.fillStyle = C.trolleyIron;
    ctx.fillRect(x + 3, y + t.h - 4, 4, 4);
    ctx.fillRect(x + t.w - 7, y + t.h - 4, 4, 4);
    ctx.fillStyle = C.gargoyleDark;
    ctx.fillRect(x + 4 + spin, y + t.h - 3, 2, 2);
    ctx.fillRect(x + t.w - 6 + spin, y + t.h - 3, 2, 2);

    ctx.fillStyle = C.trolleyBody;
    ctx.fillRect(x, y + 2, t.w, t.h - 6);
    ctx.fillStyle = C.trolleyCoal;
    ctx.fillRect(x + 2, y + 3, t.w - 4, 4);
    ctx.fillStyle = C.trolleyIron;
    ctx.fillRect(x, y + 2, t.w, 2);
    ctx.fillRect(x, y + 2, 2, t.h - 6);
    ctx.fillRect(x + t.w - 2, y + 2, 2, t.h - 6);
};

Entities.prototype.drawBell = function (ctx, b, camX, camY) {
    const x = Math.round(b.x - camX);
    const y = Math.round(b.y - camY);
    const C = CONFIG.COLORS;
    const cx = x + b.w / 2;
    const cy = y + b.h / 2;

    // The headstock it hangs from, so it reads as mounted rather than floating.
    ctx.fillStyle = C.gableStone;
    ctx.fillRect(x - 2, y - 6, b.w + 4, 3);
    ctx.fillStyle = C.brickDark;
    ctx.fillRect(x + 2, y - 3, 2, 4);
    ctx.fillRect(x + b.w - 4, y - 3, 2, 4);

    Renderer.glow(ctx, cx, cy, b.holding ? 22 : 14, '201,162,39', b.holding ? 0.34 : 0.18);
    ctx.fillStyle = b.holding ? '#f0d060' : C.bellBrass;
    ctx.fillRect(x + 4, y + 3, b.w - 8, b.h - 9);
    ctx.fillRect(x + 2, y + b.h - 8, b.w - 4, 4);
    ctx.fillStyle = C.bellShadow;
    ctx.fillRect(x + 4, y + b.h - 4, b.w - 8, 2);
    ctx.fillRect(x + b.w - 7, y + 4, 2, b.h - 10);
    ctx.fillStyle = C.bellShadow;
    ctx.fillRect(cx - 1, y + b.h - 4, 2, 3);          // clapper
};

/**
 * The aim, as a line of sparks.
 *
 * Drawn AFTER the player, because a held player sits inside the bell and
 * covered it — hiding the one thing that says when to press, at precisely the
 * moment it is the only thing that matters.
 */
Entities.prototype.drawBellAims = function (ctx, camX, camY) {
    for (let i = 0; i < this.bells.length; i++) {
        const b = this.bells[i];
        if (b.angle === undefined) continue;
        const cx = Math.round(b.x - camX) + b.w / 2;
        const cy = Math.round(b.y - camY) + b.h / 2;
        const reach = b.holding ? CONFIG.BELL_AIM_LEN + 14 : CONFIG.BELL_AIM_LEN;
        for (let d = 10; d <= reach; d += 5) {
            const px = Math.round(cx + Math.cos(b.angle) * d);
            const py = Math.round(cy + Math.sin(b.angle) * d);
            if (b.holding) {
                ctx.fillStyle = 'rgba(0, 245, 255, 0.35)';
                ctx.fillRect(px - 2, py - 2, 4, 4);
            }
            ctx.fillStyle = b.holding ? C_CYAN : 'rgba(201, 162, 39, 0.55)';
            ctx.fillRect(px - 1, py - 1, 2, 2);
        }
    }
};

const C_CYAN = '#00f5ff';

Entities.prototype.drawEnemy = function (ctx, e, camX, camY) {
    const x = Math.round(e.x - camX);
    const y = Math.round(e.y - camY);
    const C = CONFIG.COLORS;
    const lit = e.flash > 0;

    if (e.kind === 'flyer') {
        const beat = Math.sin(e.phase * 4);
        const lift = Math.round(beat * 3);
        ctx.fillStyle = C.flyerWing;
        for (let s = 0; s < 3; s++) {
            const h = 5 - s;
            const dy = y + 3 - Math.round(lift * (s + 1) * 0.6);
            ctx.fillRect(x - 1 - s * 3, dy, 3, h);
            ctx.fillRect(x + 12 + s * 3, dy, 3, h);
        }
    }

    if (e.kind === 'statue') {
        ctx.fillStyle = lit ? '#ffffff' : C.statueStone;
        ctx.fillRect(x, y - 2, 14, 16);
        ctx.fillStyle = C.gargoyleDark;
        ctx.fillRect(x + 2, y + 1, 3, 3);
        ctx.fillRect(x + 9, y + 1, 3, 3);
        ctx.fillStyle = C.gargoyleEye;
        ctx.fillRect(x + 3, y + 2, 1, 1);
        ctx.fillRect(x + 10, y + 2, 1, 1);
        ctx.fillStyle = C.gableStone;
        ctx.fillRect(x, y + 12, 14, 2);
        return;
    }

    ctx.fillStyle = lit ? '#ffffff' : C.gargoyleStone;
    ctx.fillRect(x + 2, y + 4, 10, 8);
    ctx.fillRect(x + 4, y + 1, 6, 5);
    if (!lit) {
        ctx.fillStyle = '#4a4a5c';
        ctx.fillRect(x + 2, y + 10, 10, 2);
        ctx.fillRect(x + 3, y + 4, 1, 6);
    }
    ctx.fillStyle = C.gargoyleDark;
    ctx.fillRect(x + 3, y, 2, 2);
    ctx.fillRect(x + 9, y, 2, 2);
    ctx.fillRect(x + 1, y + 10, 2, 2);
    ctx.fillRect(x + 11, y + 10, 2, 2);

    ctx.fillStyle = 'rgba(255, 61, 110, 0.25)';
    ctx.fillRect(x + 4, y + 1, 4, 4);
    ctx.fillRect(x + 8, y + 1, 4, 4);
    ctx.fillStyle = C.gargoyleEye;
    ctx.fillRect(x + 5, y + 2, 2, 2);
    ctx.fillRect(x + 9, y + 2, 2, 2);
};

Entities.prototype.drawShot = function (ctx, s, camX, camY) {
    const x = Math.round(s.x - camX);
    const y = Math.round(s.y - camY);
    Renderer.glow(ctx, x + 3, y + 4, 9, '0,245,255', 0.30);
    ctx.fillStyle = CONFIG.COLORS.noteWhite;
    ctx.fillRect(x, y + 4, 4, 4);
    ctx.fillRect(x + 1, y + 3, 3, 1);
    ctx.fillRect(x, y + 8, 3, 1);
    ctx.fillRect(x + 4, y, 1, 5);
    ctx.fillRect(x + 5, y, 2, 1);
    ctx.fillRect(x + 5, y + 1, 1, 2);
};

/** AABB overlap, shared by every collision in this file. */
function overlap(ax, ay, aw, ah, bx, by, bw, bh) {
    return ax < bx + bw && ax + aw > bx && ay < by + bh && ay + ah > by;
}

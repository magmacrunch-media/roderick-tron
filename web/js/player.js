// player.js — Roderick Tron | MagmaCrunch Media © 2026
// Roderick: momentum, roll, stomp, damage.
//
// Every per-frame quantity is multiplied by dt, which is 1.0 at 60fps. The
// runner this replaced applied dt to gravity but not to the position step, and
// ran at double speed on a 120Hz display; keeping the discipline is cheaper
// than rediscovering that.

function Player(tilemap) {
    this.map = tilemap;
    this.reset(tilemap.spawn);
    this.lives = CONFIG.MAX_LIVES;
    this.notes = 0;
    this.ammo = CONFIG.NOTE_AMMO_START;
}

Player.prototype.reset = function (spawn) {
    this.box = { x: spawn.x, y: spawn.y, w: CONFIG.PLAYER_W, h: CONFIG.PLAYER_H };
    this.vx = 0;
    this.vy = 0;
    this.facing = 1;
    this.grounded = false;
    this.coyote = 0;
    this.jumpBuffer = 0;
    this.jumping = false;
    this.rolling = false;
    this.rollTimer = 0;
    this.rollCooldown = 0;
    this.invincible = 0;
    this.shootCooldown = 0;
    this.alive = true;
    this.hasBird = true;
    this.animTimer = 0;
    this.runFrame = 0;
    this.shakeFrames = 0;
    this.exiting = false;
    // Set while a bell holds him. Normal physics is suspended: the bell owns
    // his position until it fires.
    this.captured = null;
    // Set while a trolley carries him. Like capture, normal physics is
    // suspended — the trolley owns his position — but unlike capture, jump
    // still does something, because jump is the whole of the sub-mode.
    this.riding = null;
};

/** Height depends on stance: rolling tucks him into a one-tile gap. */
Player.prototype.targetHeight = function () {
    return this.rolling ? CONFIG.ROLL_H : CONFIG.PLAYER_H;
};

Player.prototype.update = function (dt) {
    if (!this.alive) return;

    // Carried. Timers still run; position belongs to the carrier.
    if (this.riding) {
        if (this.invincible > 0) this.invincible -= dt;
        if (this.shakeFrames > 0) this.shakeFrames -= dt;
        if (this.animTimer !== undefined) this.animTimer += dt;
        return;
    }

    // Held by a bell. Timers still run — invincibility should not pause while
    // he waits for the swing — but nothing else does; the bell places him.
    if (this.captured) {
        if (this.invincible > 0) this.invincible -= dt;
        if (this.shakeFrames > 0) this.shakeFrames -= dt;
        this.vx = 0;
        this.vy = 0;
        return;
    }

    const wantLeft = Input.left();
    const wantRight = Input.right();
    const running = Input.run();
    let dir = (wantRight ? 1 : 0) - (wantLeft ? 1 : 0);

    // ── Timers ────────────────────────────────────────────
    if (this.coyote > 0) this.coyote -= dt;
    if (this.jumpBuffer > 0) this.jumpBuffer -= dt;
    if (this.rollCooldown > 0) this.rollCooldown -= dt;
    if (this.invincible > 0) this.invincible -= dt;
    if (this.shootCooldown > 0) this.shootCooldown -= dt;
    if (this.shakeFrames > 0) this.shakeFrames -= dt;
    if (Input.jump()) this.jumpBuffer = CONFIG.JUMP_BUFFER_FRAMES;

    // ── Roll ──────────────────────────────────────────────
    // Committal on purpose: it locks facing and steering for its duration, so
    // the reward for the extra distance is that you had to mean it.
    if (Input.roll() && !this.rolling && this.rollCooldown <= 0 && this.grounded) {
        this.rolling = true;
        this.rollTimer = CONFIG.ROLL_FRAMES;
        if (dir !== 0) this.facing = dir;
        this.vx = this.facing * CONFIG.ROLL_MAX;
        this.headroomAdjust();
        Sfx.play('roll');
    }

    if (this.rolling) {
        this.rollTimer -= dt;
        dir = this.facing;                    // no steering mid-roll
        // Ends on its own timer, or early if it runs out of ground to roll on
        // and the player has not converted it into a jump.
        if (this.rollTimer <= 0 && this.canStand()) {
            this.rolling = false;
            this.rollCooldown = CONFIG.ROLL_COOLDOWN;
            this.headroomAdjust();
        }
    }

    // ── Horizontal ────────────────────────────────────────
    const maxSpeed = this.rolling ? CONFIG.ROLL_MAX
        : running ? CONFIG.RUN_MAX
        : CONFIG.WALK_MAX;
    const accel = this.grounded ? CONFIG.ACCEL : CONFIG.AIR_ACCEL;

    if (dir !== 0) {
        if (!this.rolling) this.facing = dir;
        // Turning bites harder than accelerating, which is what stops a
        // direction change feeling like a slow drift through zero.
        const turning = Math.sign(this.vx) !== 0 && Math.sign(this.vx) !== dir;
        const a = accel * (turning ? CONFIG.TURN_BOOST : 1);
        const next = this.vx + dir * a * dt;

        if (Math.abs(next) < Math.abs(this.vx) || Math.abs(next) <= maxSpeed) {
            // Slowing down, or still inside the cap.
            this.vx = next;
        } else if (Math.abs(this.vx) <= maxSpeed) {
            this.vx = Math.sign(next) * maxSpeed;
        } else {
            // Already over the cap, which only a roll can do. Holding the
            // stick must NOT add to it — an earlier version let it, and since
            // AIR_ACCEL (0.17) is larger than AIR_FRICTION (0.06) a held
            // direction accelerated without limit: 10.8px a frame against a
            // 2.85 cap, straight through the level. Overspeed decays toward
            // the cap and nothing pushes it back up.
            // Bleeds on the ground only. In the air the speed a roll earned is
            // kept for the whole arc, which is what makes a roll-jump a
            // technique rather than a marginal gain.
            const bleed = this.grounded ? CONFIG.FRICTION * dt : 0;
            this.vx = Math.sign(this.vx) * Math.max(maxSpeed, Math.abs(this.vx) - bleed);
        }
    } else {
        const f = (this.grounded ? CONFIG.FRICTION : CONFIG.AIR_FRICTION) * dt;
        if (Math.abs(this.vx) <= f) this.vx = 0;
        else this.vx -= Math.sign(this.vx) * f;
    }

    // ── Jump ──────────────────────────────────────────────
    if (this.jumpBuffer > 0 && this.coyote > 0) {
        this.vy = CONFIG.JUMP_FORCE;
        this.grounded = false;
        this.jumping = true;
        this.jumpBuffer = 0;
        this.coyote = 0;
        Sfx.play('jump');
        // A roll converted into a jump keeps its speed: this is the long-gap
        // technique the levels are built around.
        if (this.rolling && this.canStand()) {
            this.rolling = false;
            this.rollCooldown = CONFIG.ROLL_COOLDOWN;
            this.headroomAdjust();
        }
    }
    if (this.jumping && !Input.jumpHeld() && this.vy < 0) {
        this.vy *= CONFIG.JUMP_CUT;
        this.jumping = false;
    }

    // ── Gravity and movement ──────────────────────────────
    this.vy += CONFIG.GRAVITY * dt;
    if (this.vy > CONFIG.MAX_FALL) this.vy = CONFIG.MAX_FALL;

    // Rising air off a chimney. Not a jump — a sustained climb, which is the
    // only way a level reaches upward at all when a jump clears just 52px.
    // Applied after gravity so it wins, and capped so it lifts rather than
    // flings.
    if (this.map.overlapsUpdraft(this.box.x, this.box.y, this.box.w, this.box.h)) {
        this.vy = Math.max(this.vy - CONFIG.UPDRAFT_LIFT * dt, -CONFIG.UPDRAFT_MAX_RISE);
        const centre = this.map.updraftCentre(this.box.x, this.box.y, this.box.w, this.box.h);
        if (centre !== null) {
            // Settles him toward the middle, so a column is a place you ride
            // rather than one you keep sliding out of.
            const mid = this.box.x + this.box.w / 2;
            this.box.x += Math.sign(centre - mid)
                * Math.min(Math.abs(centre - mid), CONFIG.UPDRAFT_DRIFT * dt);
        }
        this.inUpdraft = true;
    } else {
        this.inUpdraft = false;
    }

    this.map.moveX(this.box, this.vx * dt);

    const wasGrounded = this.grounded;
    const dropping = Input.down() && Input.jump();
    const land = this.map.moveY(this.box, this.vy * dt, dropping);

    if (land.ground) {
        // Only a real fall thumps; resting on the ground re-lands every frame.
        if (!wasGrounded && this.vy > 1.5) Sfx.play('land');
        this.vy = 0;
        this.grounded = true;
        this.jumping = false;
        this.coyote = CONFIG.COYOTE_FRAMES;
    } else {
        if (land.ceiling) this.vy = 0;
        this.grounded = false;
        if (wasGrounded) this.coyote = Math.max(this.coyote, CONFIG.COYOTE_FRAMES);
    }

    // Run cycle speed tracks actual speed, so the legs match the ground.
    if (this.grounded && Math.abs(this.vx) > 0.1) {
        this.animTimer += dt * (0.6 + Math.abs(this.vx) * 0.5);
        if (this.animTimer >= 5) { this.animTimer = 0; this.runFrame = (this.runFrame + 1) % 4; }
    } else if (this.grounded) {
        this.runFrame = 0;
    }
};

/** Is there room to stand up out of a roll where he is? */
Player.prototype.canStand = function () {
    if (!this.rolling) return true;
    const grow = CONFIG.PLAYER_H - CONFIG.ROLL_H;
    return !this.map.overlapsSolid(this.box.x, this.box.y - grow, this.box.w, CONFIG.PLAYER_H);
};

/** Resize the body around its feet when the stance changes. */
Player.prototype.headroomAdjust = function () {
    const bottom = this.box.y + this.box.h;
    this.box.h = this.targetHeight();
    this.box.y = bottom - this.box.h;
};

/** Climbed aboard a trolley. */
Player.prototype.board = function (trolley) {
    this.riding = trolley;
    this.vx = 0;
    this.vy = 0;
    this.grounded = true;
    this.jumping = false;
    if (this.rolling) {
        this.rolling = false;
        this.rollCooldown = CONFIG.ROLL_COOLDOWN;
        this.headroomAdjust();
    }
};

/** Stepped off, with whatever the trolley was doing carried into his own body. */
Player.prototype.dismount = function (vx, vy) {
    this.riding = null;
    this.vx = vx;
    this.vy = vy;
    this.grounded = false;
    this.coyote = CONFIG.COYOTE_FRAMES;
};

/** Caught by a bell. It owns him until it fires. */
Player.prototype.capture = function (bell) {
    this.captured = bell;
    this.vx = 0;
    this.vy = 0;
    this.grounded = false;
    this.jumping = false;
    if (this.rolling) {
        this.rolling = false;
        this.rollCooldown = CONFIG.ROLL_COOLDOWN;
        this.headroomAdjust();
    }
};

/** Fired out of a bell along `angle` radians. */
Player.prototype.launch = function (angle) {
    this.captured = null;
    this.vx = Math.cos(angle) * CONFIG.BELL_LAUNCH;
    this.vy = Math.sin(angle) * CONFIG.BELL_LAUNCH;
    this.grounded = false;
    this.coyote = 0;
    // Counts as a jump in flight, so releasing the button still cuts the arc
    // short and the launch stays steerable in the usual way.
    this.jumping = true;
    if (this.vx !== 0) this.facing = Math.sign(this.vx);
};

/** A stomp landed: bounce, higher if the jump button is still down. */
Player.prototype.stompBounce = function () {
    this.vy = Input.jumpHeld() ? CONFIG.STOMP_BOUNCE_HELD : CONFIG.STOMP_BOUNCE;
    this.grounded = false;
    this.jumping = true;
};

/**
 * Take a hit.
 *
 * The bird is the first thing spent — losing a companion is visible and
 * recoverable where losing a life is neither. Returns 'bird', 'life' or null
 * if the hit was refused because he is still flashing from the last one.
 */
Player.prototype.hurt = function (fromX) {
    if (this.invincible > 0 || !this.alive) return null;
    this.invincible = CONFIG.INVINCIBLE_FRAMES;
    this.shakeFrames = 10;
    const away = this.box.x + this.box.w / 2 < fromX ? -1 : 1;
    this.vx = away * CONFIG.KNOCKBACK_X;
    this.vy = CONFIG.KNOCKBACK_Y;
    this.grounded = false;
    if (this.rolling) {
        this.rolling = false;
        this.rollCooldown = CONFIG.ROLL_COOLDOWN;
        this.headroomAdjust();
    }
    if (this.hasBird) { this.hasBird = false; return 'bird'; }
    this.lives--;
    return 'life';
};

Player.prototype.collect = function (n) {
    this.notes += n;
    this.ammo = Math.min(CONFIG.NOTE_AMMO_MAX, this.ammo + CONFIG.AMMO_PER_PICKUP);
    if (this.notes >= CONFIG.NOTES_PER_LIFE) {
        this.notes -= CONFIG.NOTES_PER_LIFE;
        this.lives++;
        return true;                   // caller announces the extra life
    }
    return false;
};

Player.prototype.canShoot = function () {
    return this.alive && this.ammo > 0 && this.shootCooldown <= 0 && !this.rolling;
};

Player.prototype.spendShot = function () {
    this.ammo--;
    this.shootCooldown = CONFIG.FIRE_RATE;
};

// ── Drawing ───────────────────────────────────────────────

Player.prototype.draw = function (ctx, camX, camY) {
    if (!this.alive) return;
    if (this.invincible > 0 && Math.floor(this.invincible / 4) % 2 === 0) return;

    const x = Math.round(this.box.x - camX);
    const y = Math.round(this.box.y - camY);
    const C = CONFIG.COLORS;
    const f = this.facing;

    if (this.rolling) {
        // A tucked ball. The spin is read off world position, so it rolls at
        // the speed it is actually travelling.
        const spin = Math.floor(this.box.x / 4) % 4;
        ctx.fillStyle = C.robotCoat;
        ctx.fillRect(x, y, 14, 14);
        ctx.fillStyle = C.robotSteel;
        ctx.fillRect(x + 2, y + 2, 10, 10);
        ctx.fillStyle = C.muttonChops;
        ctx.fillRect(x + 4 + (spin % 2) * 4, y + 3 + Math.floor(spin / 2) * 5, 3, 3);
        ctx.fillStyle = C.robotCyan;
        ctx.fillRect(x + 5 + spin, y + 6, 2, 2);
        return;
    }

    // Coat
    ctx.fillStyle = C.robotCoat;
    ctx.fillRect(x + 1, y + 6, 12, 12);
    ctx.fillRect(x + (f > 0 ? 0 : 11), y + 14, 3, 5);      // tail flares behind

    // Head
    ctx.fillStyle = C.robotSteel;
    ctx.fillRect(x + 2, y, 10, 7);

    // Mutton chops
    ctx.fillStyle = C.muttonChops;
    ctx.fillRect(x + 1, y + 3, 2, 4);
    ctx.fillRect(x + 11, y + 3, 2, 4);

    // Eyes, offset toward the way he is facing
    const ex = f > 0 ? 1 : -1;
    ctx.fillStyle = C.robotEyeGlow;
    ctx.fillRect(x + 2 + ex, y + 1, 4, 4);
    ctx.fillRect(x + 8 + ex, y + 1, 4, 4);
    ctx.fillStyle = C.robotCyan;
    ctx.fillRect(x + 3 + ex, y + 2, 2, 2);
    ctx.fillRect(x + 9 + ex, y + 2, 2, 2);

    // Cravat
    ctx.fillStyle = C.gableWhite;
    ctx.fillRect(x + 5, y + 5, 4, 2);

    // Legs
    ctx.fillStyle = C.robotSteel;
    if (!this.grounded) {
        ctx.fillRect(x + 2, y + 18, 4, 4);
        ctx.fillRect(x + 8, y + 17, 4, 4);
    } else if (Math.abs(this.vx) > 0.1) {
        const lift = [0, 2, 0, -1][this.runFrame];
        ctx.fillRect(x + 2, y + 18 + lift, 4, 4 - lift);
        ctx.fillRect(x + 8, y + 18 - lift, 4, 4 + lift);
    } else {
        ctx.fillRect(x + 2, y + 18, 4, 4);
        ctx.fillRect(x + 8, y + 18, 4, 4);
    }

    ctx.fillStyle = C.robotCyan;
    ctx.fillRect(x + 3, y + 21, 1, 1);
    ctx.fillRect(x + 10, y + 21, 1, 1);
};

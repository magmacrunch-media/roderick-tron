// main.js — Roderick Tron | MagmaCrunch Media © 2026
// Loop, state machine, HUD, level lifecycle.

(function () {
    const canvas = document.getElementById('gameCanvas');
    const ctx = canvas.getContext('2d');

    const titleScreen   = document.getElementById('titleScreen');
    const hud           = document.getElementById('hud');
    const scoreDisplay  = document.getElementById('scoreDisplay');
    const livesDisplay  = document.getElementById('livesDisplay');
    const notesDisplay  = document.getElementById('notesDisplay');
    const ammoDisplay   = document.getElementById('ammoDisplay');
    const lettersDisplay = document.getElementById('lettersDisplay');
    const musicDisplay  = document.getElementById('musicDisplay');
    const bannerEl      = document.getElementById('banner');
    const overlay       = document.getElementById('gameOverOverlay');
    const overlayTitle  = document.getElementById('overlayTitle');
    const overlayBody   = document.getElementById('overlayBody');
    const overlayPrompt = document.getElementById('overlayPrompt');

    const STATE = { TITLE: 0, PLAYING: 1, DYING: 2, CLEARED: 3, GAME_OVER: 4 };
    const LETTERS = ['T', 'R', 'O', 'N'];

    let state = STATE.TITLE;
    let titleFrame = 0;
    let lastTime = 0;
    let levelIndex = 0;
    let score = 0;
    let collected = {};          // which of T R O N this run has
    let dyingTimer = 0;
    let bannerTimer = 0;
    let flashAmount = 0;
    let flashColor = '#ffffff';

    let map, player, entities, world, cam;

    // ── Music ─────────────────────────────────────────────
    // Guarded throughout: the game has to stay playable when the shared module
    // is absent, the fetch fails, or decodeAudioData rejects.
    const MUTE_KEY = 'roderickTronMuted';
    let musicReady = false, musicPlaying = false, musicWanted = false;
    let musicMuted = false, musicGen = 0;

    // ── Init ──────────────────────────────────────────────
    function init() {
        // Input first: its keydown listener must be registered before bindUI's,
        // so the press that starts a level is recorded and then cleared, rather
        // than surviving into the level's first frame.
        Input.init();
        bindUI();
        Renderer.bindResize(canvas);
        loadMutePreference();
        initAudio();
        loadLevel(0);
        document.addEventListener('visibilitychange', () => { lastTime = 0; });
        requestAnimationFrame(gameLoop);
    }

    function loadLevel(i) {
        levelIndex = Math.min(i, LEVELS.length - 1);
        map = new Tilemap(LEVELS[levelIndex]);
        player = new Player(map);
        entities = new Entities(map);
        world = new World(map);
        cam = new Camera(map);
        cam.snapTo(player);
        collected = {};
        updateHud();
    }

    /** Put him back at the start of the level with what he still has. */
    function respawn() {
        const lives = player.lives;
        const notes = player.notes;
        player.reset(map.spawn);
        player.lives = lives;
        player.notes = notes;
        player.ammo = Math.max(CONFIG.NOTE_AMMO_START, player.ammo);
        entities.reset();
        cam.snapTo(player);
        state = STATE.PLAYING;
        updateHud();
    }

    // ── Loop ──────────────────────────────────────────────
    function gameLoop(timestamp) {
        requestAnimationFrame(gameLoop);

        if (state === STATE.TITLE) {
            titleFrame++;
            drawTitle();
            lastTime = timestamp;
            return;
        }

        // dt is in 60fps frames. Every per-frame quantity in the game scales by
        // it, so the simulation runs at one rate on any display.
        const dt = lastTime ? Math.min((timestamp - lastTime) / 16.667, 2.0) : 1.0;
        lastTime = timestamp;

        if (state === STATE.PLAYING) update(dt);
        else if (state === STATE.DYING) {
            dyingTimer -= dt;
            player.box.y += 2.4 * dt;                 // he drops out of frame
            if (dyingTimer <= 0) {
                if (player.lives > 0) respawn();
                else finish(false);
            }
        } else if (state === STATE.CLEARED) {
            entities.update(player, dt);
        }

        if (bannerTimer > 0) bannerTimer -= dt;
        if (bannerTimer <= 0 && bannerEl.textContent) bannerEl.textContent = '';
        if (flashAmount > 0) flashAmount -= 0.05 * dt;

        draw();
    }

    function update(dt) {
        player.update(dt);
        cam.update(player, dt);

        if (Input.shoot() && player.canShoot()) {
            player.spendShot();
            entities.fire(player);
            Sfx.play('shoot');
            updateHud();
        }

        entities.update(player, dt);
        handleEvents();

        // Falling out of the level, or into the canal.
        // A bell holds him above the level's own floor in some layouts, and a
        // captured player is not falling by definition.
        const belowFloor = !player.captured && player.box.y > map.h + CONFIG.FALL_KILL_MARGIN;
        const drowned = map.overlapsWater(player.box.x, player.box.y, player.box.w, player.box.h);
        if (belowFloor || drowned) return die();

        if (map.exit && !player.exiting
            && rectsOverlap(player.box, map.exit)) {
            clearLevel();
        }
    }

    function handleEvents() {
        for (let i = 0; i < entities.events.length; i++) {
            const ev = entities.events[i];

            if (ev.type === 'note') {
                score += CONFIG.NOTE_POINTS;
                // Pitched, so a trail of pickups plays a rising phrase.
                Sfx.play('note');
                if (player.collect(1)) {
                    entities.addPopup(ev.x, ev.y, '1UP', CONFIG.COLORS.lifeHeart);
                    banner('EXTRA LIFE');
                    Sfx.play('oneUp');
                }
            } else if (ev.type === 'letter') {
                collected[ev.ch] = true;
                score += CONFIG.LETTER_POINTS;
                entities.addPopup(ev.x, ev.y, ev.ch, CONFIG.COLORS.letterGold);
                Sfx.play('letter');
                if (LETTERS.every((c) => collected[c])) {
                    score += 1000;
                    banner('T R O N  COMPLETE');
                }
            } else if (ev.type === 'board') {
                Sfx.play('board');
                banner('HOLD ON');
            } else if (ev.type === 'trolleyJump') {
                Sfx.play('jump');
            } else if (ev.type === 'dismount') {
                Sfx.play('dismount');
            } else if (ev.type === 'crash') {
                Sfx.play('crash');
                flash(0.3, CONFIG.COLORS.lifeHeart);
                entities.spawnParticles(ev.x, player.box.y + 10, 10,
                                        CONFIG.COLORS.trolleyIron, 22);
                player.hurt(ev.x);
                if (player.lives <= 0) return die();
            } else if (ev.type === 'caught') {
                Sfx.play('caught');
            } else if (ev.type === 'launch') {
                Sfx.play('launch');
                entities.spawnParticles(ev.x + CONFIG.BELL_W / 2, ev.y + CONFIG.BELL_H / 2,
                                        7, CONFIG.COLORS.bellBrass, 18);
            } else if (ev.type === 'kill') {
                score += CONFIG.KILL_POINTS;
                entities.addPopup(ev.x, ev.y - 6, '+' + CONFIG.KILL_POINTS, CONFIG.COLORS.noteWhite);
            } else if (ev.type === 'hurt') {
                const lost = player.hurt(ev.x);
                if (lost === 'bird') {
                    Sfx.play('birdLost');
                    banner('THE BIRD IS GONE');
                    flash(0.28, CONFIG.COLORS.birdBrass);
                    entities.spawnParticles(player.box.x + 7, player.box.y + 8, 8,
                                            CONFIG.COLORS.birdBrass, 24);
                } else if (lost === 'life') {
                    Sfx.play('hurt');
                    flash(0.34, CONFIG.COLORS.lifeHeart);
                    if (player.lives <= 0) return die();
                }
            }
            updateHud();
        }
    }

    function die() {
        if (state !== STATE.PLAYING) return;
        // A fall spends a life directly; there is no bird to spend on a pit.
        if (player.hasBird === false && player.lives > 0) player.lives--;
        else if (player.hasBird) { player.hasBird = false; player.lives--; }
        Sfx.play('hurt');
        state = STATE.DYING;
        dyingTimer = 48;
        player.alive = false;
        flash(0.4, CONFIG.COLORS.lifeHeart);
        updateHud();
    }

    function clearLevel() {
        player.exiting = true;
        score += CONFIG.EXIT_POINTS;
        Sfx.play('exit');
        state = STATE.CLEARED;
        stopMusic();
        const got = LETTERS.filter((c) => collected[c]).length;
        const total = map.notes.length;
        const taken = map.notes.filter((n) => n.taken).length;
        overlayTitle.textContent = 'LEVEL CLEAR';
        overlayBody.innerHTML =
            '<div>' + escapeHtml(map.name) + '</div>' +
            '<div class="stat">NOTES ' + taken + ' / ' + total + '</div>' +
            '<div class="stat">LETTERS ' + got + ' / 4</div>' +
            '<div class="stat">SCORE ' + score + '</div>';
        overlayPrompt.textContent = levelIndex + 1 < LEVELS.length
            ? 'PRESS SPACE FOR THE NEXT ROOF'
            : 'PRESS SPACE TO PLAY AGAIN';
        overlay.classList.add('active');
    }

    function finish(won) {
        state = STATE.GAME_OVER;
        stopMusic();
        overlayTitle.textContent = won ? 'FIN' : 'GAME OVER';
        overlayBody.innerHTML = '<div class="stat">SCORE ' + score + '</div>';
        overlayPrompt.textContent = 'PRESS SPACE TO TRY AGAIN';
        overlay.classList.add('active');
        hud.classList.remove('active');
    }

    function startRun() {
        score = 0;
        loadLevel(0);
        beginLevel();
    }

    function beginLevel() {
        state = STATE.PLAYING;
        lastTime = 0;
        Input.clearJustPressed();     // the Space that got here must not also jump
        Sfx.resetRun();               // each level's phrases start from the bottom
        overlay.classList.remove('active');
        titleScreen.classList.add('hidden');
        hud.classList.add('active');
        banner(map.name);
        startMusic();
        updateHud();
    }

    function advance() {
        if (levelIndex + 1 < LEVELS.length) {
            const carried = { lives: player.lives, notes: player.notes, score: score };
            loadLevel(levelIndex + 1);
            player.lives = carried.lives;
            player.notes = carried.notes;
            beginLevel();
        } else {
            finish(true);
        }
    }

    // ── Draw ──────────────────────────────────────────────
    function draw() {
        ctx.clearRect(0, 0, CONFIG.CANVAS_W, CONFIG.CANVAS_H);
        const shake = Renderer.shakeOffset(player.shakeFrames);
        ctx.save();
        ctx.translate(shake.x, shake.y);

        world.draw(ctx, cam);
        entities.drawBird(ctx, cam.x, cam.y);
        entities.draw(ctx, cam.x, cam.y, titleFrame);
        player.draw(ctx, cam.x, cam.y);
        entities.drawBellAims(ctx, cam.x, cam.y);

        ctx.restore();
        Renderer.vignette(ctx);
        Renderer.flash(ctx, flashAmount, flashColor);
    }

    function drawTitle() {
        const C = CONFIG.COLORS;
        const g = ctx.createLinearGradient(0, 0, 0, CONFIG.CANVAS_H);
        g.addColorStop(0, C.sky);
        g.addColorStop(0.7, C.skyHorizon);
        g.addColorStop(1, C.canalBlue);
        ctx.fillStyle = g;
        ctx.fillRect(0, 0, CONFIG.CANVAS_W, CONFIG.CANVAS_H);

        const drift = { x: titleFrame * 0.35, y: 0 };
        World.prototype.drawFar.call({ map: map }, ctx, drift);
        World.prototype.drawMid.call({ map: map }, ctx, drift);
        Renderer.vignette(ctx);
    }

    // ── HUD ───────────────────────────────────────────────
    function updateHud() {
        scoreDisplay.textContent = String(score).padStart(6, '0');
        notesDisplay.textContent = '♪ ' + player.notes;
        ammoDisplay.textContent = '♩ ' + player.ammo;

        let hearts = '';
        for (let i = 0; i < Math.max(CONFIG.MAX_LIVES, player.lives); i++) {
            hearts += '<div class="hud-life' + (i >= player.lives ? ' lost' : '') + '"></div>';
        }
        if (player.hasBird) hearts += '<div class="hud-bird" title="the bird takes the next hit"></div>';
        livesDisplay.innerHTML = hearts;

        let letters = '';
        for (let i = 0; i < LETTERS.length; i++) {
            letters += '<span class="letter' + (collected[LETTERS[i]] ? ' got' : '') + '">'
                + LETTERS[i] + '</span>';
        }
        lettersDisplay.innerHTML = letters;
    }

    function banner(text) {
        bannerEl.textContent = text;
        bannerTimer = 130;
    }

    function flash(amount, color) {
        flashAmount = amount;
        flashColor = color;
    }

    function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g, (c) => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
        })[c]);
    }

    function rectsOverlap(a, b) {
        return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
    }

    // ── Music ─────────────────────────────────────────────
    async function initAudio() {
        if (typeof AdAudio === 'undefined') return;
        try {
            // iOS has no Ogg Vorbis decoder and every browser there is WebKit, so
            // an ogg-only track is not quieter on an iPhone, it is silent. This
            // game borrows its music from music/jukebox/songs/, which is why it
            // was missed when makemecookies, SORRY, george-boole and
            // moonlight-drift were fixed - the four that were checked all keep
            // their audio in their own folder. Every jukebox track now exists as
            // both .ogg and .mp3. See AGENTS.md, "Audio needs two formats".
            const oggUrl = CONFIG.MUSIC.URL;
            const oggOk = document.createElement('audio')
                .canPlayType('audio/ogg; codecs="vorbis"') !== '';
            const musicUrl = oggOk ? oggUrl : oggUrl.replace(/\.ogg$/, '.mp3');
            await AdAudio.init({
                music: {
                    url: musicUrl,
                    volume: CONFIG.MUSIC.VOLUME,
                    fadeIn: CONFIG.MUSIC.FADE_IN,
                },
            });
            // Safe since adenosine-audio 0.3.1: the pause path banks the
            // playhead and the resume path only restores what it paused.
            AdAudio.handleVisibility({ pauseMusic: true });
            AdAudio.setMusicMuted(musicMuted, 0);
            musicReady = true;
            if (musicWanted) startMusic();
        } catch (e) {
            musicReady = false;
        }
    }

    function startMusic() {
        musicWanted = true;
        if (!musicReady) return;
        musicGen++;
        AdAudio.setMusicVolume(CONFIG.MUSIC.VOLUME, 0.01);
        if (musicPlaying) return;
        musicPlaying = true;
        try { AdAudio.playMusic(CONFIG.MUSIC.FADE_IN); }
        catch (e) { musicPlaying = false; }
    }

    function stopMusic() {
        musicWanted = false;
        if (!musicReady || !musicPlaying) return;
        musicPlaying = false;
        const gen = ++musicGen;
        const fade = CONFIG.MUSIC.FADE_OUT;
        AdAudio.setMusicVolume(0, fade);
        setTimeout(() => {
            if (gen !== musicGen) return;      // a new level began; leave it playing
            try {
                AdAudio.stopMusic();
                AdAudio.setMusicVolume(CONFIG.MUSIC.VOLUME, 0.01);
            } catch (e) { /* nothing to stop */ }
        }, fade * 1000 + 80);
    }

    function loadMutePreference() {
        try { musicMuted = localStorage.getItem(MUTE_KEY) === '1'; }
        catch (e) { musicMuted = false; }
        Sfx.setMuted(musicMuted);
        updateMusicDisplay();
    }

    function toggleMute() {
        musicMuted = !musicMuted;
        if (musicReady) AdAudio.setMusicMuted(musicMuted);
        Sfx.setMuted(musicMuted);
        try { localStorage.setItem(MUTE_KEY, musicMuted ? '1' : '0'); }
        catch (e) { /* private browsing */ }
        updateMusicDisplay();
    }

    function updateMusicDisplay() {
        if (!musicDisplay) return;
        musicDisplay.classList.toggle('muted', musicMuted);
        musicDisplay.title = musicMuted ? 'music off (M)' : 'music on (M)';
    }

    // ── Input bindings ────────────────────────────────────
    function bindUI() {
        document.addEventListener('keydown', (e) => {
            if (e.code === 'KeyM') {
                e.preventDefault();
                toggleMute();
                return;
            }
            if (e.code !== 'Space' && e.code !== 'Enter') return;
            if (state === STATE.TITLE) { e.preventDefault(); startRun(); }
            else if (state === STATE.CLEARED) { e.preventDefault(); advance(); }
            else if (state === STATE.GAME_OVER) { e.preventDefault(); startRun(); }
        });
    }

    init();
})();

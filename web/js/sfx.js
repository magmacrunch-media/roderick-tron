// sfx.js — Roderick Tron | MagmaCrunch Media © 2026
// Synthesised sound effects.
//
// Nothing here is sampled. The game is about a composer who fires musical
// notes, so the effects are generated from oscillators at runtime: no assets to
// download, no cache-busters on binaries, and pickups can be *pitched* rather
// than merely triggered.
//
// That last part is the point. Collecting a run of notes walks up a pentatonic
// scale, so following one of the level's note trails plays a rising phrase.
// The trails were already the game's way of teaching a jump without a tutorial;
// this makes them audible as well as visible.
//
// The decisions — which pitch, when a run resets, what each voice looks like —
// are pure functions, so they are testable with no audio hardware anywhere near
// them. Only `play()` touches the Web Audio API, and it no-ops without it.

const Sfx = {
    ctx: null,
    muted: false,
    noiseBuffer: null,

    /** A minor pentatonic, two octaves. Moody enough for a night rooftop. */
    SCALE: [220.00, 261.63, 293.66, 329.63, 392.00,
            440.00, 523.25, 587.33, 659.25, 783.99],

    // A run of pickups climbs the scale; a pause resets it to the bottom, so
    // every trail starts low and rises rather than continuing from wherever the
    // last one happened to stop.
    RUN_RESET_MS: 900,
    runStep: 0,
    runLast: -1e9,

    /**
     * Voice definitions.
     *
     * `type` is an oscillator shape or 'noise'; `f0`/`f1` sweep the pitch over
     * `dur` seconds; `gain` is the peak before the envelope. Kept as data so a
     * test can assert every sound is defined and sane without producing any.
     */
    VOICES: {
        jump:     { type: 'square',   f0: 300, f1: 620, dur: 0.11, gain: 0.16 },
        land:     { type: 'sine',     f0: 180, f1:  70, dur: 0.09, gain: 0.20 },
        stomp:    { type: 'noise',    f0: 900, f1: 120, dur: 0.16, gain: 0.34 },
        roll:     { type: 'noise',    f0: 420, f1: 1500, dur: 0.26, gain: 0.16 },
        shoot:    { type: 'triangle', f0: 880, f1: 1320, dur: 0.08, gain: 0.13 },
        hurt:     { type: 'sawtooth', f0: 420, f1:  90, dur: 0.30, gain: 0.24 },
        birdLost: { type: 'triangle', f0: 900, f1: 160, dur: 0.42, gain: 0.22 },
        letter:   { type: 'square',   f0: 523, f1: 523, dur: 0.10, gain: 0.18 },
        oneUp:    { type: 'square',   f0: 440, f1: 440, dur: 0.09, gain: 0.18 },
        exit:     { type: 'triangle', f0: 392, f1: 392, dur: 0.30, gain: 0.20 },
        note:     { type: 'triangle', f0: 440, f1: 440, dur: 0.13, gain: 0.15 },
        caught:   { type: 'sine',     f0: 660, f1: 330, dur: 0.18, gain: 0.20 },
        launch:   { type: 'square',   f0: 330, f1: 990, dur: 0.22, gain: 0.22 },
        updraft:  { type: 'noise',    f0: 200, f1: 800, dur: 0.40, gain: 0.10 },
        board:    { type: 'square',   f0: 160, f1: 300, dur: 0.14, gain: 0.20 },
        crash:    { type: 'noise',    f0: 1400, f1: 90, dur: 0.34, gain: 0.36 },
        dismount: { type: 'sine',     f0: 300, f1: 180, dur: 0.14, gain: 0.16 },
    },

    /** Little melodies, as scale-step offsets played in sequence. */
    ARPS: {
        letter: [0, 2, 4],
        oneUp:  [0, 2, 4, 7],
        exit:   [4, 2, 0],
    },

    // ── Pure decisions ────────────────────────────────────

    /** Pitch for the nth step of a pickup run, clamped to the scale. */
    stepFrequency(step) {
        const i = Math.max(0, Math.min(this.SCALE.length - 1, step));
        return this.SCALE[i];
    },

    /**
     * Advance the pickup run and return the step to play.
     *
     * A gap longer than RUN_RESET_MS starts a new phrase. Without that, a run
     * would top out at the highest note within the first level and stay there.
     */
    advanceRun(nowMs) {
        if (nowMs - this.runLast > this.RUN_RESET_MS) this.runStep = 0;
        else this.runStep = Math.min(this.runStep + 1, this.SCALE.length - 1);
        this.runLast = nowMs;
        return this.runStep;
    },

    // ── Audio ─────────────────────────────────────────────

    /**
     * The AudioContext, created on first use.
     *
     * Its own, because adenosine-audio keeps its context private and its sfx
     * loader only accepts URLs. Returns null anywhere Web Audio is absent —
     * headless tests included — and every caller tolerates that.
     */
    ensureCtx() {
        if (this.ctx) return this.ctx;
        const AC = (typeof window !== 'undefined')
            && (window.AudioContext || window.webkitAudioContext);
        if (!AC) return null;
        try { this.ctx = new AC(); } catch (e) { this.ctx = null; }
        return this.ctx;
    },

    setMuted(muted) { this.muted = !!muted; },

    /** One second of white noise, built once and reused by the noise voices. */
    getNoise(ctx) {
        if (this.noiseBuffer) return this.noiseBuffer;
        const n = Math.floor(ctx.sampleRate * 0.4);
        const buf = ctx.createBuffer(1, n, ctx.sampleRate);
        const d = buf.getChannelData(0);
        for (let i = 0; i < n; i++) d[i] = Math.random() * 2 - 1;
        this.noiseBuffer = buf;
        return buf;
    },

    /** Schedule one voice. `freq` overrides the voice's own f0/f1 sweep. */
    voice(name, freq, delay) {
        const ctx = this.ensureCtx();
        if (!ctx || this.muted) return false;
        const v = this.VOICES[name];
        if (!v) return false;

        const t0 = ctx.currentTime + (delay || 0);
        const gain = ctx.createGain();
        gain.connect(ctx.destination);
        // A short attack rather than an instant one: a hard start clicks.
        gain.gain.setValueAtTime(0.0001, t0);
        gain.gain.exponentialRampToValueAtTime(v.gain, t0 + 0.008);
        gain.gain.exponentialRampToValueAtTime(0.0001, t0 + v.dur);

        let src;
        if (v.type === 'noise') {
            src = ctx.createBufferSource();
            src.buffer = this.getNoise(ctx);
            const filter = ctx.createBiquadFilter();
            filter.type = 'bandpass';
            filter.frequency.setValueAtTime(v.f0, t0);
            filter.frequency.exponentialRampToValueAtTime(Math.max(40, v.f1), t0 + v.dur);
            filter.Q.value = 1.4;
            src.connect(filter);
            filter.connect(gain);
        } else {
            src = ctx.createOscillator();
            src.type = v.type;
            const a = freq || v.f0;
            const b = freq || v.f1;
            src.frequency.setValueAtTime(a, t0);
            if (b !== a) src.frequency.exponentialRampToValueAtTime(Math.max(20, b), t0 + v.dur);
            src.connect(gain);
        }

        src.start(t0);
        src.stop(t0 + v.dur + 0.02);
        return true;
    },

    /**
     * Play a named effect.
     *
     * 'note' is the pitched one: it climbs the scale for as long as pickups keep
     * coming. Anything with an entry in ARPS plays as a small melody.
     */
    play(name, nowMs) {
        if (this.muted) return false;
        if (!this.ensureCtx()) return false;

        if (name === 'note') {
            const step = this.advanceRun(nowMs === undefined ? Date.now() : nowMs);
            return this.voice('note', this.stepFrequency(step), 0);
        }

        const arp = this.ARPS[name];
        if (arp) {
            const base = name === 'exit' ? 2 : 0;
            for (let i = 0; i < arp.length; i++) {
                this.voice(name, this.stepFrequency(base + arp[i]), i * 0.07);
            }
            return true;
        }

        return this.voice(name, null, 0);
    },

    /** Forget the pitch run, so a new level starts its phrases from the bottom. */
    resetRun() {
        this.runStep = 0;
        this.runLast = -1e9;
    },
};

// renderer.js — Roderick Tron | MagmaCrunch Media © 2026
// Screen effects and canvas presentation.

const Renderer = {
    /**
     * Size the canvas element so one game pixel covers a whole number of screen
     * pixels wherever there is room for it.
     *
     * The canvas is 480x270 and stretched to fill the viewport, so on anything
     * that is not an exact multiple some game pixels land two screen pixels wide
     * and their neighbours one — a visible shimmer as the world scrolls past.
     * Snapping to an integer scale fixes that, but only above 2x: rounding a
     * 1.6x-sized window down to 1x would shrink the game to a stamp in the
     * middle of the screen, which is a worse trade than an uneven pixel.
     */
    fit(canvas) {
        const fit = Math.min(
            window.innerWidth / CONFIG.CANVAS_W,
            window.innerHeight / CONFIG.CANVAS_H
        );
        const scale = fit >= 2 ? Math.floor(fit) : fit;
        canvas.style.width = Math.round(CONFIG.CANVAS_W * scale) + 'px';
        canvas.style.height = Math.round(CONFIG.CANVAS_H * scale) + 'px';
    },

    bindResize(canvas) {
        this.fit(canvas);
        window.addEventListener('resize', () => this.fit(canvas));
    },

    /**
     * Soft radial glow. Filling an arc() at a flat low alpha does not read as
     * light — it reads as a grey disc with a hard rim, which is what the moon
     * halo and every gas lamp looked like before this existed.
     */
    glow(ctx, x, y, radius, rgb, alpha) {
        const g = ctx.createRadialGradient(x, y, 0, x, y, radius);
        g.addColorStop(0, 'rgba(' + rgb + ',' + alpha + ')');
        g.addColorStop(0.5, 'rgba(' + rgb + ',' + (alpha * 0.4).toFixed(3) + ')');
        g.addColorStop(1, 'rgba(' + rgb + ',0)');
        ctx.fillStyle = g;
        ctx.fillRect(x - radius, y - radius, radius * 2, radius * 2);
    },

    /** Random offset for a screen shake of the given strength, in game pixels. */
    shakeOffset(frames) {
        if (frames <= 0) return { x: 0, y: 0 };
        const mag = Math.min(frames, 12) * 0.8;
        return {
            x: Math.round((Math.random() - 0.5) * mag),
            y: Math.round((Math.random() - 0.5) * mag),
        };
    },

    /** Corner darkening — pulls the eye to the middle of a very wide playfield. */
    vignette(ctx) {
        if (!this._vignette) {
            const g = ctx.createRadialGradient(
                CONFIG.CANVAS_W / 2, CONFIG.CANVAS_H / 2, CONFIG.CANVAS_H * 0.35,
                CONFIG.CANVAS_W / 2, CONFIG.CANVAS_H / 2, CONFIG.CANVAS_W * 0.72
            );
            g.addColorStop(0, 'rgba(0,0,0,0)');
            g.addColorStop(1, 'rgba(0,0,0,0.45)');
            this._vignette = g;
        }
        ctx.fillStyle = this._vignette;
        ctx.fillRect(0, 0, CONFIG.CANVAS_W, CONFIG.CANVAS_H);
    },

    /** White wash on taking a hit, and a cyan one when a distance marker passes. */
    flash(ctx, amount, color) {
        if (amount <= 0) return;
        ctx.globalAlpha = Math.min(0.5, amount);
        ctx.fillStyle = color;
        ctx.fillRect(0, 0, CONFIG.CANVAS_W, CONFIG.CANVAS_H);
        ctx.globalAlpha = 1;
    },
};

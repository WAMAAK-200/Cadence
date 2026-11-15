/*
 * theme.js: light / dark handling shared by every page.
 *
 * Loaded in <head>, straight after <meta name="color-scheme">, so the right theme is
 * applied before the page paints (no white flash in dark mode).
 *
 * - By default the app follows the phone or computer setting.
 * - The "Light / dark" button stores an override only when it differs from that setting;
 *   switching back to match the system removes the override, so the app follows the system again.
 * - The resolved theme is written to <html data-theme="light|dark"> for the CSS.
 * - Without JavaScript, the CSS falls back to prefers-color-scheme on its own.
 */
(function () {
    const KEY = 'color-scheme';
    const system = window.matchMedia('(prefers-color-scheme: dark)');

    function readOverride() {
        try {
            const value = localStorage.getItem(KEY);
            if (value === 'dark' || value === 'light') return value;
            // Older versions stored dark-mode=true when the user switched to dark.
            if (localStorage.getItem('dark-mode') === 'true') return 'dark';
        } catch (e) { /* storage blocked: just follow the system */ }
        return null;
    }

    let override = readOverride();

    function apply() {
        const scheme = override || (system.matches ? 'dark' : 'light');
        document.documentElement.dataset.theme = scheme;
        const meta = document.querySelector('meta[name="color-scheme"]');
        if (meta) meta.content = override || 'light dark';
    }

    apply();
    system.addEventListener('change', apply);
    // Keep other open tabs in step.
    window.addEventListener('storage', e => {
        if (e.key === KEY || e.key === 'dark-mode') { override = readOverride(); apply(); }
    });

    // Returns the theme now showing ('light' or 'dark').
    window.cadenceToggleTheme = function cadenceToggleTheme() {
        const target = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
        const systemScheme = system.matches ? 'dark' : 'light';
        override = target === systemScheme ? null : target;
        try {
            if (override) localStorage.setItem(KEY, override);
            else localStorage.removeItem(KEY);
            localStorage.removeItem('dark-mode');
        } catch (e) { /* the theme still changes for this page */ }
        apply();
        return target;
    };
})();

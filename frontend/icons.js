/*
 * icons.js: one small set of line icons used across every page, in place of emoji.
 *
 * Usage in HTML:  <svg class="icon" aria-hidden="true" focusable="false"><use href="#i-moon"></use></svg>
 * Usage in JS:    element.insertAdjacentHTML('afterbegin', cadenceIcon('moon'));
 *
 * Icons are drawn on a 24px grid with a 1.75 stroke in currentColor, so they follow
 * the text colour (light, dark and high-contrast modes all work without extra CSS).
 */
(function () {
    const PATHS = {
        sliders: '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
        contrast: '<circle cx="12" cy="12" r="9"/><path d="M12 3a9 9 0 0 1 0 18z" fill="currentColor" stroke="none"/>',
        moon: '<path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z"/>',
        user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
        'user-plus': '<circle cx="10" cy="8" r="4"/><path d="M2.5 21a7.5 7.5 0 0 1 13-5"/><path d="M19 14v6M16 17h6"/>',
        'text-size': '<path d="M3 7V5h11v2M8.5 5v14M6.5 19h4"/><path d="M14 12v-1.5h7V12M17.5 10.5V19M16 19h3"/>',
        spacing: '<path d="M3 12h18M6.5 8.5 3 12l3.5 3.5M17.5 8.5 21 12l-3.5 3.5"/>',
        gauge: '<path d="M4 17a8 8 0 1 1 16 0"/><path d="m12 17 4-5.5"/><circle cx="12" cy="17" r="1" fill="currentColor"/>',
        battery: '<rect x="2" y="7" width="17" height="10" rx="2"/><path d="M22 10.5v3M5.5 10.5v3"/>',
        book: '<path d="M5 4.5A1.5 1.5 0 0 1 6.5 3H19v15H6.5A1.5 1.5 0 0 0 5 19.5z"/><path d="M5 19.5A1.5 1.5 0 0 0 6.5 21H19M9 7h6"/>',
        briefcase: '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8.5 7V5.5A1.5 1.5 0 0 1 10 4h4a1.5 1.5 0 0 1 1.5 1.5V7M3 13h18"/>',
        star: '<path d="m12 3.5 2.6 5.3 5.8.8-4.2 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8-4.2-4.1 5.8-.8z"/>',
        printer: '<path d="M6.5 9V3.5h11V9"/><rect x="3" y="9" width="18" height="8" rx="2"/><path d="M7 14h10v6.5H7z"/>',
        mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M9 21h6"/>'
    };

    function injectSprite() {
        if (document.getElementById('cadence-icon-sprite')) return;
        const symbols = Object.entries(PATHS).map(([name, body]) =>
            `<symbol id="i-${name}" viewBox="0 0 24 24">${body}</symbol>`).join('');
        const holder = document.createElement('div');
        holder.innerHTML = `<svg id="cadence-icon-sprite" xmlns="http://www.w3.org/2000/svg" style="position:absolute;width:0;height:0;overflow:hidden" aria-hidden="true">${symbols}</svg>`;
        document.body.prepend(holder.firstChild);
    }

    window.cadenceIcon = function cadenceIcon(name) {
        return `<svg class="icon" aria-hidden="true" focusable="false"><use href="#i-${name}"></use></svg>`;
    };

    if (document.body) injectSprite();
    else document.addEventListener('DOMContentLoaded', injectSprite);
})();

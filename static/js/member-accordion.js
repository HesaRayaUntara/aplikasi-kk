(() => {
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    document.querySelectorAll('.member-accordion').forEach(details => {
        const summary = details.querySelector('.member-summary');
        const panel = details.querySelector('.member-detail-wrap');
        summary.setAttribute('aria-expanded', details.open ? 'true' : 'false');

        summary.addEventListener('click', event => {
            event.preventDefault();
            if (details.dataset.animating === 'true') return;

            const opening = !details.open;
            summary.setAttribute('aria-expanded', opening ? 'true' : 'false');
            details.dataset.animating = 'true';

            if (opening) {
                details.open = true;
                panel.hidden = false;
            }

            const fromHeight = opening ? 0 : panel.scrollHeight;
            const toHeight = opening ? panel.scrollHeight : 0;
            if (typeof panel.animate !== 'function') {
                details.open = opening;
                panel.hidden = !opening;
                details.dataset.animating = 'false';
                return;
            }

            const animation = panel.animate(
                [
                    { height: `${fromHeight}px`, opacity: opening ? 0 : 1 },
                    { height: `${toHeight}px`, opacity: opening ? 1 : 0 }
                ],
                { duration: reducedMotion ? 0 : (opening ? 180 : 160), easing: opening ? 'ease-out' : 'ease-in' }
            );

            animation.onfinish = () => {
                if (opening) {
                    panel.style.height = 'auto';
                    panel.style.opacity = '1';
                } else {
                    details.open = false;
                    panel.hidden = true;
                    panel.style.height = '';
                    panel.style.opacity = '';
                }
                details.dataset.animating = 'false';
            };
        });
    });
})();

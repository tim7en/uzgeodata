/* Shared page chrome: the auto-hiding header bar.
 *
 * A reading page should give the reader its width back. The bar slides away
 * as the reader scrolls into the page and returns on the first upward
 * scroll, on the pointer touching the top edge, or whenever keyboard focus
 * moves into it. Reduced-motion readers get the same behaviour without the
 * animation.
 */

const EDGE_PX = 72; // pointer distance from the top that reveals the bar
const PIN_PX = 120; // never hide above this scroll offset

let styleInjected = false;
function injectStyle() {
  if (styleInjected) return;
  styleInjected = true;
  const style = document.createElement('style');
  style.textContent = `
.uz-autohide{position:fixed;top:0;left:0;right:0;z-index:1200;transition:transform .26s ease}
.uz-autohide.uz-hidden{transform:translateY(-110%)}
body.uz-padded{padding-top:var(--uz-header-h,80px)}
@media (prefers-reduced-motion: reduce){.uz-autohide{transition:none}}
/* Themed backdrops, because a fixed bar scrolls over page content. */
.uz-autohide.site-header{background:#e7ebee;border-bottom:1px solid #d0dadf;box-sizing:border-box}
[data-theme="dark"] .uz-autohide.site-header{background:#060b0e;border-bottom-color:#1d282d}
nav.uz-autohide{background:#0a0f12;border-bottom:1px solid #1d282d;padding:14px 5vw;box-sizing:border-box}
[data-theme="light"] nav.uz-autohide{background:#e7ebee;border-bottom-color:#d0dadf}
.cs-header.uz-autohide{background:var(--c-bg-6,#0d1117)}
.admin-topbar.uz-autohide{background:#fbfcfc}
[data-theme="dark"] .admin-topbar.uz-autohide{background:#0b1013}
`;
  document.head.appendChild(style);
}

export function autoHideHeader(header) {
  if (!header || header.dataset.uzAutohide) return;
  header.dataset.uzAutohide = '1';
  injectStyle();
  header.classList.add('uz-autohide');
  document.body.classList.add('uz-padded');

  const measure = () => {
    document.documentElement.style.setProperty('--uz-header-h', `${header.offsetHeight}px`);
  };
  measure();
  window.addEventListener('resize', measure);

  const show = () => header.classList.remove('uz-hidden');
  let lastY = window.scrollY;
  let queued = false;

  const update = () => {
    queued = false;
    const y = window.scrollY;
    if (y <= PIN_PX || y < lastY) show();
    else header.classList.add('uz-hidden');
    lastY = y;
  };

  window.addEventListener('scroll', () => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(update);
  }, { passive: true });

  document.addEventListener('mousemove', event => {
    if (event.clientY <= EDGE_PX) show();
  }, { passive: true });

  header.addEventListener('focusin', show);
}

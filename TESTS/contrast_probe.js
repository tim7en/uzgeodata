// WCAG contrast of rendered text, used by the study browser suite.
// Kept beside the test so the threshold and the measurement travel together.
() => {
  const lum = ([r, g, b]) => {
    const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  };
  const rgb = s => (s.match(/\d+(\.\d+)?/g) || []).slice(0, 3).map(Number);
  const alpha = s => { const m = s.match(/rgba?\([^)]*,\s*([\d.]+)\s*\)/); return m ? parseFloat(m[1]) : 1; };
  const behind = el => {
    let node = el;
    while (node) {
      const bg = getComputedStyle(node).backgroundColor;
      if (bg && alpha(bg) > 0.6) return rgb(bg);
      node = node.parentElement;
    }
    const root = rgb(getComputedStyle(document.documentElement).backgroundColor);
    return root.length === 3 ? root : [255, 255, 255];
  };
  const out = [];
  const seen = new Set();
  document.querySelectorAll('h1,h2,h3,p,td,th,li,span,a,button,strong,small,summary').forEach(el => {
    const text = (el.innerText || '').trim();
    if (!text || text.length < 3 || el.children.length > 2) return;
    const box = el.getBoundingClientRect();
    if (box.width < 4 || box.height < 4) return;
    const style = getComputedStyle(el);
    if (style.visibility === 'hidden' || style.opacity === '0') return;
    const fg = rgb(style.color);
    const bg = behind(el);
    if (!fg.length || !bg.length) return;
    const a = lum(fg), b = lum(bg);
    const ratio = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
    const size = parseFloat(style.fontSize);
    const bold = parseInt(style.fontWeight, 10) >= 700;
    const large = size >= 24 || (size >= 18.66 && bold);
    const key = el.tagName + '|' + text.slice(0, 28) + '|' + style.color;
    if (seen.has(key)) return;
    seen.add(key);
    out.push({ tag: el.tagName, text: text.slice(0, 40), ratio: +ratio.toFixed(2),
               need: large ? 3 : 4.5, size, color: style.color });
  });
  return out;
}

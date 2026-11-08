// WCAG contrast for the effective MTN theme = LibreChat defaults + mtn/config/librechat.yaml overrides.
// Usage (from repo root): node mtn/scripts/theme-contrast.js . [--md]
const fs = require('fs'), path = require('path');
const root = process.argv[2], md = process.argv.includes('--md');
const parseTs = (f) => Object.fromEntries([...fs.readFileSync(path.join(root, f), 'utf8')
  .matchAll(/'(rgb-[a-z0-9-]+)':\s*'(\d+ \d+ \d+)'/g)].map((m) => [m[1], m[2]]));
const base = { light: parseTs('packages/data-provider/src/themes/default.ts'),
               dark: parseTs('packages/data-provider/src/themes/dark.ts') };
// Overrides: lines under "modes: > light|dark: > colors:" in the YAML (simple indentation parse).
const yaml = fs.readFileSync(path.join(root, 'mtn/config/librechat.yaml'), 'utf8').split('\n');
const over = { light: {}, dark: {} }; let mode = null, inColors = false;
for (const line of yaml) {
  const m = line.match(/^ {6}(light|dark):\s*$/); if (m) { mode = m[1]; inColors = false; continue; }
  if (/^ {8}colors:\s*$/.test(line)) { inColors = !!mode; continue; }
  if (/^ {8}\S/.test(line) || /^ {0,5}\S/.test(line)) inColors = false;
  const t = line.match(/^ {10}(rgb-[a-z0-9-]+):\s*'(\d+ \d+ \d+)'/);
  if (inColors && t) over[mode][t[1]] = t[2];
}
const lum = (rgb) => { const c = rgb.split(' ').map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]; };
const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
const hex = (rgb) => '#' + rgb.split(' ').map((v) => (+v).toString(16).padStart(2, '0')).join('').toUpperCase();
const T = 4.5, U = 3;
const pairs = [
  ...['surface-primary','surface-secondary','surface-chat','surface-sidebar','surface-composer','surface-dialog',
      'surface-user-message','surface-nav-selected','surface-tab-selected'].map((b) => ['text-primary', b, T]),
  ...['surface-primary','surface-chat','surface-sidebar','surface-user-message','surface-nav-selected'].map((b) => ['text-secondary', b, T]),
  ...['surface-primary','surface-chat','surface-sidebar','surface-nav-selected'].map((b) => ['text-tertiary', b, T]),
  ['text-on-status', 'surface-submit', T], ['text-on-status', 'surface-submit-hover', T], ['text-on-status', 'surface-destructive', T],
  ['text-inverted', 'button-primary', T], ['text-inverted', 'button-primary-hover', T], ['text-inverted', 'surface-inverted', T],
  ['avatar-text', 'avatar-fill', T],
  ['link', 'surface-chat', T], ['link', 'surface-primary', T], ['link-hover', 'surface-chat', T], ['link-prose', 'surface-chat', T],
  // non-text UI indicators (WCAG 1.4.11, 3:1)
  ['focus-outline', 'surface-chat', U], ['focus-outline', 'surface-primary', U], ['ring-primary', 'surface-primary', U],
  ['border-field-focus', 'field-fill', U],
  // chat send button = bg-surface-inverted + text-inverted (composerSubmitClasses); text buttons = surface-submit
  ['surface-inverted', 'surface-composer', U], ['text-inverted', 'surface-inverted', U],
  ['surface-submit', 'surface-primary', U], ['surface-submit', 'surface-dialog', U],
];
const rows = [];
for (const mode of ['light', 'dark']) {
  const eff = { ...base[mode], ...over[mode] };
  for (const [fg, bg, min] of pairs) {
    const a = eff['rgb-' + fg], b = eff['rgb-' + bg];
    if (!a || !b) { rows.push({ mode, fg, bg, missing: true }); continue; }
    const r = ratio(a, b), mtn = !!(over[mode]['rgb-' + fg] || over[mode]['rgb-' + bg]);
    rows.push({ mode, fg, bg, fgHex: hex(a), bgHex: hex(b), r, min, pass: r >= min, mtn });
  }
}
if (md) {
  console.log('| Mode | Foreground | Background | Colours | Ratio | Needs | AA |');
  console.log('|---|---|---|---|---|---|---|');
  for (const x of rows) console.log(x.missing ? `| ${x.mode} | \`${x.fg}\` | \`${x.bg}\` | — | — | — | token missing |`
    : `| ${x.mode} | \`${x.fg}\`${x.mtn ? ' *' : ''} | \`${x.bg}\` | ${x.fgHex} / ${x.bgHex} | ${x.r.toFixed(2)}:1 | ${x.min}:1${x.min === U ? ' (UI)' : ''} | ${x.pass ? '✅ Pass' : '❌ Fail'} |`);
} else {
  console.log('overrides:', JSON.stringify({ light: Object.keys(over.light).length, dark: Object.keys(over.dark).length }));
  for (const x of rows) if (x.missing || !x.pass) console.log('FAIL/MISSING', x.mode, x.fg, 'on', x.bg, x.r ? x.r.toFixed(2) : '', x.mtn ? '(MTN-affected)' : '(LibreChat default)');
  console.log('total pairs', rows.length, 'failures', rows.filter((x) => x.missing || !x.pass).length);
}

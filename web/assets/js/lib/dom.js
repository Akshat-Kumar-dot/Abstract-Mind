// Small DOM helpers shared by every page. Anything that came from a file or
// from the server goes through escapeHtml before it touches innerHTML.

export const $ = (id) => document.getElementById(id);
export const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

export function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

export const icon = (name, cls = "ic") => `<svg class="${cls}" aria-hidden="true"><use href="#${name}"/></svg>`;

export function plural(n, one, many) {
  return `${n} ${n === 1 ? one : many || one + "s"}`;
}

export function formatSize(n) {
  if (n < 1024) return n + " B";
  if (n < 1024 * 1024) return (n / 1024).toFixed(0) + " KB";
  return (n / 1024 / 1024).toFixed(1) + " MB";
}

export function ago(ts) {
  const s = Date.now() / 1000 - ts;
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  if (s < 60) return "just now";
  if (s < 3600) return rtf.format(-Math.round(s / 60), "minute");
  if (s < 86400) return rtf.format(-Math.round(s / 3600), "hour");
  if (s < 86400 * 30) return rtf.format(-Math.round(s / 86400), "day");
  return new Date(ts * 1000).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export async function copyText(text, button, fallbackInput) {
  try {
    await navigator.clipboard.writeText(text);
    flash(button, true);
  } catch (_) {
    if (fallbackInput && fallbackInput.select) { fallbackInput.focus(); fallbackInput.select(); }
    flash(button, false);
  }
}

function flash(button, ok) {
  const label = button.querySelector("span");
  if (label) {
    const old = label.dataset.label || label.textContent;
    label.dataset.label = old;
    label.textContent = ok ? "Copied" : "Press Ctrl+C";
    setTimeout(() => { label.textContent = old; }, 1400);
  } else {
    button.title = ok ? "Copied" : "Press Ctrl+C";
    setTimeout(() => { button.title = "Copy"; }, 1400);
  }
  button.classList.add("done");
  setTimeout(() => button.classList.remove("done"), 1400);
}

/** Disable a button while `work` runs, showing `label` meanwhile. */
export async function busy(button, label, work) {
  const old = button.textContent;
  button.disabled = true;
  if (label) button.textContent = label;
  try {
    return await work();
  } finally {
    button.disabled = false;
    button.textContent = old;
  }
}

export function showError(el, message) {
  el.textContent = message;
  el.hidden = !message;
}

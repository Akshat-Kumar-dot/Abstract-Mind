// The library: every saved document, decrypted in the browser, with search,
// sort, shelves (all, starred, receipts) and a running count.

import { $, ago, escapeHtml, icon, plural } from "../lib/dom.js";
import * as library from "../services/library.js";
import { isGuest, session } from "../services/session.js";

const SHELF_TITLE = { all: "My papers", starred: "Starred", receipts: "Receipts" };
const SORTS = {
  new: (a, b) => b.created_at - a.created_at,
  old: (a, b) => a.created_at - b.created_at,
  title: (a, b) => (a.title || a.filename).localeCompare(b.title || b.filename),
  found: (a, b) => b.fields_found / (b.fields_total || 1) - a.fields_found / (a.fields_total || 1),
};

let docs = [];
let shelf = "all";

export function init() {
  $("q").addEventListener("input", render);
  $("sort").addEventListener("change", render);
  $("shelf").addEventListener("click", onAction);
}

export async function show(which) {
  shelf = which;
  document.title = `${SHELF_TITLE[shelf]} · Abstract Mind`;
  $("lib-title").textContent = SHELF_TITLE[shelf];
  document.querySelectorAll("[data-nav]").forEach((a) => {
    if (a.dataset.nav === shelf) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
  $("guest-card").hidden = !isGuest();
  let stats = (session.me && session.me.stats) || { total: 0, this_week: 0, weeks: [] };
  try {
    const data = await library.list();
    docs = data.docs;
    stats = data.stats;
  } catch (_) { /* keep what we had */ }
  renderStats(stats);
  render();
}

function renderStats(s) {
  const papers = docs.filter((d) => d.kind === "paper" && !d.unreadable).length;
  const receipts = docs.filter((d) => d.kind === "upi").length;
  const fields = docs.reduce((n, d) => n + (d.fields_found || 0), 0);
  const pages = docs.reduce((n, d) => n + (d.pages || 0), 0);
  $("tally-line").textContent = !s.total
    ? "Nothing here yet. Upload a paper and it will be kept on this shelf, encrypted so only you can read it."
    : `Everything you've extracted, newest first. ${s.this_week ? `${s.this_week} added this week.` : "Nothing new this week."}`;
  const bits = [];
  if (papers) bits.push(plural(papers, "paper"));
  if (receipts) bits.push(plural(receipts, "receipt"));
  if (fields) bits.push(`${fields.toLocaleString()} fields captured`);
  if (pages) bits.push(plural(pages, "page") + " read");
  $("ledger").textContent = bits.join("  ·  ");
  $("big-n").textContent = s.total;
  $("big-n-label").textContent = s.total === 1 ? "document extracted" : "documents extracted";
  $("side-total").textContent = plural(s.total, "document");
  $("side-week").textContent = s.this_week ? `${s.this_week} this week` : "none this week";
}

function dateGroup(ts) {
  const d = new Date(ts * 1000), now = new Date();
  const day = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((day(now) - day(d)) / 86400000);
  if (diff <= 0) return "Today";
  if (diff === 1) return "Yesterday";
  if (diff < 7) return "This week";
  if (d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth()) return "Earlier this month";
  return d.toLocaleDateString(undefined, { month: "long", year: "numeric" });
}

function render() {
  $("n-all").textContent = docs.length || "";
  $("n-starred").textContent = docs.filter((p) => p.starred).length || "";
  $("n-receipts").textContent = docs.filter((p) => p.kind === "upi").length || "";
  const q = $("q").value.trim().toLowerCase();
  const inShelf = (p) => shelf === "all" || (shelf === "starred" ? p.starred : p.kind === "upi");
  const onShelf = docs.filter(inShelf);
  const rows = onShelf.filter((p) => !q || [p.title, p.byline, p.filename].some((v) => v && v.toLowerCase().includes(q)))
    .sort(SORTS[$("sort").value]);
  $("empty").hidden = onShelf.length > 0;
  $("empty-title").textContent = shelf === "starred" ? "Nothing starred yet" : shelf === "receipts" ? "No receipts yet" : "No papers yet";
  $("empty-text").textContent = shelf === "starred" ? "Star a paper to keep it here." : "Your first extraction will show up here, along with a running count.";
  $("no-match").hidden = !onShelf.length || rows.length > 0;
  const byDate = $("sort").value === "new" || $("sort").value === "old";
  let lastGroup = null, html = "";
  rows.forEach((p) => {
    if (byDate) {
      const g = dateGroup(p.created_at);
      if (g !== lastGroup) { html += `<li class="day">${escapeHtml(g)}</li>`; lastGroup = g; }
    }
    const kind = p.kind === "upi" ? "upi" : "paper";
    const type = p.unreadable ? "LOCKED" : kind === "upi" ? "UPI" : (p.file_type || "file").toUpperCase();
    const id = escapeHtml(p.id);
    html += `
      <li class="entry ${kind}" data-id="${id}">
        <span class="ftype ${kind}">${escapeHtml(type)}</span>
        <div class="entry-main">
          ${p.unreadable ? `<span class="t">Can't be opened with this account's key</span>`
            : `<a class="t" href="#/doc/${id}">${escapeHtml(p.title || p.filename)}</a>`}
          <p class="by">${p.byline ? escapeHtml(p.byline) : `<span class="file">${escapeHtml(p.filename)}</span>`}</p>
        </div>
        <div class="fill" title="${p.fields_found} of ${p.fields_total} fields found">
          <span class="fill-bar"><span data-share="${p.fields_total ? Math.round((p.fields_found / p.fields_total) * 100) : 0}"></span></span>
          <span class="fill-n">${p.fields_found}<small>/${p.fields_total} fields</small></span>
        </div>
        <time datetime="${new Date(p.created_at * 1000).toISOString()}" title="${escapeHtml(new Date(p.created_at * 1000).toLocaleString())}">${escapeHtml(ago(p.created_at))}</time>
        <div class="acts">
          <button type="button" class="icon-btn" data-act="star" aria-pressed="${p.starred}" title="${p.starred ? "Unstar" : "Star"}" aria-label="Star">${icon("i-star")}</button>
          <button type="button" class="icon-btn danger" data-act="delete" title="Delete" aria-label="Delete">${icon("i-trash")}</button>
        </div>
      </li>`;
  });
  $("shelf").innerHTML = html;
  // widths are set through the style object: the CSP forbids inline style attributes
  $("shelf").querySelectorAll("[data-share]").forEach((el) => { el.style.width = `${el.dataset.share}%`; });
}

async function onAction(e) {
  const b = e.target.closest("button[data-act]");
  if (!b) return;
  const p = docs.find((x) => x.id === b.closest(".entry").dataset.id);
  if (!p) return;
  if (b.dataset.act === "star") {
    p.starred = !p.starred;
    render();
    library.star(p.id, p.starred).catch(() => {});
  } else if (confirm(`Delete “${p.title || p.filename}” from your library? This can't be undone.`)) {
    await library.remove(p.id);
    show(shelf);
  }
}

// One saved extraction. It reads like a record card: an overview first, then
// one section per group. Values show as text; the pencil turns a row into an
// input. Edits are encrypted and saved a moment after typing stops.

import { $, copyText, escapeHtml, icon, reduceMotion } from "../lib/dom.js";
import {
  LIST_KEYS, SOURCE_LABEL, STATUS_LABEL, allFields, asPlainText, exportObject, found, fromText, groupFields, hasValue,
  plainValue, toText,
} from "../lib/fields.js";
import * as library from "../services/library.js";

const GROUP_ICON = {
  paper: "i-bookmark", authors: "i-users", publication: "i-book", declarations: "i-seal", stats: "i-hash",
  transaction: "i-swap", parties: "i-users", other: "i-pen",
};
const ORDINAL = ["First author", "Second author", "Third author", "Fourth author", "Fifth author"];
const OVERVIEW_KEYS = {
  paper: ["title", "keywords", "journal", "published", "doi", "pages"],
  upi: ["amount", "status", "datetime", "receiver_name", "app", "utr"],
};
const TAG_KEYS = new Set(["keywords", "grant_ids", "credit_roles", "approval_ids"]);

let current = null;      // { result, saved }
let go = () => {};
let observer = null;
let saveTimer = null;

export function init(navigate) {
  go = navigate;
  $("toc").addEventListener("click", (e) => {
    const a = e.target.closest("a[data-sec]");
    if (!a) return;
    e.preventDefault();
    jump(a.dataset.sec);
  });
  $("star").addEventListener("click", () => {
    if (!current) return;
    current.saved.starred = !current.saved.starred;
    $("star").setAttribute("aria-pressed", current.saved.starred);
    library.star(current.saved.id, current.saved.starred).catch(() => {});
  });
  $("remove").addEventListener("click", async () => {
    if (!current || !confirm(`Delete “${titleOf()}” from your library? This can't be undone.`)) return;
    clearTimeout(saveTimer);
    saveTimer = null;
    await library.remove(current.saved.id);
    go("#/");
  });
  $("copy-all").addEventListener("click", (e) => copyText(asPlainText(current.result), e.currentTarget));
  $("download").addEventListener("click", download);
  window.addEventListener("beforeunload", (e) => {
    if (saveTimer) { flush(); e.preventDefault(); }
  });
}

export async function show(id) {
  current = null;
  $("groups").innerHTML = "";
  $("doc-title").textContent = "Opening…";
  ["summary", "doc-kind"].forEach((x) => { $(x).textContent = ""; });
  ["tally", "warnings", "toc", "save-state"].forEach((x) => { $(x).innerHTML = ""; });
  try {
    current = await library.open(id);
  } catch (err) {
    $("doc-title").textContent = err.message;
    return;
  }
  render();
}

const titleOf = () => {
  const t = groupFields(current.result).find((f) => f.key === "title" && hasValue(f));
  return (t && t.value) || current.result.filename;
};

function render() {
  const d = current.result, saved = current.saved;
  $("doc-title").textContent = titleOf();
  document.title = `${titleOf()} · Abstract Mind`;
  $("doc-kind").textContent = d.kind === "paper" ? "Research paper" : "UPI receipt";
  $("summary").innerHTML = [
    `<span class="pill">${icon(d.kind === "upi" ? "i-receipt" : "i-paper")}${escapeHtml((d.file_type || "file").toUpperCase())}</span>`,
    `<span class="pill ok">${icon("i-lock")}Encrypted</span>`,
    `<span class="when">${icon("i-clock")}Extracted on ${escapeHtml(new Date(saved.created_at * 1000).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }))}</span>`,
    `<span class="file">${escapeHtml(d.filename)}</span>`,
  ].join("");
  $("star").setAttribute("aria-pressed", saved.starred);

  const counts = { verified: 0, check: 0, needs_review: 0, missing: 0 };
  allFields(d).forEach((f) => { counts[f.status] = (counts[f.status] || 0) + 1; });
  $("tally").innerHTML = ["verified", "check", "needs_review"].filter((k) => counts[k]).map((k) =>
    `<span class="tally-item"><span class="dot ${k}"></span>${counts[k]} ${STATUS_LABEL[k].toLowerCase()}</span>`).join("") +
    (counts.needs_review || counts.check ? `<span class="tally-hint">Rows marked with a dot are worth a second look.</span>` : "");

  const warns = (d.warnings || []).map((w) => `<li>${icon("i-alert")}<span>${escapeHtml(w)}</span></li>`);
  (d.notes || []).forEach((n) => warns.push(`<li class="info">${icon("i-info")}<span>${escapeHtml(n)}</span></li>`));
  if (d.llm && d.llm.reason) warns.push(`<li class="info">${icon("i-info")}<span>${escapeHtml(d.llm.reason)}</span></li>`);
  $("warnings").innerHTML = warns.join("");

  const byKey = {};
  groupFields(d).forEach((f) => { if (!(f.key in byKey)) byKey[f.key] = f; });
  const used = new Set();
  const sections = [];
  const ov = [];
  (OVERVIEW_KEYS[d.kind] || []).forEach((k) => {
    const f = byKey[k];
    if (!f) return;
    used.add(k);
    ov.push(f);
    if (k === "title" && d.kind === "paper") ov.push({ derived: "authors" });
  });
  sections.push({ id: "overview", label: "Overview", icon: "i-bookmark", el: sectionEl("overview", "Basic information", ov, true) });
  if (d.kind === "paper") {
    const abs = byKey.abstract;
    if (abs) { used.add("abstract"); sections.push({ id: "abstract", label: "Abstract", icon: "i-paper", el: proseEl("abstract", "Abstract", abs) }); }
    sections.push({ id: "authors", label: "Authors", icon: "i-users", n: d.authors.length, el: authorsEl(d.authors) });
  }
  d.groups.forEach((g) => {
    const rest = g.fields.filter((f) => !used.has(f.key));
    if (!rest.length) return;
    const id = g.id === "paper" ? "details" : g.id;
    const label = g.id === "paper" ? "Other details" : g.id === "publication" ? "Publication info" : g.title;
    const el = g.id === "stats" ? countsEl(id, label, rest) : sectionEl(id, label, rest);
    sections.push({ id, label, icon: GROUP_ICON[g.id] || "i-bookmark", n: rest.filter(found).length, el });
  });
  sections.push({ id: "raw", label: "Raw output", icon: "i-code", el: rawEl() });

  $("groups").innerHTML = "";
  sections.forEach((s) => $("groups").appendChild(s.el));
  $("toc").innerHTML = sections.map((s) =>
    `<li><a href="#sec-${s.id}" data-sec="${s.id}">${icon(s.icon)}${escapeHtml(s.label)}${s.n !== undefined ? `<span class="n">${s.n}</span>` : ""}</a></li>`).join("");
  watchSections();
}

// ---------------------------------------------------------------- sections

function shell(id, title, extra = "") {
  const sec = document.createElement("section");
  sec.className = "sec";
  sec.id = `sec-${id}`;
  sec.innerHTML = `<header class="sec-head"><h2>${escapeHtml(title)}</h2>${extra}</header>`;
  return sec;
}

function sectionEl(id, title, fields, boxed = false) {
  const sec = shell(id, title);
  if (boxed) sec.classList.add("boxed");
  sec.appendChild(rowsEl(fields));
  return sec;
}

// label/value rows, plus a "not found" line for the empty ones
function rowsEl(fields) {
  const wrap = document.createElement("div");
  const dl = document.createElement("dl");
  dl.className = "rows";
  const missing = [];
  fields.forEach((f) => {
    if (f.derived === "authors") { dl.appendChild(authorsRow()); return; }
    if (found(f)) dl.appendChild(rowEl(f)); else missing.push(f);
  });
  wrap.appendChild(dl);
  if (missing.length) {
    const p = document.createElement("p");
    p.className = "absent";
    p.innerHTML = "<span>Not found in the file:</span> ";
    missing.forEach((f, i) => {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = f.label;
      b.title = "Add it yourself";
      b.addEventListener("click", () => {
        const row = rowEl(f);
        dl.appendChild(row);
        b.remove();
        if (!p.querySelector("button")) p.remove();
        startEdit(row, f);
      });
      p.appendChild(b);
      if (i < missing.length - 1) p.appendChild(document.createTextNode(" "));
    });
    wrap.appendChild(p);
  }
  return wrap;
}

function authorsRow() {
  const row = document.createElement("div");
  row.className = "row";
  const names = authorNames();
  row.innerHTML = `<dt>Authors</dt><dd><div class="val">${names.length ? escapeHtml(names.join(", ")) : '<span class="muted">None found</span>'}</div></dd>
    <div class="acts">
      <button type="button" class="act" data-a="copy" title="Copy all names" aria-label="Copy all author names">${icon("i-copy")}</button>
      <a class="act" href="#sec-authors" data-jump="authors" title="See each author">${icon("i-users")}</a>
    </div>`;
  row.querySelector('[data-a="copy"]').addEventListener("click", (e) => copyText(authorNames().join(", "), e.currentTarget));
  row.querySelector("[data-jump]").addEventListener("click", (e) => { e.preventDefault(); jump("authors"); });
  return row;
}

function rowEl(f) {
  const row = document.createElement("div");
  row.className = `row s-${f.status}`;
  const tip = f.status === "missing" ? "Added by you"
    : `${STATUS_LABEL[f.status]} · ${SOURCE_LABEL[f.source] || f.source}${f.confidence ? ` · ${Math.round(f.confidence * 100)}%` : ""}`;
  const flag = f.status === "check" || f.status === "needs_review" ? `<span class="dot ${f.status}" title="${escapeHtml(tip)}"></span>` : "";
  row.innerHTML = `<dt>${escapeHtml(f.label)}${flag}</dt><dd><div class="val"></div></dd>
    <div class="acts">
      <button type="button" class="act" data-a="copy" title="Copy" aria-label="Copy ${escapeHtml(f.label)}">${icon("i-copy")}</button>
      <button type="button" class="act" data-a="edit" title="Edit" aria-label="Edit ${escapeHtml(f.label)}">${icon("i-pen")}</button>
    </div>`;
  const dd = row.querySelector("dd");
  paintValue(row.querySelector(".val"), f);
  if (f.note) dd.insertAdjacentHTML("beforeend", `<p class="note">${escapeHtml(f.note)}</p>`);
  if (f.evidence && f.evidence.text) {
    dd.insertAdjacentHTML("beforeend", `<details class="ev"><summary>Source${f.evidence.page ? `, page ${escapeHtml(f.evidence.page)}` : ""}</summary><p></p></details>`);
    dd.querySelector(".ev p").textContent = `“${f.evidence.text}”`;
  }
  row.title = tip;
  row.querySelector('[data-a="copy"]').addEventListener("click", (e) => copyText(plainValue(f), e.currentTarget));
  row.querySelector('[data-a="edit"]').addEventListener("click", () => startEdit(row, f));
  row.querySelector(".val").addEventListener("dblclick", () => startEdit(row, f));
  return row;
}

const safeUrl = (u) => /^https?:\/\//i.test(u);

function paintValue(el, f) {
  const v = f.value;
  if (typeof v === "boolean") { el.innerHTML = v ? `<span class="yes">${icon("i-check")}Yes</span>` : "No"; return; }
  if (!hasValue(f)) { el.innerHTML = '<span class="muted">—</span>'; return; }
  const list = Array.isArray(v) ? v : [v];
  if (TAG_KEYS.has(f.key)) { el.innerHTML = list.map((x) => `<span class="tag">${escapeHtml(x)}</span>`).join(""); return; }
  if (f.key === "doi") { el.innerHTML = `<a href="https://doi.org/${encodeURI(v)}" target="_blank" rel="noopener noreferrer">${escapeHtml(v)}${icon("i-external")}</a>`; return; }
  if (f.key === "email") { el.innerHTML = `<a href="mailto:${encodeURIComponent(v).replace(/%40/g, "@")}">${escapeHtml(v)}</a>`; return; }
  if (f.key === "orcid") { el.innerHTML = `<a href="https://orcid.org/${encodeURIComponent(v)}" target="_blank" rel="noopener noreferrer">${escapeHtml(v)}${icon("i-external")}</a>`; return; }
  if (f.key === "data_urls") {
    el.innerHTML = list.map((u) => safeUrl(u) ? `<a href="${escapeHtml(u)}" target="_blank" rel="noopener noreferrer">${escapeHtml(u)}</a>` : escapeHtml(u)).join("<br>");
    return;
  }
  if (f.key === "amount") { el.innerHTML = `<span class="big">₹${escapeHtml(v)}</span>`; return; }
  el.innerHTML = list.map((x) => escapeHtml(x)).join("<br>");
  el.classList.toggle("prose", !!f.long);
}

function startEdit(row, f) {
  if (typeof f.value === "boolean") {
    f.value = !f.value;
    markEdited(f);
    paintValue(row.querySelector(".val"), f);
    queueSave();
    return;
  }
  if (row.classList.contains("editing")) return;
  row.classList.add("editing");
  const val = row.querySelector(".val");
  const long = f.long || toText(f).length > 70 || f.key === "affiliations";
  const input = document.createElement(long ? "textarea" : "input");
  if (!long) input.type = "text";
  input.className = "editor";
  input.value = toText(f);
  input.setAttribute("aria-label", f.label);
  if (long) input.rows = Math.min(12, Math.max(3, Math.ceil(input.value.length / 75)));
  const hint = document.createElement("p");
  hint.className = "edit-hint";
  hint.textContent = (LIST_KEYS.has(f.key) || Array.isArray(f.value) ? `Separate items with “${f.key === "affiliations" ? "|" : ";"}”. ` : "") +
    (long ? "Ctrl+Enter to save, Esc to cancel." : "Enter to save, Esc to cancel.");
  val.replaceWith(input);
  input.after(hint);
  input.focus();
  let done = false;
  const finish = (keep) => {
    if (done) return;
    done = true;
    if (keep && input.value !== toText(f)) {
      f.value = fromText(f, input.value);
      markEdited(f);
      queueSave();
      if (f.key === "title") $("doc-title").textContent = titleOf();
    }
    row.replaceWith(rowEl(f));
  };
  input.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { e.preventDefault(); finish(false); }
    if (e.key === "Enter" && (!long || e.ctrlKey || e.metaKey)) { e.preventDefault(); finish(true); }
  });
  input.addEventListener("blur", () => finish(true));
}

function markEdited(f) {
  if (hasValue(f) && f.status === "missing") f.status = "check";
  f.source = "you";
  f.note = null;
}

function proseEl(id, title, f) {
  const sec = shell(id, title, `<div class="sec-acts">
    <button type="button" class="act" data-a="copy" title="Copy">${icon("i-copy")}</button>
    <button type="button" class="act" data-a="edit" title="Edit">${icon("i-pen")}</button></div>`);
  sec.classList.add("boxed");
  const row = rowEl(f);
  row.classList.add("lone");
  sec.appendChild(row);
  sec.querySelector('.sec-acts [data-a="copy"]').addEventListener("click", (e) => copyText(toText(f), e.currentTarget));
  sec.querySelector('.sec-acts [data-a="edit"]').addEventListener("click", () => startEdit(sec.querySelector(".row"), f));
  return sec;
}

// read from the fields, so copies include the user's edits
function fieldValue(a, key) {
  const f = a.fields.find((x) => x.key === key);
  return f && hasValue(f) ? plainValue(f) : "";
}
function authorNames() {
  return (current.result.authors || []).map((a) => fieldValue(a, "name") || a.name).filter(Boolean);
}
function authorBlock(a, i) {
  const lines = [`${i + 1}. ${fieldValue(a, "name") || a.name}${a.corresponding ? " (corresponding author)" : ""}`];
  const aff = a.fields.find((f) => f.key === "affiliations");
  if (aff && hasValue(aff)) (Array.isArray(aff.value) ? aff.value : [aff.value]).forEach((x) => lines.push(`   ${x}`));
  if (fieldValue(a, "email")) lines.push(`   ${fieldValue(a, "email")}`);
  if (fieldValue(a, "orcid")) lines.push(`   ORCID ${fieldValue(a, "orcid")}`);
  return lines.join("\n");
}

function authorsEl(authors) {
  const n = authors.length;
  const sec = shell("authors", "Authors", `<span class="sec-meta">${n ? `${n} in the order printed` : "none found"}</span>` +
    (n ? `<div class="sec-acts sec-acts-tight"><button type="button" class="ghost sm" data-a="copy-all">${icon("i-copy")}<span>Copy all authors</span></button></div>` : ""));
  if (n) sec.querySelector('[data-a="copy-all"]').addEventListener("click", (e) =>
    copyText(authors.map((a, i) => authorBlock(a, i)).join("\n\n"), e.currentTarget));
  const list = document.createElement("ol");
  list.className = "people";
  authors.forEach((a, i) => {
    const li = document.createElement("li");
    li.className = "person";
    const aff = a.fields.find((f) => f.key === "affiliations");
    const email = a.fields.find((f) => f.key === "email");
    const sub = [aff && hasValue(aff) ? toText(aff).split(" | ")[0] : "", email && hasValue(email) ? email.value : ""]
      .filter(Boolean).map(escapeHtml).join(" · ") || "No affiliation or email found";
    li.innerHTML = `
      <div class="person-row">
      <button type="button" class="person-head" aria-expanded="false">
        <span class="pos">${i + 1}</span>
        <span class="who-txt"><strong>${escapeHtml(a.name)}</strong><span class="sub">${sub}</span></span>
        ${a.corresponding ? '<span class="badge">Corresponding</span>' : ""}
        <span class="role">${ORDINAL[i] || `Author ${i + 1}`}</span>
        <svg class="ic chev" aria-hidden="true"><use href="#i-chevron"/></svg>
      </button>
      <div class="person-acts">
        <button type="button" class="act" data-a="name" title="Copy name" aria-label="Copy ${escapeHtml(a.name)}'s name">${icon("i-copy")}</button>
        <button type="button" class="act" data-a="block" title="Copy name, affiliation, email and ORCID" aria-label="Copy all details for ${escapeHtml(a.name)}">${icon("i-clipboard")}</button>
      </div>
      </div>`;
    li.querySelector('[data-a="name"]').addEventListener("click", (e) => copyText(fieldValue(a, "name") || a.name, e.currentTarget));
    li.querySelector('[data-a="block"]').addEventListener("click", (e) => copyText(authorBlock(a, i), e.currentTarget));
    const body = document.createElement("div");
    body.className = "person-body";
    body.hidden = true;
    body.appendChild(rowsEl(a.fields));
    li.appendChild(body);
    const head = li.querySelector(".person-head");
    head.addEventListener("click", () => {
      body.hidden = !body.hidden;
      head.setAttribute("aria-expanded", !body.hidden);
    });
    list.appendChild(li);
  });
  if (n === 1) { list.querySelector(".person-body").hidden = false; list.querySelector(".person-head").setAttribute("aria-expanded", "true"); }
  sec.appendChild(list);
  return sec;
}

function countsEl(id, title, fields) {
  const sec = shell(id, title);
  const figs = document.createElement("dl");
  figs.className = "counts";
  fields.forEach((f) => {
    const div = document.createElement("div");
    div.title = f.note || "";
    div.innerHTML = `<dt>${escapeHtml(f.label)}</dt><dd>${hasValue(f) ? escapeHtml(f.value) : '<span class="muted">—</span>'}</dd>`;
    figs.appendChild(div);
  });
  sec.appendChild(figs);
  return sec;
}

function rawEl() {
  const sec = shell("raw", "Raw output", `<div class="sec-acts"><button type="button" class="act" data-a="copy" title="Copy JSON">${icon("i-copy")}</button></div>`);
  sec.classList.add("boxed");
  const pre = document.createElement("pre");
  pre.className = "raw";
  const text = () => JSON.stringify(exportObject(current.result), null, 2);
  pre.textContent = text();
  sec.querySelector('[data-a="copy"]').addEventListener("click", (e) => copyText(text(), e.currentTarget));
  sec.addEventListener("refresh", () => { pre.textContent = text(); });
  sec.appendChild(pre);
  return sec;
}

function jump(id) {
  $(`sec-${id}`).scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
}

function watchSections() {
  if (observer) observer.disconnect();
  if (!("IntersectionObserver" in window)) return;
  observer = new IntersectionObserver((entries) => {
    entries.forEach((en) => {
      if (!en.isIntersecting) return;
      const id = en.target.id.replace(/^sec-/, "");
      $("toc").querySelectorAll("a").forEach((a) => a.classList.toggle("on", a.dataset.sec === id));
    });
  }, { rootMargin: "-15% 0px -75% 0px" });
  $("groups").querySelectorAll(".sec").forEach((s) => observer.observe(s));
}

// ---------------------------------------------------------------- saving

function queueSave() {
  $("save-state").textContent = "Unsaved changes";
  const raw = $("sec-raw");
  if (raw) raw.dispatchEvent(new Event("refresh"));
  clearTimeout(saveTimer);
  saveTimer = setTimeout(flush, 900);
}

/** Encrypt and save pending edits now. Safe to call any time. */
export function flush() {
  if (!saveTimer || !current) return Promise.resolve();
  clearTimeout(saveTimer);
  saveTimer = null;
  $("save-state").textContent = "Saving…";
  return library.update(current.saved.id, current.result)
    .then(() => { $("save-state").innerHTML = `${icon("i-lock")}Saved, encrypted`; })
    .catch(() => { $("save-state").textContent = "Couldn't save. Check your connection."; });
}

function download() {
  const blob = new Blob([JSON.stringify(exportObject(current.result), null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = (current.result.filename || "abstract-mind").replace(/\.[^.]+$/, "") + ".json";
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 0);
}

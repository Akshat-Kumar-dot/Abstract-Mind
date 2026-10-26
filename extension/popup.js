// The popup: pick the details (upload a file to Abstract Mind, or open one from
// your library), then fill the page you are on. The chosen details are kept in
// the extension's session storage, because the popup closes whenever you click
// the page; Chrome clears that storage when the browser closes.
import { summarize } from "./lib/fields.js";
import * as keystore from "./lib/keystore.js";
import * as vault from "./lib/vault.js";

(() => {
  "use strict";

  const DEFAULT_SERVER = "http://localhost:8765";
  const BUILT_IN = /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$|^https:\/\/[\w-]+\.onrender\.com$/;
  const $ = (id) => document.getElementById(id);
  const inTab = location.hash === "#tab";   // opened as a page, for when the file picker closes the popup

  let server = DEFAULT_SERVER;
  let current = null;   // the details in use, from AbstractMindData.toFillData

  // ------------------------------------------------------------ server
  async function api(path, { json, headers = {}, ...init } = {}) {
    if (json !== undefined) {
      headers = { ...headers, "Content-Type": "application/json" };
      init.body = JSON.stringify(json);
    }
    let r;
    try {
      r = await fetch(server + path, { credentials: "include", ...init, headers });
    } catch (_) {
      throw new Error(`Can't reach Abstract Mind at ${server}. Is it running?`);
    }
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      const err = new Error(data.detail || `Abstract Mind answered ${r.status}.`);
      err.status = r.status;
      throw err;
    }
    return data;
  }

  async function ping() {
    const dot = $("server-state");
    try {
      await api("/api/v1/health");
      dot.className = "dot on";
      dot.title = `Connected to ${server}`;
    } catch (_) {
      dot.className = "dot off";
      dot.title = `Can't reach ${server}`;
    }
  }

  // ------------------------------------------------------------ state
  function setStatus(text, isError) {
    $("status").textContent = text || "";
    $("status").classList.toggle("error", !!isError);
  }

  async function useResult(result, source) {
    current = { ...AbstractMindData.toFillData(result), source };
    await chrome.storage.session.set({ current });
    $("report").hidden = true;
    render();
  }

  function render() {
    document.body.classList.toggle("in-tab", inTab);
    $("loaded").hidden = !current;
    $("choose").hidden = !!current;
    $("fill-section").hidden = !current || inTab;
    $("tab-done").hidden = !(current && inTab);
    $("tab-hint").hidden = inTab;
    $("all").hidden = !current;
    if (!current) return;
    const isPaper = current.kind === "paper";
    $("loaded-kind").textContent = isPaper ? "Research paper" : "UPI receipt";
    $("loaded-title").textContent = current.title;
    const bits = [];
    if (isPaper) bits.push(`${current.authors.length} author${current.authors.length === 1 ? "" : "s"}`);
    bits.push(`${Object.keys(current.fields).length + current.authors.reduce((n, a) => n + Object.keys(a).length, 0)} details`);
    bits.push(current.source === "library" ? "from your library" : current.filename || "uploaded");
    $("loaded-meta").textContent = bits.join(" · ");
    renderAll();
  }

  // Every detail with a Copy button, for fields the page could not match.
  function renderAll() {
    const box = $("all-list");
    box.innerHTML = "";
    const add = (title, entries) => {
      const list = Object.values(entries).filter((e) => e.label);
      if (!list.length) return;
      const h = document.createElement("p");
      h.className = "all-h";
      h.textContent = title;
      box.appendChild(h);
      list.forEach((e) => {
        const text = Array.isArray(e.value) ? e.value.join("; ") : typeof e.value === "boolean" ? (e.value ? "Yes" : "No") : String(e.value);
        const row = document.createElement("div");
        row.className = "all-row";
        const span = document.createElement("span");
        span.innerHTML = `<small></small>`;
        span.querySelector("small").textContent = e.label;
        span.appendChild(document.createTextNode(text));
        span.title = text;
        const btn = document.createElement("button");
        btn.type = "button";
        btn.textContent = "Copy";
        btn.addEventListener("click", () => copy(text, btn));
        row.append(span, btn);
        box.appendChild(row);
      });
    };
    add(current.kind === "paper" ? "Paper" : "Payment", current.fields);
    current.authors.forEach((a, i) => add(`Author ${i + 1}`, a));
  }

  async function copy(text, btn) {
    try {
      await navigator.clipboard.writeText(text);
      btn.textContent = "Copied";
    } catch (_) {
      btn.textContent = "Can't copy";
    }
    setTimeout(() => (btn.textContent = "Copy"), 1200);
  }

  // ------------------------------------------------------------ choosing details
  function showTab(which) {
    const lib = which === "library";
    $("tab-upload").setAttribute("aria-selected", String(!lib));
    $("tab-library").setAttribute("aria-selected", String(lib));
    $("pane-upload").hidden = lib;
    $("pane-library").hidden = !lib;
    if (lib) loadLibrary();
  }
  $("tab-upload").addEventListener("click", () => showTab("upload"));
  $("tab-library").addEventListener("click", () => showTab("library"));

  $("file").addEventListener("change", () => {
    const f = $("file").files[0];
    $("file-label").textContent = f ? f.name : "Choose a paper (PDF, Word, LaTeX) or a UPI receipt";
    $("extract").disabled = !f;
  });

  $("extract").addEventListener("click", async () => {
    const f = $("file").files[0];
    if (!f) return;
    $("extract").disabled = true;
    setStatus(`Reading ${f.name}…`);
    try {
      // The server reads the raw file in memory; nothing is stored there.
      const result = await api(`/api/v1/extract?${new URLSearchParams({ kind: $("kind").value })}`, {
        method: "POST", body: f,
        headers: { "Content-Type": "application/octet-stream", "X-File-Name": encodeURIComponent(f.name) },
      });
      await useResult(result, "upload");
      let saved = false;
      try {
        const k = await libraryKey();
        if (k) {
          await api("/api/v1/documents", { method: "POST", json: await seal(k, result) });
          saved = true;
        }
      } catch (_) { /* reading worked; saving is a bonus */ }
      setStatus(saved ? "Read and saved to your library." : "Read. Unlock Your library to keep a copy there too.");
    } catch (e) {
      setStatus(e.message, true);
    } finally {
      $("extract").disabled = false;
    }
  });

  // ------------------------------------------------------------ library
  // Saved papers are encrypted with the account's data key. The site keeps
  // that key in its own storage, which the extension can't read, so the
  // extension unlocks it once with the password (worked out here; the password
  // is never sent) and keeps it like the site does: a non-extractable key in
  // the extension's IndexedDB, tagged with the server and account.
  let account = null;   // /api/v1/auth/me
  let dataKey = null;

  const owner = () => `${server} ${account.user.email}`;

  async function libraryKey() {
    if (dataKey) return dataKey;
    if (!account) {
      try { account = await api("/api/v1/auth/me"); } catch (_) { return null; }
    }
    if (account.user.guest || !account.key) return null;
    dataKey = await keystore.load(owner());
    return dataKey;
  }

  async function seal(k, result) {
    return { meta: await vault.sealJSON(k, summarize(result), "meta"), body: await vault.sealJSON(k, result, "body") };
  }

  async function forgetKey() {
    dataKey = null;
    await keystore.clear();
  }

  function showUnlock(message) {
    $("unlock").hidden = false;
    $("unlock-email").value = account.user.email || "";
    $("unlock-note").textContent = message ||
      `Enter the password for ${account.user.email} to open your library here. It's checked inside the extension and never sent.`;
    $("library-note").textContent = "";
    setTimeout(() => $("unlock-password").focus(), 0);
  }

  async function loadLibrary() {
    const list = $("library");
    const note = $("library-note");
    list.innerHTML = "";
    $("unlock").hidden = true;
    $("lock").hidden = true;
    note.textContent = "Loading your library…";
    try {
      account = await api("/api/v1/auth/me");
    } catch (e) {
      account = null;
      await forgetKey();
      if (e.status === 401) {
        note.innerHTML = 'Sign in to Abstract Mind in this browser to use your library. <a href="#" id="open-site">Open Abstract Mind</a>';
        $("open-site").addEventListener("click", (ev) => {
          ev.preventDefault();
          chrome.tabs.create({ url: server });
        });
      } else {
        note.textContent = e.message;
      }
      return;
    }
    if (account.user.guest) {
      note.textContent = "You're signed in to the site as a guest. A guest library's key never leaves the site's tab, so it can't be opened here. Continue with Google on the site to keep your papers, then unlock them here.";
      return;
    }
    if (account.user.needs_password || !account.key) {
      note.textContent = "Finish setting up your account on the site (choose a password), then come back here.";
      return;
    }
    const k = await libraryKey();
    if (!k) return showUnlock();

    let docs;
    try {
      docs = (await api("/api/v1/documents")).documents || [];
    } catch (e) {
      note.textContent = e.message;
      return;
    }
    const rows = await Promise.all(docs.map(async (d) => {
      try { return { id: d.id, ...(await vault.openJSON(k, d.meta, "meta")) }; } catch (_) { return null; }
    }));
    if (docs.length && rows.every((r) => r === null)) {
      // The key no longer opens anything: the password was changed on the site.
      await forgetKey();
      return showUnlock("Your password was changed on the site. Enter the new one to open your library here.");
    }
    $("lock").hidden = false;
    const readable = rows.filter(Boolean);
    note.textContent = readable.length ? "Your edits on the site are included." : "Your library is empty. Upload a file on the site or here.";
    readable.slice(0, 40).forEach((p) => {
      const li = document.createElement("li");
      const b = document.createElement("button");
      b.type = "button";
      b.innerHTML = `<span class="t"></span><span class="b"></span>`;
      b.querySelector(".t").textContent = p.title || p.filename;
      b.querySelector(".b").textContent = [p.kind === "upi" ? "UPI receipt" : "Paper", p.byline].filter(Boolean).join(" · ");
      b.addEventListener("click", async () => {
        setStatus("Opening…");
        try {
          const d = await api(`/api/v1/documents/${encodeURIComponent(p.id)}`);
          await useResult(await vault.openJSON(k, d.body, "body"), "library");
          setStatus("");
        } catch (e) {
          setStatus(e.message || "This document can't be opened with your key.", true);
        }
      });
      li.appendChild(b);
      list.appendChild(li);
    });
  }

  $("unlock").addEventListener("submit", async (e) => {
    e.preventDefault();
    const password = $("unlock-password").value;
    if (!password || !account) return;
    $("unlock-go").disabled = true;
    setStatus("Unlocking…");
    try {
      const { dataKey: k } = await vault.unlock(password, account.key);
      if (!k) throw new Error("no key");
      dataKey = k;
      await keystore.save(owner(), k);
      $("unlock-password").value = "";
      setStatus("");
      await loadLibrary();
    } catch (_) {
      setStatus("That password doesn't open your library.", true);
    } finally {
      $("unlock-go").disabled = false;
    }
  });

  $("lock").addEventListener("click", async () => {
    await forgetKey();
    setStatus("Locked. The extension will ask for your password next time.");
    loadLibrary();
  });

  $("change").addEventListener("click", async () => {
    current = null;
    await chrome.storage.session.remove("current");
    setStatus("");
    $("report").hidden = true;
    render();
  });

  $("open-tab").addEventListener("click", (e) => {
    e.preventDefault();
    chrome.tabs.create({ url: chrome.runtime.getURL("popup.html#tab") });
  });

  // ------------------------------------------------------------ filling
  async function activeTab() {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    return tab;
  }

  $("fill").addEventListener("click", async () => {
    const tab = await activeTab();
    if (!tab || /^(chrome|edge|about|chrome-extension):/.test(tab.url || "")) {
      setStatus("Open the form you want to fill first. Chrome's own pages can't be filled.", true);
      return;
    }
    setStatus("Filling…");
    try {
      await chrome.scripting.executeScript({ target: { tabId: tab.id, allFrames: true }, files: ["fill.js"] });
      const runs = await chrome.scripting.executeScript({
        target: { tabId: tab.id, allFrames: true },
        func: (data, opts) => (window.__abstractMind ? window.__abstractMind.fill(data, opts) : null),
        args: [current, { overwrite: $("overwrite").checked }],
      });
      showReport(runs.map((r) => r.result).filter(Boolean));
      setStatus("");
    } catch (e) {
      setStatus(`Chrome didn't allow filling this page: ${e.message}`, true);
    }
  });

  $("clear").addEventListener("click", async () => {
    const tab = await activeTab();
    if (!tab) return;
    try {
      await chrome.scripting.executeScript({
        target: { tabId: tab.id, allFrames: true },
        func: () => (window.__abstractMind ? window.__abstractMind.clear() : null),
      });
    } catch (_) { /* nothing was filled there */ }
  });

  function showReport(reports) {
    const box = $("report");
    box.hidden = false;
    const filled = reports.flatMap((r) => r.filled);
    const warnings = [...new Set(reports.flatMap((r) => r.warnings))];
    const unmatched = [...new Set(reports.flatMap((r) => r.unmatched))];
    const kept = reports.reduce((n, r) => n + r.kept, 0);
    const toCheck = filled.filter((f) => f.status !== "verified").length;
    const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

    let html = `<h3>${filled.length ? `Filled ${filled.length} field${filled.length === 1 ? "" : "s"}` : "Nothing filled"}</h3>`;
    const parts = [];
    if (toCheck) parts.push(`${toCheck} outlined in amber need a look`);
    if (kept) parts.push(`${kept} already had text and were kept`);
    if (parts.length) html += `<p class="fine" style="margin:0">${esc(parts.join("; "))}.</p>`;
    if (!filled.length && !kept) html += `<p class="fine" style="margin:0">No fields on this page matched the details. Use "All details" below to copy them by hand.</p>`;
    if (warnings.length) html += `<ul>${warnings.map((w) => `<li class="warn">${esc(w)}</li>`).join("")}</ul>`;
    if (filled.length) {
      html += "<ul>" + filled.map((f) => {
        const who = f.author !== null && f.author !== undefined ? `Author ${f.author + 1} · ` : "";
        return `<li class="${f.status === "verified" ? "" : "check"}"><span><span class="lbl">${esc(who + f.label)}</span><span class="val">${esc(f.value)}</span></span></li>`;
      }).join("") + "</ul>";
    }
    if (unmatched.length) {
      html += `<p class="sub-h">Left for you</p><ul>${unmatched.map((u) => `<li class="check"><span class="lbl">${esc(u)}</span></li>`).join("")}</ul>`;
    }
    box.innerHTML = html;
  }

  // ------------------------------------------------------------ settings
  $("save-server").addEventListener("click", async () => {
    let value = $("server").value.trim().replace(/\/+$/, "") || DEFAULT_SERVER;
    if (!/^https?:\/\//.test(value)) value = "https://" + value;
    let origin;
    try {
      origin = new URL(value).origin;
    } catch (_) {
      setStatus("That doesn't look like a web address.", true);
      return;
    }
    if (!BUILT_IN.test(origin)) {
      // Any other address needs your permission once, asked by Chrome.
      const ok = await chrome.permissions.request({ origins: [origin + "/*"] });
      if (!ok) {
        setStatus("Chrome needs your permission to talk to that address.", true);
        return;
      }
    }
    server = origin;
    account = null;
    dataKey = null;
    $("server").value = server;
    await chrome.storage.local.set({ server });
    setStatus(`Using ${server}.`);
    ping();
  });

  // ------------------------------------------------------------ start
  (async () => {
    const saved = await chrome.storage.local.get(["server"]);
    await chrome.storage.local.remove("current");     // older versions kept it here, on disk
    server = saved.server || DEFAULT_SERVER;
    $("server").value = server;
    current = (await chrome.storage.session.get("current")).current || null;
    render();
    ping();
  })();
})();

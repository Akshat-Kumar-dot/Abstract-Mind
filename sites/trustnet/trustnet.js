// TrustNet'26 registration: drop in the paper and the payment receipt, and the
// form fills itself. Files go to the Abstract Mind reader (POST /api/v1/extract),
// which reads them in memory and stores nothing; this page keeps nothing either
// (no cookies, no browser storage). Every filled answer stays editable.
(() => {
  "use strict";

  const API = (window.TRUSTNET_CONFIG && window.TRUSTNET_CONFIG.api) || "";
  const $ = (id) => document.getElementById(id);

  // the questions, in form order, with the labels used in the review
  const QUESTIONS = [
    ["email", "Email"], ["paper_id", "Paper ID"], ["title", "Paper title"], ["authors", "All author names"],
    ["institutes", "All author affiliating institutes"], ["presenter", "Presenter of paper"],
    ["presenter_affiliation", "Presenter affiliation"], ["presenter_email", "Presenter email"],
    ["mobile", "Presenter mobile (WhatsApp)"], ["nationality", "Nationality"], ["amount", "Amount paid (₹)"],
    ["date", "Date of payment"], ["transaction", "Transaction ID"], ["proof", "Proof of payment"],
    ["whatsapp", "Joined the WhatsApp group"],
  ];

  const NATIONALITY = {
    india: "Indian", "united states": "American", usa: "American", us: "American", "united kingdom": "British", uk: "British",
    england: "British", scotland: "British", china: "Chinese", germany: "German", france: "French", japan: "Japanese",
    canada: "Canadian", australia: "Australian", italy: "Italian", spain: "Spanish", netherlands: "Dutch",
    singapore: "Singaporean", "south korea": "South Korean", korea: "South Korean", brazil: "Brazilian",
    bangladesh: "Bangladeshi", nepal: "Nepali", "sri lanka": "Sri Lankan", pakistan: "Pakistani", bhutan: "Bhutanese",
    "saudi arabia": "Saudi", "united arab emirates": "Emirati", uae: "Emirati", malaysia: "Malaysian",
    indonesia: "Indonesian", switzerland: "Swiss", sweden: "Swedish", norway: "Norwegian", denmark: "Danish",
    finland: "Finnish", ireland: "Irish", "new zealand": "New Zealander", russia: "Russian", egypt: "Egyptian",
    nigeria: "Nigerian", "south africa": "South African", kenya: "Kenyan", iran: "Iranian", turkey: "Turkish",
    vietnam: "Vietnamese", thailand: "Thai", portugal: "Portuguese", poland: "Polish", greece: "Greek",
  };

  const state = { authors: [], presenter: -1, receiptFile: null };

  // ------------------------------------------------------------ reading files
  async function read(file, kind) {
    let r;
    try {
      r = await fetch(`${API}/api/v1/extract?${new URLSearchParams({ kind })}`, {
        method: "POST", body: file,
        headers: { "Content-Type": "application/octet-stream", "X-File-Name": encodeURIComponent(file.name) },
      });
    } catch (_) {
      throw new Error("The reader couldn't be reached. Check your connection and try again.");
    }
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.detail || `The reader answered ${r.status}.`);
    return data;
  }

  function fieldsOf(fields) {
    const out = {};
    (fields || []).forEach((f) => {
      const empty = f.value === null || f.value === undefined || f.value === "" || (Array.isArray(f.value) && !f.value.length);
      if (!empty && !(f.key in out)) out[f.key] = f;
    });
    return out;
  }
  const groupFields = (result) => fieldsOf((result.groups || []).flatMap((g) => g.fields));

  function authorsOf(result) {
    return (result.authors || []).map((a) => {
      const f = fieldsOf(a.fields);
      const aff = f.affiliations ? [].concat(f.affiliations.value)[0] : "";
      return {
        name: (f.name && f.name.value) || a.name || "",
        email: f.email ? f.email.value : "",
        institute: f.institution ? f.institution.value : aff,
        country: f.country ? f.country.value : "",
        corresponding: !!a.corresponding,
        sure: ["name", "email", "institution"].every((k) => !f[k] || f[k].status === "verified"),
      };
    });
  }

  // ------------------------------------------------------------ filling answers
  function q(id) { return document.querySelector(`.q[data-q="${id}"]`); }

  /** Types a value into a question unless the person already typed their own. */
  function fill(id, value, { from, sure = true, force = false } = {}) {
    const box = q(id);
    const input = $(id);
    if (!box || value === undefined || value === null || value === "") return;
    if (!force && input.value && !box.dataset.from) return;      // keep what they typed
    input.value = value;
    mark(box, from, sure);
  }

  function mark(box, from, sure, label) {
    box.dataset.from = from;
    box.classList.toggle("needs-check", !sure);
    box.classList.remove("invalid");
    let tag = box.querySelector(".source");
    if (!tag) {
      tag = document.createElement("span");
      tag.className = "source";
      box.insertBefore(tag, box.firstChild);
    }
    tag.innerHTML = `<svg class="ic"><use href="#${sure ? "i-check" : "i-alert"}"/></svg>`;
    tag.append(label || (sure ? `From your ${from}` : `From your ${from}, check it`));
    box.classList.remove("flash");
    void box.offsetWidth;                // restart the highlight
    box.classList.add("flash");
  }

  /** Like fill, for answers that belong to one author: when the newly chosen
   *  author has no value, an answer the form filled for someone else is cleared
   *  (what the person typed themselves is kept). */
  function replace(id, value, opts) {
    const box = q(id);
    if (value) return fill(id, value, opts);
    if (box && box.dataset.from) {
      $(id).value = "";
      unmark(box);
    }
  }

  function unmark(box) {
    delete box.dataset.from;
    box.classList.remove("needs-check", "flash");
    const tag = box.querySelector(".source");
    if (tag) tag.remove();
  }

  function fillFromPaper(result) {
    const f = groupFields(result);
    state.authors = authorsOf(result);
    const authorsSure = state.authors.length > 0 && state.authors.every((a) => a.sure);
    fill("title", f.title && f.title.value, { from: "paper", sure: !!f.title && f.title.status === "verified", force: true });
    fill("authors", state.authors.map((a) => a.name).join(", "), { from: "paper", sure: authorsSure, force: true });
    // An author whose institute wasn't found keeps their place in the sequence
    // with a marker the form won't accept, so it can't be submitted by mistake.
    const institutes = state.authors.map((a) => a.institute || missing(a.name));
    fill("institutes", institutes.join(", "),
      { from: "paper", sure: authorsSure && state.authors.every((a) => a.institute), force: true });

    const corresponding = state.authors.findIndex((a) => a.corresponding);
    renderPresenterChips();
    if (state.authors.length) choosePresenter(corresponding >= 0 ? corresponding : 0);
    return `${state.authors.length} author${state.authors.length === 1 ? "" : "s"} found`;
  }

  function choosePresenter(i) {
    const a = state.authors[i];
    if (!a) return;
    state.presenter = i;
    fill("presenter", a.name, { from: "paper", sure: a.sure, force: true });
    replace("presenter_affiliation", a.institute, { from: "paper", sure: a.sure && !!a.institute, force: true });
    replace("presenter_email", a.email, { from: "paper", sure: a.sure, force: true });
    replace("email", a.email, { from: "paper", sure: false, force: !!q("email").dataset.from });
    if (q("email").dataset.from) mark(q("email"), "paper", false, "Same as presenter email");
    const nationality = NATIONALITY[(a.country || "").trim().toLowerCase()];
    replace("nationality", nationality, { from: "paper", sure: false, force: !!q("nationality").dataset.from });
    $("presenter-chips").querySelectorAll(".chip").forEach((c, j) => c.setAttribute("aria-pressed", String(j === i)));
    update();
  }

  function renderPresenterChips() {
    const box = $("presenter-chips");
    box.innerHTML = "";
    box.hidden = state.authors.length < 2;
    state.authors.forEach((a, i) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "chip";
      b.textContent = a.name;
      if (a.corresponding) {
        const s = document.createElement("small");
        s.textContent = "corresponding";
        b.appendChild(s);
      }
      b.addEventListener("click", () => choosePresenter(i));
      box.appendChild(b);
    });
  }

  function fillFromReceipt(result, file) {
    const f = groupFields(result);
    const sure = (k) => !!f[k] && f[k].status === "verified";
    fill("amount", f.amount && f.amount.value, { from: "receipt", sure: sure("amount"), force: true });
    const txn = f.utr || f.app_txn_id;
    fill("transaction", txn && txn.value, { from: "receipt", sure: !!txn && txn.status === "verified", force: true });
    const when = f.datetime && String(f.datetime.value).match(/^\d{4}-\d{2}-\d{2}/);
    fill("date", when && when[0], { from: "receipt", sure: sure("datetime"), force: true });
    attachProof(file, true);
    const status = f.status ? String(f.status.value) : "";
    return /success|complete|paid/i.test(status) || !status ? `${f.amount ? `₹${f.amount.value}` : "Receipt"} read` : `The receipt says: ${status}`;
  }

  function attachProof(file, fromReceipt) {
    state.receiptFile = file;
    $("proof-empty").hidden = !!file;
    $("proof-file").hidden = !file;
    $("proof-name").textContent = file ? file.name : "";
    const box = q("proof");
    if (file && fromReceipt) mark(box, "receipt", true);
    else unmark(box);
    update();
  }

  // ------------------------------------------------------------ the two drop zones
  function setupDrop(kind) {
    const input = $(`${kind}-file`), zone = $(`drop-${kind}`), stateEl = $(`${kind}-state`), note = $(`${kind}-note`);
    ["dragenter", "dragover"].forEach((t) => zone.addEventListener(t, () => zone.classList.add("over")));
    ["dragleave", "drop"].forEach((t) => zone.addEventListener(t, () => zone.classList.remove("over")));
    input.addEventListener("change", async () => {
      const file = input.files[0];
      if (!file) return;
      zone.classList.remove("done", "failed");
      zone.classList.add("busy");
      stateEl.textContent = "Reading…";
      note.hidden = true;
      note.classList.remove("error");
      showProgress(true, kind === "paper" ? `Reading ${file.name}: title, authors and affiliations…` : `Reading ${file.name}: amount, UTR and date…`);
      const slow = setTimeout(() => showProgress(true, "Still working. The reader may be waking up after a quiet spell; this can take up to a minute."), 7000);
      try {
        const result = await read(file, kind === "paper" ? "paper" : "upi");
        const wrongKind = (result.warnings || []).find((w) => /looks more like/i.test(w));
        const summary = kind === "paper" ? fillFromPaper(result) : fillFromReceipt(result, file);
        zone.classList.add("done");
        stateEl.textContent = "Read";
        note.textContent = wrongKind ? `${file.name}: ${wrongKind}` : `${file.name} · ${summary}`;
        note.classList.toggle("error", !!wrongKind);
        note.hidden = false;
      } catch (err) {
        zone.classList.add("failed");
        stateEl.textContent = "Try again";
        note.textContent = err.message;
        note.classList.add("error");
        note.hidden = false;
      } finally {
        clearTimeout(slow);
        zone.classList.remove("busy");
        showProgress(false);
        input.value = "";            // the same file can be chosen again
        update();
      }
    });
  }

  function showProgress(on, text) {
    $("progress").hidden = !on;
    if (text) $("progress-text").textContent = text;
  }

  // ------------------------------------------------------------ counts, checks, review
  const MISSING_RE = /\[not found: [^\]]*\]/;
  const missing = (name) => `[not found: ${name || "an author"}]`;

  function answered(id) {
    if (id === "whatsapp") return $("whatsapp").checked;
    if (id === "proof") return !!state.receiptFile;
    const value = $(id).value.trim();
    return value !== "" && !MISSING_RE.test(value);
  }

  function update() {
    const filled = QUESTIONS.filter(([id]) => q(id).dataset.from && answered(id)).length;
    const left = QUESTIONS.filter(([id]) => !answered(id)).length;
    $("count-filled").textContent = filled;
    $("count-left").textContent = left;
  }

  function validate() {
    const bad = [];
    QUESTIONS.forEach(([id]) => {
      const el = $(id);
      const ok = answered(id) && (!el || !el.checkValidity || el.checkValidity());
      q(id).classList.toggle("invalid", !ok);
      if (!ok) bad.push(id);
    });
    return bad;
  }

  function answers() {
    return QUESTIONS.map(([id, label]) => {
      let value;
      if (id === "whatsapp") value = $("whatsapp").checked ? "Yes" : "No";
      else if (id === "proof") value = state.receiptFile ? state.receiptFile.name : "";
      else value = $(id).value.trim();
      return [label, value];
    });
  }

  const asText = () => "TrustNet'26 registration\n\n" + answers().map(([l, v]) => `${l}: ${v}`).join("\n") + "\n";

  $("form").addEventListener("submit", (e) => {
    e.preventDefault();
    const bad = validate();
    const err = $("form-error");
    if (bad.length) {
      err.textContent = `${bad.length} question${bad.length === 1 ? " needs" : "s need"} an answer or a fix. They're marked in red.` +
        (MISSING_RE.test($("institutes").value) ? " Replace each [not found: …] with that author's institute from the paper." : "");
      err.hidden = false;
      q(bad[0]).scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" });
      const first = $(bad[0]);
      if (first && first.focus) first.focus({ preventScroll: true });
      return;
    }
    err.hidden = true;
    const list = $("review-list");
    list.innerHTML = "";
    answers().forEach(([label, value]) => {
      const dt = document.createElement("dt");
      dt.textContent = label;
      const dd = document.createElement("dd");
      dd.textContent = value;
      list.append(dt, dd);
    });
    $("review").showModal();
  });

  $("review-close").addEventListener("click", () => $("review").close());
  $("review-copy").addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    const label = btn.lastChild;
    try {
      await navigator.clipboard.writeText(asText());
      label.textContent = "Copied";
    } catch (_) {
      label.textContent = "Couldn't copy";
    }
    setTimeout(() => { label.textContent = "Copy all answers"; }, 1600);
  });
  $("review-download").addEventListener("click", () => {
    // made in the browser; nothing is uploaded
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([asText()], { type: "text/plain" }));
    a.download = "trustnet26-registration.txt";
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 0);
  });

  $("clear").addEventListener("click", () => {
    if (!confirm("Clear every answer on this form?")) return;
    $("form").reset();
    document.querySelectorAll(".q").forEach((box) => { unmark(box); box.classList.remove("invalid"); });
    state.authors = [];
    state.presenter = -1;
    renderPresenterChips();
    attachProof(null, false);
    ["paper", "receipt"].forEach((k) => {
      $(`drop-${k}`).classList.remove("done", "failed");
      $(`${k}-state`).textContent = "Choose";
      $(`${k}-note`).hidden = true;
    });
    $("form-error").hidden = true;
    update();
  });

  $("proof-remove").addEventListener("click", () => attachProof(null, false));

  // Typing over a filled answer makes it the person's own.
  $("form").addEventListener("input", (e) => {
    const box = e.target.closest(".q");
    if (box) {
      if (box.dataset.from && e.target.type !== "checkbox") unmark(box);
      box.classList.remove("invalid");
    }
    // The contact email follows the presenter's while it's a copy (or empty),
    // until the person types their own contact email.
    if (e.target.id === "presenter_email" && (q("email").dataset.from || !$("email").value.trim())) {
      $("email").value = $("presenter_email").value;
      mark(q("email"), "paper", false, "Same as presenter email");
    }
    update();
  });

  setupDrop("paper");
  setupDrop("receipt");
  update();
  // Wake the reader early: a free server sleeps when idle.
  fetch(`${API}/api/v1/health`).catch(() => {});
})();

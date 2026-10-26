// Abstract Mind form filler. Injected into the page only when you press "Fill
// this page" in the extension. For every visible field it reads the label the
// person sees (plus placeholder, name and id), decides which detail the field
// asks for, and types the value the way a person would: focus, set the value,
// fire input and change, blur. That way pages built with React or Angular see
// the change too. It never clicks Submit, never empties a field you already
// filled (unless you ask it to replace text), and outlines everything it typed
// so you can review it. Amber outlines mark values Abstract Mind was less sure of.
(() => {
  "use strict";
  if (window.__abstractMind) return;

  // ------------------------------------------------------------ what each field asks for
  // Checked in this order; the first match wins. Author details come first so
  // "Organization" or "E-mail" inside an author block is never read as a
  // paper-level field.
  const AUTHOR_FIELDS = [
    ["first_name", /first\s*-?\s*name|given\s*-?\s*names?|fore\s*names?|\bfname\b/],
    ["last_name", /last\s*-?\s*name|sur\s*-?\s*name|family\s*-?\s*name|\blname\b/],
    ["email", /e\s*-?\s*mail/],
    ["orcid", /orcid/],
    ["department", /department|\bdept\b/],
    ["affiliations", /affiliation/],
    ["institution", /organi[sz]ation|institution|university|employer|company/],
    ["city", /\bcity\b|\btown\b/],
    ["country", /\bcountry\b|country\s*\/\s*region/],
  ];
  const PAPER_FIELDS = [
    // Counts first, so "Abstract word count" is a count, not the abstract.
    ["pages", /(number|no\.?|count)\s*of\s*pages|page\s*count|total\s*pages/],
    ["words_main", /word\s*count|(number|no\.?)\s*of\s*words/],
    ["figures", /(number|no\.?)\s*of\s*figures/],
    ["tables", /(number|no\.?)\s*of\s*tables/],
    ["references", /(number|no\.?)\s*of\s*references/],
    ["short_title", /\b(short|running)\s*-?\s*(title|head)\b/],
    ["title", /\btitle\b/],
    ["abstract", /\babstract\b|\bsummary\b/],
    ["keywords", /key\s*-?\s*words?|key\s*phrases|index\s*terms/],
    ["grant_ids", /grant\s*(no|number|id)s?\b|award\s*(no|number)s?\b/],
    ["funding", /funding|financial\s*support|sponsor/],
    ["conflicts", /conflicts?\s*of\s*interests?|competing\s*interests?/],
    ["data", /data\s*(and\s*code\s*)?availability|data\s*access|code\s*availability/],
    ["contributions", /author\s*contributions?|credit\s*(authorship|statement)|contributions?\s*statement/],
    ["ethics", /ethic|\birb\b|informed\s*consent/],
    ["acknowledgments", /acknowledg/],
    ["doi", /\bdoi\b/],
  ];
  const UPI_FIELDS = [
    ["utr", /\butr\b|\brrn\b|upi\s*(ref|reference|transaction)|transaction\s*(ref|reference|id|no|number)|reference\s*(no|number|id)|payment\s*(ref|reference|id)/],
    ["payment_mode", /(payment|pay)\s*(mode|method)|mode\s*of\s*payment/],
    ["sender_upi", /\bupi\s*id\b|\bvpa\b/],
    ["sender_name", /payer|paid\s*by|remitter|account\s*holder|depositor/],
    ["bank", /\bbank\b/],
    ["amount", /amount|\bfees?\b|\bpaid\b/],
    ["date", /\bdate\b/],
    ["time", /\btime\b/],
  ];
  // Fields never filled. Whole words only, so "statement" or "research" are not caught.
  const NEVER = /\bpassword\b|captcha|\bsearch\b|user\s*name|\blog\s*-?\s*in\b|\botp\b|one[\s-]*time|\bpromo|\bcoupons?\b|salutation|\bprefix\b|honorific|job\s*title|\bdesignation\b|middle\s*name|nationality|citizenship|\bphone\b|\bmobile\b|\bfax\b|\bzip\b|postal|pin\s*code|\bstate\b|\bprovince\b|\bstreet\b|address\s*line/;
  const CORRESPONDING = /corresponding|contact\s*author|correspondence/;
  const FULL_NAME = /^(the\s*)?(author'?s?\s*)?(full\s*)?name$/;

  const COUNTRY_ALIASES = {
    "uk": ["united kingdom", "great britain", "uk"], "u k": ["united kingdom", "uk"], "england": ["united kingdom"],
    "scotland": ["united kingdom"], "wales": ["united kingdom"],
    "usa": ["united states", "united states of america", "usa", "us"], "us": ["united states", "united states of america", "usa"],
    "u s a": ["united states", "united states of america", "usa"], "united states of america": ["united states", "usa"],
    "south korea": ["korea republic of", "korea south", "republic of korea", "south korea", "korea"],
    "korea": ["korea republic of", "republic of korea", "south korea"], "republic of korea": ["korea republic of", "south korea"],
    "russia": ["russian federation"], "iran": ["iran islamic republic of"], "vietnam": ["viet nam"], "viet nam": ["vietnam"],
    "p r china": ["china"], "pr china": ["china"], "prc": ["china"], "taiwan": ["taiwan province of china", "taiwan roc"],
    "czech republic": ["czechia"], "czechia": ["czech republic"], "turkey": ["turkiye"], "turkiye": ["turkey"],
    "uae": ["united arab emirates"], "the netherlands": ["netherlands"], "holland": ["netherlands"],
  };

  // ------------------------------------------------------------ reading the page
  function textOf(node) {
    return node ? (node.innerText || node.textContent || "").replace(/\s+/g, " ").trim() : "";
  }

  function labelText(el) {
    const parts = [];
    if (el.labels && el.labels.length) [...el.labels].forEach((l) => parts.push(textOf(l)));
    const aria = el.getAttribute("aria-label");
    if (aria) parts.push(aria);
    (el.getAttribute("aria-labelledby") || "").split(/\s+/).filter(Boolean).forEach((id) => {
      const n = document.getElementById(id);
      if (n) parts.push(textOf(n));
    });
    if (!parts.length) {
      // Table layouts (EasyChair, older systems): the label sits in the cell before.
      const cell = el.closest("td, th");
      if (cell && cell.previousElementSibling) parts.push(textOf(cell.previousElementSibling));
    }
    for (let n = el, i = 0; !parts.length && n && i < 3; i++, n = n.parentElement) {
      // Otherwise: the nearest text just before the field.
      let s = n.previousElementSibling;
      while (s && !textOf(s)) s = s.previousElementSibling;
      if (s) parts.push(textOf(s).slice(-80));
    }
    return parts.join(" ").slice(0, 160);
  }

  function helpText(el) {
    const out = [];
    (el.getAttribute("aria-describedby") || "").split(/\s+/).filter(Boolean).forEach((id) => {
      const n = document.getElementById(id);
      if (n) out.push(textOf(n));
    });
    let s = el.nextElementSibling;
    if (s && textOf(s).length < 160) out.push(textOf(s));
    return out.join(" ");
  }

  function describe(el) {
    const label = labelText(el);
    const idName = [el.name, el.id].filter(Boolean).join(" ")
      .replace(/([a-z])([A-Z])/g, "$1 $2").replace(/[_\-[\].]+/g, " ");
    const placeholder = el.getAttribute("placeholder") || "";
    const extra = [placeholder, el.getAttribute("title"), helpText(el)].filter(Boolean).join(" ");
    return {
      label: label || placeholder || idName || "(unlabelled field)",
      // What the field asks for is decided from these only. Help text next to
      // a field ("do not repeat the title here") would mislead it.
      text: `${label} ${placeholder} ${idName}`.toLowerCase(),
      plainLabel: label.toLowerCase().replace(/[*:()]/g, " ").replace(/\s+/g, " ").trim(),
      idName: idName.toLowerCase(),
      // Help text is used only to format the value ("one keyword per line", "dd/mm/yyyy").
      hint: `${extra} ${label}`.toLowerCase(),
    };
  }

  function visible(el) {
    if (el.disabled || el.readOnly || el.type === "hidden") return false;
    if (!el.getClientRects().length) return false;
    const s = getComputedStyle(el);
    return s.visibility !== "hidden" && s.display !== "none";
  }

  function fillable() {
    const types = new Set(["", "text", "email", "url", "tel", "number", "date", "datetime-local", "time", "checkbox", "radio"]);
    return [...document.querySelectorAll("input, textarea, select, [contenteditable=''], [contenteditable='true']")]
      .filter((el) => (el.tagName !== "INPUT" || types.has((el.getAttribute("type") || "").toLowerCase())) && visible(el));
  }

  function isSalutationSelect(el) {
    if (el.tagName !== "SELECT") return false;
    const hits = [...el.options].filter((o) => /^(dr|mr|mrs|ms|miss|prof|professor)\.?$/i.test(o.text.trim()));
    return hits.length >= 2;
  }

  function classify(el, d, kind) {
    if (NEVER.test(d.text) || isSalutationSelect(el)) return null;
    if (el.type === "checkbox" || el.type === "radio") {
      return CORRESPONDING.test(d.text) && kind === "paper" ? { key: "corresponding", level: "author" } : null;
    }
    if (kind === "upi") {
      for (const [key, rx] of UPI_FIELDS) if (rx.test(d.text)) return { key, level: "paper" };
      return null;
    }
    for (const [key, rx] of AUTHOR_FIELDS) if (rx.test(d.text)) return { key, level: "author" };
    for (const [key, rx] of PAPER_FIELDS) if (rx.test(d.text)) return { key, level: "paper" };
    if (FULL_NAME.test(d.plainLabel) || /\b(full|author)\s*name\b/.test(d.idName)) return { key: "name", level: "author" };
    return null;
  }

  // ------------------------------------------------------------ values
  const v = (entry) => (entry ? entry.value : null);

  function splitName(name) {
    const t = String(name || "").trim().split(/\s+/);
    return t.length < 2 ? { first: "", last: t[0] || "" } : { first: t.slice(0, -1).join(" "), last: t[t.length - 1] };
  }

  function authorValue(a, key) {
    if (!a) return null;
    const st = (k) => (a[k] ? a[k].status : "check");
    const parts = splitName(v(a.name));
    switch (key) {
      case "first_name": return a.first_name ? a.first_name : (parts.first ? { value: parts.first, status: "check" } : null);
      case "last_name": return a.last_name ? a.last_name : (parts.last ? { value: parts.last, status: "check" } : null);
      case "affiliations": {
        const list = v(a.affiliations);
        return list && list.length ? { value: list[0], status: st("affiliations") } : null;
      }
      case "institution": {
        if (a.institution) return a.institution;
        const list = v(a.affiliations);
        return list && list.length ? { value: list[0], status: "check" } : null;
      }
      case "corresponding": return a.corresponding || { value: false, status: "check" };
      default: return a[key] || null;
    }
  }

  function upiValue(f, key) {
    if (key === "payment_mode") return { value: "UPI", status: "verified" };
    if (key === "date" || key === "time") return f.datetime || null;
    return f[key] || null;
  }

  function norm(s) {
    return String(s).normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase()
      .replace(/[^a-z0-9 ]+/g, " ").replace(/\s+/g, " ").trim();
  }

  // Shape a value for this particular box.
  function shape(el, d, key, value) {
    if (Array.isArray(value)) {
      if (key === "keywords") {
        const perLine = el.tagName === "TEXTAREA" && /per\s*line|each\s*line|separate\s*lines|new\s*line|one\s*keyword\s*per/.test(d.hint);
        return value.join(perLine ? "\n" : /semicolon/.test(d.hint) ? "; " : ", ");
      }
      return value.join("; ");
    }
    if (key === "date" || key === "time") {
      const m = String(value).match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
      if (!m) return String(value);
      const [, Y, M, D, h, min] = m;
      const type = (el.getAttribute("type") || "").toLowerCase();
      if (key === "time" || type === "time") return `${h}:${min}`;
      if (type === "date") return `${Y}-${M}-${D}`;
      if (type === "datetime-local") return `${Y}-${M}-${D}T${h}:${min}`;
      if (/yyyy\s*[-/.]\s*mm/.test(d.hint)) return `${Y}-${M}-${D}`;
      if (/mm\s*[-/.]\s*dd/.test(d.hint)) return `${M}/${D}/${Y}`;
      return /dd\s*-\s*mm/.test(d.hint) ? `${D}-${M}-${Y}` : `${D}/${M}/${Y}`;
    }
    if ((el.getAttribute("type") || "") === "number") {
      const n = String(value).replace(/,/g, "");
      return /^-?\d+(\.\d+)?$/.test(n) ? n : null;
    }
    return String(value);
  }

  // ------------------------------------------------------------ typing
  function nativeSet(el, value) {
    const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype
      : el.tagName === "SELECT" ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value);
  }

  function typeInto(el, text) {
    el.focus({ preventScroll: true });
    if (el.isContentEditable) {
      document.execCommand("selectAll", false);
      if (!document.execCommand("insertText", false, text)) el.textContent = text;
    } else {
      nativeSet(el, text);
      el.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: text }));
    }
    el.dispatchEvent(new Event("change", { bubbles: true }));
    el.blur();
  }

  function chooseOption(el, value) {
    const want = norm(value);
    const accept = new Set([want, ...(COUNTRY_ALIASES[want] || []).map(norm)]);
    const opts = [...el.options];
    let pick = opts.find((o) => accept.has(norm(o.text)) || accept.has(norm(o.value)));
    if (!pick && want.length > 3) pick = opts.find((o) => norm(o.text).startsWith(want) || (norm(o.text).length > 3 && want.startsWith(norm(o.text))));
    if (!pick) return false;
    el.focus({ preventScroll: true });
    nativeSet(el, pick.value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    el.blur();
    return true;
  }

  function hasValue(el) {
    if (el.tagName === "SELECT") return el.selectedIndex > 0 && el.value !== "";
    if (el.isContentEditable) return textOf(el) !== "";
    return String(el.value || "").trim() !== "";
  }

  // ------------------------------------------------------------ highlighting
  function ensureStyle() {
    if (document.getElementById("abstract-mind-style")) return;
    const s = document.createElement("style");
    s.id = "abstract-mind-style";
    s.textContent = `
      [data-abstract-mind="ok"] { outline: 2px solid #1F5FBF !important; outline-offset: 1px !important; background-color: rgba(31,95,191,.07) !important; }
      [data-abstract-mind="check"] { outline: 2px solid #C98A1B !important; outline-offset: 1px !important; background-color: rgba(201,138,27,.10) !important; }`;
    (document.head || document.documentElement).appendChild(s);
  }

  function mark(el, status, note) {
    ensureStyle();
    el.setAttribute("data-abstract-mind", status === "verified" ? "ok" : "check");
    if (!el.hasAttribute("title")) {
      el.setAttribute("title", note);
      el.setAttribute("data-abstract-mind-title", "1");
    }
  }

  function clear() {
    document.querySelectorAll("[data-abstract-mind]").forEach((el) => {
      el.removeAttribute("data-abstract-mind");
      if (el.hasAttribute("data-abstract-mind-title")) {
        el.removeAttribute("title");
        el.removeAttribute("data-abstract-mind-title");
      }
    });
    const s = document.getElementById("abstract-mind-style");
    if (s) s.remove();
    return true;
  }

  // ------------------------------------------------------------ the fill
  function fill(data, opts) {
    const overwrite = !!(opts && opts.overwrite);
    const report = { frame: location.host || location.href, filled: [], kept: 0, unmatched: [], warnings: [], authorBlocks: 0 };
    const authors = data.authors || [];
    const corrIndex = authors.findIndex((a) => a.corresponding && a.corresponding.value === true);

    // 1. Decide what every field asks for.
    const found = [];
    const unmatched = new Set();
    fillable().forEach((el) => {
      const d = describe(el);
      const what = classify(el, d, data.kind);
      if (what) found.push({ el, d, ...what });
      else if (!hasValue(el) && el.type !== "checkbox" && el.type !== "radio" && d.label !== "(unlabelled field)") unmatched.add(d.label.slice(0, 60));
    });

    // 2. Which author each author field belongs to: numbered names/ids
    //    (first_name1, authors[2].email) when every field of that kind has a
    //    distinct number, otherwise the order the fields appear on the page.
    const byKey = {};
    found.filter((f) => f.level === "author").forEach((f) => (byKey[f.key] = byKey[f.key] || []).push(f));
    Object.entries(byKey).forEach(([key, list]) => {
      if (key === "corresponding" && list.every((f) => f.el.type === "radio")) {
        list.forEach((f, i) => (f.author = i));   // one radio per author
        return;
      }
      const nums = list.map((f) => {
        const m = `${f.el.name || ""} ${f.el.id || ""}`.match(/\d+/g);
        return m ? Number(m[m.length - 1]) : null;
      });
      const distinct = nums.every((n) => n !== null) && new Set(nums).size === nums.length;
      const order = list.map((f, i) => i);
      if (distinct) order.sort((x, y) => nums[x] - nums[y]);
      order.forEach((idx, rank) => (list[idx].author = rank));
      list.forEach((f) => {
        if (key !== "corresponding" && CORRESPONDING.test(f.d.text)) f.author = corrIndex;   // "Corresponding author e-mail"
      });
    });
    report.authorBlocks = Math.max(0, ...["first_name", "last_name", "name", "email"].map((k) => (byKey[k] || []).length));

    // 3. Type the values.
    found.forEach((f) => {
      const { el, d, key } = f;
      let entry;
      if (f.level === "author") {
        if (f.author < 0 || f.author === undefined) return;
        entry = authorValue(authors[f.author], key);
      } else {
        entry = data.kind === "upi" ? upiValue(data.fields, key) : data.fields[key];
      }
      if (!entry || entry.value === null || entry.value === undefined) {
        if (!hasValue(el) && el.type !== "checkbox" && el.type !== "radio") unmatched.add(d.label.slice(0, 60));   // asked for, but not in the paper
        return;
      }
      const who = f.level === "author" ? `Author ${f.author + 1} · ` : "";
      const note = `Filled by Abstract Mind: ${who}${d.label}`;

      if (el.type === "checkbox" || el.type === "radio") {
        const want = entry.value === true;
        if (el.type === "radio" ? (want && !el.checked) : (el.checked !== want && (want || overwrite))) {
          el.click();
          mark(el, entry.status, note);
          report.filled.push({ label: d.label, key, author: f.author, status: entry.status, value: want ? "Yes" : "No" });
        }
        return;
      }
      if (hasValue(el) && !overwrite) {
        report.kept += 1;
        return;
      }
      const text = shape(el, d, key, entry.value);
      if (text === null || text === "") return;
      if (el.tagName === "SELECT") {
        if (!chooseOption(el, text)) {
          report.warnings.push(`"${d.label}" has no option matching "${text}".`);
          return;
        }
      } else {
        typeInto(el, text);
        if (el.maxLength > 0 && text.length > el.maxLength) {
          report.warnings.push(`"${d.label}" allows ${el.maxLength} characters; the value has ${text.length}. Shorten it before submitting.`);
        }
      }
      mark(el, entry.status, note);
      report.filled.push({ label: d.label, key, author: f.level === "author" ? f.author : null, status: entry.status, value: text.slice(0, 80) });
    });

    if (data.kind === "paper" && report.authorBlocks > 0 && report.authorBlocks < authors.length) {
      const missing = authors.length - report.authorBlocks;
      report.warnings.push(`This form shows ${report.authorBlocks} author ${report.authorBlocks === 1 ? "block" : "blocks"}; the paper has ${authors.length} authors. Add ${missing} more on the page, then press Fill again. Fields already filled are kept.`);
    }
    report.unmatched = [...unmatched].slice(0, 15);
    return report;
  }

  window.__abstractMind = { fill, clear, version: 1 };
})();

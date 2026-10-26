// Working with an extraction result: field labels, reading and writing values,
// the short summary kept (encrypted) for the library list, and exports.

export const STATUS_LABEL = { verified: "Verified", check: "Check", needs_review: "Review", missing: "Not found" };
export const SOURCE_LABEL = {
  tex: "from LaTeX", template: "app template", rule: "rules", count: "counted", generic: "generic rules",
  llm: "AI", suggested: "AI suggestion", layout: "layout", you: "edited by you", none: "",
};
export const LIST_KEYS = new Set(["keywords", "affiliations", "grant_ids", "data_urls", "credit_roles", "approval_ids"]);

export function hasValue(f) {
  return !(f.value === null || f.value === undefined || f.value === "" || (Array.isArray(f.value) && !f.value.length));
}
export const found = (f) => f.status !== "missing" || hasValue(f);

export function toText(f) {
  if (f.value === null || f.value === undefined) return "";
  if (Array.isArray(f.value)) return f.value.join(f.key === "affiliations" ? " | " : "; ");
  return String(f.value);
}

export function fromText(f, text) {
  if (LIST_KEYS.has(f.key) || Array.isArray(f.value)) {
    const sep = f.key === "affiliations" ? "|" : ";";
    return text.split(sep).map((s) => s.trim()).filter(Boolean);
  }
  return text;
}

export const plainValue = (f) => (typeof f.value === "boolean" ? (f.value ? "Yes" : "No") : toText(f));

export function groupFields(result) {
  const out = [];
  (result.groups || []).forEach((g) => out.push(...g.fields));
  return out;
}

export function allFields(result) {
  const out = groupFields(result);
  (result.authors || []).forEach((a) => out.push(...a.fields));
  return out;
}

function firstValue(result, key) {
  const f = allFields(result).find((x) => x.key === key && hasValue(x));
  return f ? f.value : null;
}

/** The library row for a result. It is encrypted along with the document, so
 * titles and authors are never visible to the server. */
export function summarize(result) {
  const fields = allFields(result);
  let title, byline = "";
  if (result.kind === "paper") {
    title = firstValue(result, "title");
    const names = (result.authors || []).map((a) => a.name).filter(Boolean);
    if (names.length) byline = names[0] + (names.length > 2 ? " et al." : names.length === 2 ? ` and ${names[1]}` : "");
    const dates = ["published", "accepted", "received"].map((k) => firstValue(result, k) || "").join(" ");
    const year = dates.match(/\b(?:19|20)\d{2}\b/);
    if (year) byline += (byline ? " · " : "") + year[0];
  } else {
    const amount = firstValue(result, "amount"), payee = firstValue(result, "receiver_name");
    title = amount ? `₹${amount}${payee ? ` to ${payee}` : ""}` : payee;
    const when = firstValue(result, "datetime");
    const pretty = when ? new Date(when).toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "";
    byline = [firstValue(result, "app"), pretty].filter(Boolean).join(" · ");
  }
  return {
    v: 1,
    kind: result.kind,
    title: title ? String(title).slice(0, 300) : null,
    byline: byline.slice(0, 200) || null,
    filename: result.filename || "untitled",
    file_type: result.file_type || null,
    pages: result.pages || null,
    fields_found: fields.filter((f) => f.status !== "missing").length,
    fields_total: fields.length,
  };
}

export function exportObject(result) {
  const out = { file: result.filename, kind: result.kind, extracted: {} };
  (result.groups || []).forEach((g) => g.fields.forEach((f) => { out.extracted[f.key] = f.value; }));
  if (result.kind === "paper") {
    out.extracted.authors = (result.authors || []).map((a, i) => {
      const o = { position: i + 1 };
      a.fields.forEach((f) => { o[f.key] = f.value; });
      return o;
    });
  }
  return out;
}

export function asPlainText(result) {
  const lines = [];
  const put = (f, indent) => {
    if (f.status === "missing" && !hasValue(f)) return;
    lines.push(`${indent}${f.label}: ${plainValue(f)}`);
  };
  (result.groups || []).forEach((g, gi) => {
    lines.push(g.title.toUpperCase());
    g.fields.forEach((f) => put(f, "  "));
    lines.push("");
    if (gi === 0 && result.kind === "paper") {
      (result.authors || []).forEach((a, i) => {
        lines.push(`AUTHOR ${i + 1}${a.corresponding ? " (corresponding)" : ""}`);
        a.fields.forEach((f) => put(f, "  "));
        lines.push("");
      });
    }
  });
  return lines.join("\n").trim() + "\n";
}

// Turns an Abstract Mind result (the JSON the site and API return) into the flat
// shape the form filler uses: one entry per detail with its value and status,
// plus one such set per author in printed order. Missing details are left out,
// so the filler never types an empty or guessed value.
(function (root) {
  "use strict";

  function entries(fields) {
    const out = {};
    (fields || []).forEach((f) => {
      const empty = f.value === null || f.value === undefined || f.value === "" ||
        (Array.isArray(f.value) && f.value.length === 0);
      if (!empty) out[f.key] = { value: f.value, status: f.status, label: f.label };
    });
    return out;
  }

  function toFillData(result) {
    const paper = {};
    (result.groups || []).forEach((g) => Object.assign(paper, entries(g.fields)));
    const authors = (result.authors || []).map((a) => entries(a.fields));
    let title = paper.title ? paper.title.value : null;
    if (result.kind === "upi") {
      const amount = paper.amount ? `₹${paper.amount.value}` : null;
      const payee = paper.receiver_name ? paper.receiver_name.value : null;
      title = [amount, payee && `to ${payee}`].filter(Boolean).join(" ") || "UPI receipt";
    }
    return {
      kind: result.kind,
      filename: result.filename || null,
      title: title || result.filename || "Untitled",
      fields: paper,
      authors,
    };
  }

  root.AbstractMindData = { toFillData };
})(typeof window !== "undefined" ? window : globalThis);

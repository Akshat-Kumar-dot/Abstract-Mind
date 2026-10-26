// Tiny test harness for the form filler. Each test page lays out a form the
// way a real submission or payment system does, loads a real Abstract Mind result,
// runs the filler and checks every field. Results go into #results and into
// document.title ("PASS 14/14") so they can be read without looking.
window.FormTest = {
  rows: [],
  async load(path, tweak) {
    const result = await (await fetch(path)).json();
    const data = AbstractMindData.toFillData(result);
    if (tweak) tweak(data);
    return data;
  },
  expect(name, actual, wanted) {
    const ok = actual === wanted;
    this.rows.push({ name, ok, actual, wanted });
    return ok;
  },
  value(sel) {
    const el = document.querySelector(sel);
    if (!el) return "(missing element)";
    if (el.type === "checkbox" || el.type === "radio") return el.checked;
    if (el.isContentEditable) return el.textContent;
    return el.value;
  },
  done(report) {
    const pass = this.rows.filter((r) => r.ok).length;
    const box = document.getElementById("results");
    const esc = (s) => String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
    box.innerHTML = `<h2>${pass === this.rows.length ? "PASS" : "FAIL"} ${pass}/${this.rows.length}</h2>` +
      "<table>" + this.rows.map((r) => `<tr class="${r.ok ? "ok" : "bad"}"><td>${r.ok ? "✓" : "✗"}</td><td>${esc(r.name)}</td>` +
        `<td>${r.ok ? "" : `got <code>${esc(JSON.stringify(r.actual))}</code>, wanted <code>${esc(JSON.stringify(r.wanted))}</code>`}</td></tr>`).join("") +
      "</table>" + (report ? `<pre>${esc(JSON.stringify(report, null, 1))}</pre>` : "");
    document.title = `${pass === this.rows.length ? "PASS" : "FAIL"} ${pass}/${this.rows.length}`;
  },
};

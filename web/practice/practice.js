// Shared behaviour for the practice forms, wired through data attributes so
// the pages need no inline scripts (the site's Content-Security-Policy forbids
// them):
//
//   data-practice              the form; Submit shows what would have been sent
//   data-start-authors="3"     how many author blocks the page starts with
//   data-author-block="sel"    the block to copy when adding an author
//   data-add-author="id"       the "add more authors" button for container #id
//   data-countries             a <select> that gets the country list
(function () {
  "use strict";

  const COUNTRIES = ["Argentina", "Australia", "Austria", "Bangladesh", "Belgium", "Brazil", "Canada", "Chile", "China",
    "Colombia", "Czechia", "Denmark", "Egypt", "Finland", "France", "Germany", "Greece", "Hong Kong", "Hungary", "India",
    "Indonesia", "Iran, Islamic Republic of", "Ireland", "Israel", "Italy", "Japan", "Kenya", "Korea, Republic of",
    "Malaysia", "Mexico", "Nepal", "Netherlands", "New Zealand", "Nigeria", "Norway", "Pakistan", "Philippines", "Poland",
    "Portugal", "Qatar", "Russian Federation", "Saudi Arabia", "Singapore", "South Africa", "Spain", "Sri Lanka", "Sweden",
    "Switzerland", "Taiwan", "Thailand", "Turkey", "United Arab Emirates", "United Kingdom", "United States", "Viet Nam"];

  const escapeHtml = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  // Adding an author copies the first block and renumbers its fields, the way
  // EasyChair-style systems name them (first_name1, first_name2, ...).
  function addAuthor(container) {
    const blocks = container.querySelectorAll(container.dataset.authorBlock);
    const n = blocks.length + 1;
    const copy = blocks[0].cloneNode(true);
    copy.querySelectorAll("[name], [id], [for]").forEach((el) => {
      ["name", "id", "for"].forEach((attr) => {
        const v = el.getAttribute(attr);
        if (v && !(attr === "name" && el.type === "radio")) el.setAttribute(attr, v.replace(/\d+$/, String(n)));
      });
      if (el.type === "checkbox" || el.type === "radio") el.checked = false;
      else if (el.tagName === "SELECT") el.selectedIndex = 0;
      else if ("value" in el && el.tagName !== "OPTION") el.value = "";
    });
    copy.querySelectorAll("[data-n]").forEach((el) => { el.textContent = String(n); });
    copy.querySelectorAll("input[type=radio]").forEach((r) => { r.value = String(n); });
    blocks[blocks.length - 1].after(copy);
  }

  // Submit sends nothing: it shows the values, with empty required fields marked.
  function showSubmission(form) {
    const rows = [];
    form.querySelectorAll("input, textarea, select, .rich").forEach((el) => {
      if (["button", "submit", "reset", "file"].includes(el.type)) return;
      if (el.type === "radio" && !el.checked) return;
      let value;
      if (el.classList.contains("rich")) value = el.textContent;
      else if (el.type === "checkbox") value = el.checked ? "yes" : "no";
      else value = el.value;
      rows.push({ name: el.getAttribute("name") || el.id || "(no name)", value: String(value), required: el.dataset.required === "1" });
    });
    const empties = rows.filter((r) => r.required && !r.value.trim()).length;
    const out = form.parentElement.querySelector(".sent") || document.createElement("section");
    out.className = "sent";
    out.innerHTML = `<h3>Practice only: nothing was sent.</h3>
      <p>${empties ? `${empties} required field${empties === 1 ? " is" : "s are"} still empty (marked red).` : "All required fields have a value."}</p>
      <table>${rows.map((r) => `<tr><td>${escapeHtml(r.name)}</td><td class="${r.required && !r.value.trim() ? "empty" : ""}">${
        r.value.trim() ? escapeHtml(r.value).replace(/\n/g, "<br>") : "(empty)"}</td></tr>`).join("")}</table>`;
    form.after(out);
    out.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  document.querySelectorAll("select[data-countries]").forEach((sel) => {
    COUNTRIES.forEach((c) => sel.appendChild(new Option(c)));
  });
  document.querySelectorAll("[data-start-authors]").forEach((box) => {
    for (let i = box.querySelectorAll(box.dataset.authorBlock).length; i < Number(box.dataset.startAuthors); i++) addAuthor(box);
  });
  document.querySelectorAll("[data-add-author]").forEach((b) => {
    b.addEventListener("click", () => addAuthor(document.getElementById(b.dataset.addAuthor)));
  });
  document.querySelectorAll("form[data-practice]").forEach((form) => {
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      showSubmission(form);
    });
    form.addEventListener("reset", () => {
      const sent = form.parentElement.querySelector(".sent");
      if (sent) sent.remove();
      form.querySelectorAll(".rich").forEach((r) => { r.textContent = ""; });
    });
  });
})();

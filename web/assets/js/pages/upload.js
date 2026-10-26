// Add a document: upload → the server reads it in memory and returns the
// details → they are encrypted here and saved to the library. The file itself
// is never stored, and nothing goes to an AI provider unless "Let AI help" is
// ticked for this upload.

import { uploadFile } from "../lib/api.js";
import { $, formatSize, reduceMotion } from "../lib/dom.js";
import * as library from "../services/library.js";

const STEP_LABEL = ["Uploading…", "Reading the file…", "Finding the details…", "Encrypting and saving…", "Done"];
let go = () => {};

export function init(navigate, health) {
  go = navigate;
  const form = $("form"), fileInput = $("file"), drop = $("drop");
  fileInput.addEventListener("change", showChosen);
  ["dragenter", "dragover"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((t) => drop.addEventListener(t, () => drop.classList.remove("over")));
  drop.addEventListener("drop", (e) => {
    e.preventDefault();
    if (e.dataTransfer && e.dataTransfer.files.length) { fileInput.files = e.dataTransfer.files; showChosen(); }
  });
  form.addEventListener("submit", submit);
  if (health && health.ai_provider) {
    const name = health.ai_provider === "gemini" ? "Google Gemini" : "Groq";
    $("ai-row").hidden = false;
    $("ai-provider").textContent = name;
  }
}

export function show() {
  document.title = "New extraction · Abstract Mind";
  $("form").hidden = false;
  $("progress").hidden = true;
  setStatus("");
}

const chosen = () => $("file").files && $("file").files[0];

function showChosen() {
  const f = chosen();
  const el = $("chosen");
  if (!f) { el.hidden = true; $("go").disabled = true; return; }
  el.textContent = `${f.name} · ${formatSize(f.size)}`;
  el.hidden = false;
  $("go").disabled = false;
}

function setStep(n, note, fill) {
  $("working-label").textContent = STEP_LABEL[n];
  $("working-fill").style.width = `${fill !== undefined ? fill : [8, 35, 65, 90, 100][n]}%`;
  $("steps").querySelectorAll("li").forEach((li, i) => {
    li.classList.toggle("done", i < n);
    li.classList.toggle("on", i === n);
  });
  if (note !== undefined) $("progress-note").textContent = note;
}

function setStatus(text, isError) {
  $("status").textContent = text;
  $("status").classList.toggle("error", !!isError);
}

async function submit(e) {
  e.preventDefault();
  const f = chosen();
  if (!f) return;
  const kind = $("form").querySelector("input[name=kind]:checked").value;
  const allowAi = !$("ai-row").hidden && $("allow-ai").checked;
  $("go").disabled = true;
  setStatus("");
  $("progress").hidden = false;
  $("form").hidden = true;
  $("progress-what").textContent = kind === "upi" ? "receipt" : kind === "paper" ? "paper" : "document";
  setStep(0, `Sending ${f.name}…`);
  let reading;
  try {
    const result = await uploadFile(f, { kind, allow_ai: allowAi ? "true" : "false" }, (p) => {
      if (p < 1) { setStep(0, `Sending ${f.name}… ${Math.round(p * 100)}%`, 4 + p * 26); return; }
      if (reading) return;
      setStep(1, "Laying out pages, columns and fonts.");
      reading = setTimeout(() => setStep(2, "Matching authors to affiliations and checking every value against the text."), 1400);
    });
    clearTimeout(reading);
    setStep(3, "Encrypting the details in your browser, then saving them.");
    const saved = await library.save(result);
    await new Promise((r) => setTimeout(r, reduceMotion ? 0 : 300));
    setStep(4, "Done.");
    $("file").value = "";
    showChosen();
    go(`#/doc/${saved.id}`);
  } catch (err) {
    clearTimeout(reading);
    $("progress").hidden = true;
    $("form").hidden = false;
    setStatus(err.message || "Something went wrong.", true);
  } finally {
    $("go").disabled = !chosen();
  }
}

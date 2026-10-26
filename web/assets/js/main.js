// Abstract Mind web app: boot and routing.
//
//   signed out   #/            landing page
//                #/login       log in          #/signup   sign up (Google or guest)
//   new Google   (any)         set the password that locks the library
//   locked       (any)         unlock with password (new device, cleared data)
//   signed in    #/            library         #/starred  #/receipts
//                #/new         add a document  #/doc/<id> one document
//                #/account     settings        #/keep     guest → account
//
// Pages live in pages/, the account and the encrypted library in services/,
// and shared helpers in lib/. Nothing here talks to the server directly.

import { whenSignedOut } from "./lib/api.js";
import { $, reduceMotion } from "./lib/dom.js";
import * as accountPage from "./pages/account.js";
import * as authPage from "./pages/auth.js";
import * as documentPage from "./pages/document.js";
import * as libraryPage from "./pages/library.js";
import * as passwordPage from "./pages/password.js";
import * as unlockPage from "./pages/unlock.js";
import * as uploadPage from "./pages/upload.js";
import * as account from "./services/session.js";

const SHELVES = { "/": "all", "/starred": "starred", "/receipts": "receipts" };
const VIEWS = ["welcome", "auth", "password", "unlock", "app"];
const PAGES = ["library", "new", "paper", "account"];

function navigate(hash) {
  if (location.hash === hash) route();
  else location.hash = hash;
}

function showView(name) {
  VIEWS.forEach((v) => { $(`view-${v}`).hidden = v !== name; });
}

function route() {
  const hash = location.hash.replace(/^#/, "") || "/";
  window.scrollTo(0, 0);

  if (!account.signedIn()) {
    if (hash === "/login" || hash === "/signup") {
      showView("auth");
      authPage.show(hash.slice(1));
    } else {
      showView("welcome");
      document.title = "Abstract Mind · Extract research metadata in seconds";
    }
    return;
  }
  if (account.needsPassword()) {
    showView("password");
    passwordPage.show();
    return;
  }
  if (account.locked()) {
    showView("unlock");
    unlockPage.show();
    return;
  }
  if (hash === "/keep" && account.isGuest()) {
    showView("auth");
    authPage.show("claim");
    return;
  }
  if (hash === "/login" || hash === "/signup" || hash === "/keep") {
    history.replaceState(null, "", "#/");
    return route();
  }

  showView("app");
  const u = account.session.me.user;
  $("avatar").textContent = u.guest ? "G" : (u.name || u.email).trim()[0].toUpperCase();
  $("avatar").title = u.guest ? "Guest account" : `${u.name} · ${u.email}`;
  const doc = hash.match(/^\/doc\/([A-Za-z0-9_-]{16})$/);
  const page = doc ? "paper" : hash === "/new" ? "new" : hash === "/account" ? "account" : "library";
  PAGES.forEach((p) => { $(`page-${p}`).hidden = p !== page; });
  if (page === "library") libraryPage.show(SHELVES[hash] || "all");
  else if (page === "new") uploadPage.show();
  else if (page === "account") accountPage.show();
  else documentPage.show(doc[1]);
}

async function logOut() {
  if (account.isGuest() && !confirm("Logging out of a guest account deletes it and everything saved in it. Create an account first to keep them.\n\nLog out anyway?")) return;
  await documentPage.flush();
  await account.logOut();
  history.replaceState(null, "", location.pathname);
  route();
}

async function boot() {
  if (location.protocol === "file:") {
    document.body.innerHTML = `<div class="file-note"><h1>Start the server first</h1>
      <p>This page was opened as a file, so logging in and saving can't work. Start Abstract Mind and open
      <a href="http://localhost:8765">http://localhost:8765</a> instead.</p></div>`;
    return;
  }
  if (!globalThis.crypto || !globalThis.crypto.subtle) {
    document.body.innerHTML = `<div class="file-note"><h1>This browser can't encrypt</h1>
      <p>Abstract Mind encrypts your library in the browser, which needs a secure (https) connection and a current browser.</p></div>`;
    return;
  }

  let health = null;
  try {
    health = await (await fetch("/api/v1/health")).json();
    $("limit").textContent = health.max_upload_mb;
    $("engine").textContent = `rules${health.ocr ? " · OCR" : ""}${health.ai_provider ? " · AI on request" : ""}`;
  } catch (_) {
    $("engine").textContent = "server not reachable";
  }

  authPage.init(navigate, health);
  passwordPage.init(navigate);
  unlockPage.init(navigate);
  libraryPage.init();
  uploadPage.init(navigate, health);
  documentPage.init(navigate);
  accountPage.init(navigate);
  $("logout").addEventListener("click", logOut);
  $("view-welcome").addEventListener("click", (e) => {
    const a = e.target.closest("[data-jump]");
    if (!a) return;
    e.preventDefault();
    $(a.dataset.jump).scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
  });
  whenSignedOut(async () => {
    await account.forget();
    route();
  });
  window.addEventListener("hashchange", async () => {
    await documentPage.flush();
    route();
  });

  await account.restore();
  route();
}

boot();

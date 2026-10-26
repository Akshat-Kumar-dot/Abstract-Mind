// Sign up, log in, and "keep your papers" (guest → account).
//
// New accounts are made with Google or as a guest; there's no email sign-up.
// Accounts that were made with an email and password can still log in with
// them from the "Log in with email" section on the log-in page.

import { ApiError } from "../lib/api.js";
import { $, busy, showError } from "../lib/dom.js";
import * as account from "../services/session.js";

// Why the server sent someone back from Google (?signin=…)
const SIGNIN_ERRORS = {
  cancelled: "Google sign-in was cancelled.",
  expired: "That sign-in took too long or was started in another tab. Try again.",
  unverified: "That Google account's email isn't verified yet, so it can't be used here.",
  unreachable: "Google couldn't be reached. Check your connection and try again.",
  failed: "Google sign-in didn't work. Try again.",
  off: "Google sign-in isn't switched on for this server yet.",
};

let mode = "signup";
let go = () => {};
let googleOn = false;
let pendingError = "";

export function init(navigate, health) {
  go = navigate;
  googleOn = !!(health && health.google);
  $("auth-form").addEventListener("submit", submit);
  document.querySelectorAll("[data-guest]").forEach((b) => b.addEventListener("click", () => startGuest(b)));

  const params = new URLSearchParams(location.search);
  const code = params.get("signin");
  if (code) {
    pendingError = SIGNIN_ERRORS[code] || SIGNIN_ERRORS.failed;
    history.replaceState(null, "", location.pathname + location.hash);
  }
}

export function show(next) {
  mode = next;
  const login = mode === "login", claim = mode === "claim";
  $("auth-title").textContent = login ? "Welcome back" : claim ? "Keep your papers" : "Create your account";
  $("auth-sub").textContent = login ? "Continue with Google to open your library."
    : claim ? "Continue with Google. Everything you saved as a guest moves into your account."
    : "Continue with Google to save every paper you extract. You'll set a password next, which locks your library so only you can read it.";
  $("google-go").hidden = !googleOn;
  $("google-off").hidden = googleOn;
  $("guest-block").hidden = claim;
  $("email-block").hidden = !login;
  showError($("signin-error"), pendingError);
  pendingError = "";
  showError($("auth-error"), "");
  document.title = `${login ? "Log in" : claim ? "Keep your papers" : "Sign up"} · Abstract Mind`;
}

function message(err) {
  if (err instanceof ApiError && err.status === 422 && err.fields.includes("email")) return "Enter a valid email address.";
  return err.message || "Something went wrong.";
}

async function submit(e) {
  e.preventDefault();
  const email = $("auth-email").value.trim();
  const password = $("auth-password").value;
  if (!email || !password) return showError($("auth-error"), "Enter your email and password.");
  showError($("auth-error"), "");
  try {
    await busy($("auth-go"), "Opening your library…", () => account.logIn(email, password));
    $("auth-password").value = "";
    go("#/");
  } catch (err) {
    showError($("auth-error"), message(err));
  }
}

async function startGuest(button) {
  button.disabled = true;
  try {
    await account.startGuest();
    go("#/");
  } catch (err) {
    alert(message(err));
  } finally {
    button.disabled = false;
  }
}

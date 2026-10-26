// Account settings: what Abstract Mind can and can't see, change password,
// delete the account. Both forms prove the password in the browser; the
// server only ever receives derived keys.

import { $, busy, plural, showError } from "../lib/dom.js";
import * as account from "../services/session.js";

const MIN_PASSWORD = 10;
let go = () => {};

export function init(navigate) {
  go = navigate;
  $("pw-form").addEventListener("submit", changePassword);
  $("del-form").addEventListener("submit", deleteAccount);
}

export function show() {
  document.title = "Account · Abstract Mind";
  const { user, stats } = account.session.me;
  const since = new Date(user.since * 1000).toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" });
  $("acct-line").textContent = user.guest
    ? `Guest account since ${since} · ${plural(stats.total, "saved document")}, kept in this browser only.`
    : `${user.name} · ${user.email} · member since ${since}`;
  $("acct-password").hidden = user.guest;
  $("acct-guest").hidden = !user.guest;
  $("del-pw-row").hidden = user.guest;
  ["pw-error", "pw-done", "del-error"].forEach((id) => showError($(id), ""));
}

async function changePassword(e) {
  e.preventDefault();
  const current = $("pw-current").value, next = $("pw-new").value, again = $("pw-repeat").value;
  showError($("pw-done"), "");
  if (next.length < MIN_PASSWORD) return showError($("pw-error"), `Use a new password of at least ${MIN_PASSWORD} characters.`);
  if (next !== again) return showError($("pw-error"), "The two new passwords don't match.");
  showError($("pw-error"), "");
  try {
    await busy($("pw-go"), "Re-encrypting your key…", () => account.changePassword(current, next));
    ["pw-current", "pw-new", "pw-repeat"].forEach((id) => { $(id).value = ""; });
    showError($("pw-done"), "Password changed. Other devices have been signed out.");
  } catch (err) {
    showError($("pw-error"), err.message);
  }
}

async function deleteAccount(e) {
  e.preventDefault();
  if ($("del-confirm").value.trim().toLowerCase() !== "delete my account") {
    return showError($("del-error"), "Type “delete my account” to confirm.");
  }
  showError($("del-error"), "");
  try {
    await busy($("del-go"), "Deleting…", () => account.deleteAccount($("del-password").value));
    go("#/");
  } catch (err) {
    showError($("del-error"), err.status === 401 ? "That password is wrong." : err.message);
  }
}

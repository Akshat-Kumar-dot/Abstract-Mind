// Shown once, right after someone first continues with Google: Google proves
// who they are but gives us nothing secret, so this password is what locks
// their library (see services/session.js setPassword). Checked here because
// the server never sees it.

import { $, busy, showError } from "../lib/dom.js";
import * as account from "../services/session.js";

const MIN_PASSWORD = 10;
let go = () => {};

export function init(navigate) {
  go = navigate;
  $("password-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const first = $("new-password").value, second = $("new-password-2").value;
    if (first.length < MIN_PASSWORD) return showError($("password-error"), `Use at least ${MIN_PASSWORD} characters.`);
    if (first !== second) return showError($("password-error"), "The two passwords don't match.");
    showError($("password-error"), "");
    try {
      await busy($("password-go"), "Locking your library…", () => account.setPassword(first));
      $("new-password").value = $("new-password-2").value = "";
      go("#/");
    } catch (err) {
      showError($("password-error"), err.message || "Something went wrong.");
    }
  });
  $("password-logout").addEventListener("click", async () => {
    await account.logOut();
    go("#/");
  });
}

export function show() {
  const u = account.session.me.user;
  const first = (u.name || "").split(/\s+/)[0];
  $("password-sub").textContent = `${first ? `Hi ${first}, you're` : "You're"} signed in as ${u.email}. One last step: choose a password for your library.`;
  showError($("password-error"), "");
  document.title = "Set a password · Abstract Mind";
  setTimeout(() => $("new-password").focus(), 0);
}

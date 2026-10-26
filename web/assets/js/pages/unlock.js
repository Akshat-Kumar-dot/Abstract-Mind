// Shown when the session is valid but this browser doesn't hold the key that
// opens the library: a new device, or cleared site data. Registered accounts
// unlock with their password. A guest's key existed only in the browser that
// created it, so a guest library can't be reopened anywhere else.

import { $, busy, showError } from "../lib/dom.js";
import * as account from "../services/session.js";

let go = () => {};

export function init(navigate) {
  go = navigate;
  $("unlock-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    showError($("unlock-error"), "");
    try {
      await busy($("unlock-go"), "Opening…", () => account.unlockWith($("unlock-password").value));
      $("unlock-password").value = "";
      go("#/");
    } catch (err) {
      showError($("unlock-error"), err.message);
    }
  });
  $("unlock-logout").addEventListener("click", async () => {
    await account.logOut();
    go("#/");
  });
}

export function show() {
  const guest = account.isGuest();
  $("unlock-sub").textContent = guest
    ? "This guest library was started in another browser, or this browser's data was cleared. Its key was only ever in that browser, so its papers can't be opened here."
    : `Enter the password for ${account.session.me.user.email} to open your library on this device.`;
  $("unlock-form").hidden = guest;
  $("unlock-logout").textContent = guest ? "Start over" : "Log out";
  document.title = "Unlock · Abstract Mind";
}

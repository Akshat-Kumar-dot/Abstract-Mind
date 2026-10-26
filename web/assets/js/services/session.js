// Who is signed in, and the key that opens their library.
//
// The password never leaves this file's functions: it is stretched in the
// browser (lib/vault.js) and only the derived auth key is sent. The data key
// that encrypts every document is created here, wrapped with the password for
// the server, and kept in IndexedDB between visits (lib/keystore.js).
//
// A guest's data key is created in this browser and exists nowhere else until
// the guest sets an email and password, which wraps that same key.
//
// "Continue with Google" happens on the server (a redirect to Google and
// back). A new Google account has no password yet, so it lands in the
// needs-password state; setPassword() then creates the data key (or reuses the
// guest's, if a guest continued with Google) and wraps it with that password.

import { api } from "../lib/api.js";
import * as keystore from "../lib/keystore.js";
import * as vault from "../lib/vault.js";

export const session = {
  me: null,        // { user, key, stats } from /auth/me
  dataKey: null,   // CryptoKey, or null while locked
};

const ownerOf = (user) => (user.guest ? `guest:${user.since}` : `user:${user.email}`);

async function refresh() {
  session.me = await api("/auth/me", { quiet: true });
  return session.me;
}

async function keep(key) {
  session.dataKey = key;
  await keystore.save(ownerOf(session.me.user), key);
}

/** On page load: is there a session, and is its key in this browser? */
export async function restore() {
  try {
    await refresh();
  } catch (_) {
    session.me = null;
    session.dataKey = null;
    return;
  }
  const user = session.me.user;
  session.dataKey = await keystore.load(ownerOf(user));
  // A guest who just continued with Google: their key is still filed under the guest.
  if (!session.dataKey && user.needs_password) session.dataKey = await keystore.load(`guest:${user.since}`);
}

export const signedIn = () => !!session.me;
export const needsPassword = () => !!session.me && !!session.me.user.needs_password;
export const locked = () => !!session.me && !needsPassword() && !session.dataKey;
export const isGuest = () => !!session.me && session.me.user.guest;

function checkMaterial(material) {
  if (!material || material.kdf !== vault.KDF) throw new Error("This account uses a key format this page doesn't know.");
}

export async function signUp(email, password, name) {
  const dataKey = await vault.newDataKey();
  const creds = await vault.makeCredentials(password, dataKey);
  await api("/auth/signup", { json: { email, name, ...creds } });
  await refresh();
  await keep(await vault.nonExtractable(dataKey));
}

export async function logIn(email, password) {
  const material = await api("/auth/prelogin", { json: { email } });
  checkMaterial(material);
  const { authKey, wrapKey } = await vault.deriveKeys(password, vault.b64.decode(material.salt), material.iterations);
  const res = await api("/auth/login", { json: { email, auth_key: vault.b64.encode(authKey) }, quiet: true });
  const dataKey = await vault.unwrapDataKey(res.key.wrapped_key, wrapKey);
  await refresh();
  await keep(dataKey);
}

export async function startGuest() {
  const dataKey = await vault.newDataKey();     // stays extractable so it can be wrapped if the guest signs up
  await api("/auth/guest", { method: "POST" });
  await refresh();
  await keep(dataKey);
}

/** Guest → full account. The guest's key is wrapped with the new password,
 * so every document saved as a guest stays readable. */
export async function claim(email, password, name) {
  if (!session.dataKey) throw new Error("This guest library's key isn't in this browser.");
  const creds = await vault.makeCredentials(password, session.dataKey);
  await api("/auth/claim", { json: { email, name, ...creds } });
  await refresh();
  await keep(await vault.nonExtractable(session.dataKey));
}

/** First password for an account made with Google. Keeps a guest's key, so
 * papers saved before continuing with Google stay readable. */
export async function setPassword(password) {
  const dataKey = session.dataKey ? await extractable(session.dataKey) : await vault.newDataKey();
  const creds = await vault.makeCredentials(password, dataKey);
  await api("/auth/password", { json: creds });
  await refresh();
  await keep(await vault.nonExtractable(dataKey));
}

async function extractable(key) {
  if (key.extractable) return key;
  throw new Error("This library's key can't be re-wrapped here. Log out and continue with Google again.");
}

/** The session is valid but this browser doesn't hold the key (new device,
 * cleared storage): open it with the password. */
export async function unlockWith(password) {
  const material = session.me.key;
  checkMaterial(material);
  let opened;
  try {
    opened = await vault.unlock(password, material);
  } catch (_) {
    throw new Error("That password doesn't open your library.");
  }
  await keep(opened.dataKey);
}

export async function changePassword(current, next) {
  const material = session.me.key;
  checkMaterial(material);
  const { authKey, wrapKey } = await vault.deriveKeys(current, vault.b64.decode(material.salt), material.iterations);
  let dataKey;
  try {
    dataKey = await vault.unwrapDataKey(material.wrapped_key, wrapKey, true);
  } catch (_) {
    throw new Error("Your current password is wrong.");
  }
  const creds = await vault.makeCredentials(next, dataKey);
  await api("/account/password", { json: { current_auth_key: vault.b64.encode(authKey), ...creds } });
  await refresh();
}

export async function deleteAccount(password) {
  const body = { confirm: "delete my account" };
  if (!isGuest()) body.auth_key = await vault.authKeyFor(password, session.me.key);
  await api("/account/delete", { json: body, quiet: true });
  await forget();
}

export async function logOut() {
  await api("/auth/logout", { method: "POST", quiet: true }).catch(() => {});
  await forget();
}

/** Drop everything this browser knows about the account. */
export async function forget() {
  session.me = null;
  session.dataKey = null;
  await keystore.clear();
}

// Vault: everything Abstract Mind encrypts happens here, in the browser, with the
// Web Crypto API. The server only ever sees the outputs.
//
//   password ──PBKDF2-SHA256 (600,000 rounds, per-account salt)──▶ master key
//   master   ──HKDF "auth"──▶ auth key   (sent to the server to log in; stored there as a scrypt hash)
//   master   ──HKDF "wrap"──▶ wrap key   (never leaves the browser)
//   data key (random AES-256-GCM)  ──wrapped with the wrap key──▶ stored on the server, unreadable there
//   every saved document ──AES-256-GCM with the data key──▶ stored on the server, unreadable there
//
// Envelope format for every sealed value: base64( 0x01 | 12-byte IV | ciphertext+tag ).
// The "purpose" string is bound in as additional data, so a document's title
// can't be swapped for its body, or a body passed off as a key.
//
// The same file runs in the extension (copied to extension/lib/vault.js; a
// test keeps the copies identical) and under Node for the unit tests.

const VERSION = 1;
export const KDF = "pbkdf2-sha256";
export const ITERATIONS = 600_000;
const subtle = globalThis.crypto.subtle;
const utf8 = new TextEncoder();
const fromUtf8 = new TextDecoder();

export const b64 = {
  encode(bytes) {
    let s = "";
    const u = new Uint8Array(bytes);
    for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode(...u.subarray(i, i + 0x8000));
    return btoa(s);
  },
  decode(text) {
    const s = atob(text);
    const out = new Uint8Array(s.length);
    for (let i = 0; i < s.length; i++) out[i] = s.charCodeAt(i);
    return out;
  },
};

export function randomBytes(n) {
  return globalThis.crypto.getRandomValues(new Uint8Array(n));
}

// ---------------------------------------------------------------- passwords

/** Stretch a password into the auth key (bytes) and the wrap key (CryptoKey). */
export async function deriveKeys(password, salt, iterations = ITERATIONS) {
  const pwKey = await subtle.importKey("raw", utf8.encode(password.normalize("NFKC")), "PBKDF2", false, ["deriveBits"]);
  const master = await subtle.deriveBits({ name: "PBKDF2", hash: "SHA-256", salt, iterations }, pwKey, 256);
  const hkdf = await subtle.importKey("raw", master, "HKDF", false, ["deriveBits", "deriveKey"]);
  // "paper-mind" is the app's old name, kept on purpose: this label is part of
  // how every account's keys are derived, so changing it locks everyone out.
  const info = (label) => ({ name: "HKDF", hash: "SHA-256", salt: new Uint8Array(0), info: utf8.encode(`paper-mind ${label} v1`) });
  const authKey = new Uint8Array(await subtle.deriveBits(info("auth"), hkdf, 256));
  const wrapKey = await subtle.deriveKey(info("wrap"), hkdf, { name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]);
  return { authKey, wrapKey };
}

// ---------------------------------------------------------------- sealing

export async function seal(key, bytes, purpose) {
  const iv = randomBytes(12);
  const ct = new Uint8Array(await subtle.encrypt({ name: "AES-GCM", iv, additionalData: utf8.encode(purpose) }, key, bytes));
  const out = new Uint8Array(1 + iv.length + ct.length);
  out[0] = VERSION;
  out.set(iv, 1);
  out.set(ct, 1 + iv.length);
  return b64.encode(out);
}

export async function open(key, sealed, purpose) {
  const raw = b64.decode(sealed);
  if (raw.length < 29 || raw[0] !== VERSION) throw new Error("Unknown encryption format");
  return new Uint8Array(await subtle.decrypt({ name: "AES-GCM", iv: raw.subarray(1, 13), additionalData: utf8.encode(purpose) },
    key, raw.subarray(13)));
}

export async function sealJSON(key, value, purpose) {
  return seal(key, utf8.encode(JSON.stringify(value)), purpose);
}

export async function openJSON(key, sealed, purpose) {
  return JSON.parse(fromUtf8.decode(await open(key, sealed, purpose)));
}

// ---------------------------------------------------------------- data keys

/** A fresh data key. Extractable, so it can be wrapped for the server. */
export function newDataKey() {
  return subtle.generateKey({ name: "AES-GCM", length: 256 }, true, ["encrypt", "decrypt"]);
}

export async function wrapDataKey(dataKey, wrapKey) {
  return seal(wrapKey, new Uint8Array(await subtle.exportKey("raw", dataKey)), "data-key");
}

/** A copy of a data key whose bytes scripts can no longer read. */
export async function nonExtractable(key) {
  const raw = await subtle.exportKey("raw", key);
  return subtle.importKey("raw", raw, { name: "AES-GCM" }, false, ["encrypt", "decrypt"]);
}

/** Opens the wrapped data key. Keep `extractable` false except when the key
 * must be wrapped again (changing the password). */
export async function unwrapDataKey(wrapped, wrapKey, extractable = false) {
  const raw = await open(wrapKey, wrapped, "data-key");
  return subtle.importKey("raw", raw, { name: "AES-GCM" }, extractable, ["encrypt", "decrypt"]);
}

/** Everything sign-up, claim and password change send to the server. */
export async function makeCredentials(password, dataKey) {
  const salt = randomBytes(16);
  const { authKey, wrapKey } = await deriveKeys(password, salt, ITERATIONS);
  return {
    auth_key: b64.encode(authKey),
    kdf_salt: b64.encode(salt),
    kdf_iterations: ITERATIONS,
    wrapped_key: await wrapDataKey(dataKey, wrapKey),
  };
}

/** Password + the key material from /auth/me or /auth/login → keys. */
export async function unlock(password, material, extractable = false) {
  if (material.kdf !== KDF) throw new Error("Unknown key derivation");
  const { authKey, wrapKey } = await deriveKeys(password, b64.decode(material.salt), material.iterations);
  let dataKey = null;
  if (material.wrapped_key) dataKey = await unwrapDataKey(material.wrapped_key, wrapKey, extractable);
  return { authKey: b64.encode(authKey), dataKey };
}

/** Just the auth key, for log-in before the wrapped key is known. */
export async function authKeyFor(password, material) {
  const { authKey } = await deriveKeys(password, b64.decode(material.salt), material.iterations);
  return b64.encode(authKey);
}

// Unit tests for the browser vault. Run: node --test tests/web/vault.test.mjs
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import * as vault from "../../web/assets/js/lib/vault.js";

const FAST = 1000;   // the real ITERATIONS is slow on purpose; the maths is the same

test("the auth key and wrap key are deterministic for a password and salt", async () => {
  const salt = vault.randomBytes(16);
  const a = await vault.deriveKeys("correct horse", salt, FAST);
  const b = await vault.deriveKeys("correct horse", salt, FAST);
  const c = await vault.deriveKeys("correct horsf", salt, FAST);
  assert.deepEqual(a.authKey, b.authKey);
  assert.notDeepEqual(a.authKey, c.authKey);
  assert.equal(a.authKey.length, 32);
  assert.equal(a.wrapKey.extractable, false);
});

test("the auth key reveals nothing usable as the wrap key", async () => {
  const salt = vault.randomBytes(16);
  const { authKey, wrapKey } = await vault.deriveKeys("pw-123456", salt, FAST);
  const dataKey = await vault.newDataKey();
  const wrapped = await vault.wrapDataKey(dataKey, wrapKey);
  const pretend = await globalThis.crypto.subtle.importKey("raw", authKey, "AES-GCM", false, ["decrypt"]);
  await assert.rejects(vault.unwrapDataKey(wrapped, pretend));
});

test("documents round-trip and any tampering is detected", async () => {
  const key = await vault.newDataKey();
  const doc = { title: "Mapping glacier retreat", authors: ["Asha Raman"], n: 4 };
  const sealed = await vault.sealJSON(key, doc, "body");
  assert.deepEqual(await vault.openJSON(key, sealed, "body"), doc);
  assert.ok(!sealed.includes("glacier"));
  const raw = vault.b64.decode(sealed);
  raw[raw.length - 1] ^= 1;
  await assert.rejects(vault.openJSON(key, vault.b64.encode(raw), "body"));
  await assert.rejects(vault.openJSON(key, sealed, "meta"));            // wrong purpose
  await assert.rejects(vault.openJSON(await vault.newDataKey(), sealed, "body"));
});

test("every seal uses a fresh IV", async () => {
  const key = await vault.newDataKey();
  const a = await vault.sealJSON(key, { x: 1 }, "body");
  const b = await vault.sealJSON(key, { x: 1 }, "body");
  assert.notEqual(a, b);
});

test("credentials unlock the same data key, and the wrong password doesn't", async () => {
  const dataKey = await vault.newDataKey();
  const creds = await vault.makeCredentials("my long password", dataKey);
  assert.equal(creds.kdf_iterations, vault.ITERATIONS);
  assert.equal(vault.b64.decode(creds.auth_key).length, 32);
  const material = { kdf: vault.KDF, salt: creds.kdf_salt, iterations: creds.kdf_iterations, wrapped_key: creds.wrapped_key };
  const opened = await vault.unlock("my long password", material);
  assert.equal(opened.authKey, creds.auth_key);
  assert.equal(opened.dataKey.extractable, false);
  const sealed = await vault.sealJSON(dataKey, { ok: true }, "body");
  assert.deepEqual(await vault.openJSON(opened.dataKey, sealed, "body"), { ok: true });
  await assert.rejects(vault.unlock("not my password", material));
});

test("passwords are normalised, so the same password typed differently still works", async () => {
  const salt = vault.randomBytes(16);
  const composed = await vault.deriveKeys("café-password", salt, FAST);
  const decomposed = await vault.deriveKeys("café-password", salt, FAST);
  assert.deepEqual(composed.authKey, decomposed.authKey);
});

test("the extension carries an identical copy of the vault", () => {
  const web = readFileSync(new URL("../../web/assets/js/lib/vault.js", import.meta.url), "utf8");
  const ext = readFileSync(new URL("../../extension/lib/vault.js", import.meta.url), "utf8");
  assert.equal(ext, web, "run: python scripts/sync_extension.py");
});

// Keeps the data key between page loads, in IndexedDB, as a CryptoKey object.
// For a registered account the stored key is non-extractable: page scripts can
// use it but can't read its bytes. It is tagged with its owner, so a key left
// behind by another account in this browser is never used, and it is deleted
// on log-out. If IndexedDB isn't available (some private windows), the key
// lives only in memory and the library asks for the password after a reload.

const DB_NAME = "abstract-mind";
const STORE = "keys";
const ID = "data-key";

let memory = null;

function openDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function run(mode, fn) {
  const db = await openDb();
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, mode);
      const req = fn(tx.objectStore(STORE));
      tx.oncomplete = () => resolve(req && req.result);
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error);
    });
  } finally {
    db.close();
  }
}

export async function save(owner, key) {
  memory = { owner, key };
  try {
    await run("readwrite", (s) => s.put({ owner, key }, ID));
  } catch (_) { /* memory only */ }
}

export async function load(owner) {
  if (memory && memory.owner === owner) return memory.key;
  try {
    const entry = await run("readonly", (s) => s.get(ID));
    if (entry && entry.owner === owner) {
      memory = entry;
      return entry.key;
    }
  } catch (_) { /* nothing stored */ }
  return null;
}

export async function clear() {
  memory = null;
  try {
    await run("readwrite", (s) => s.delete(ID));
  } catch (_) { /* nothing stored */ }
}

// The encrypted library. Documents are sealed with the data key before they
// leave the browser and opened again only here. The server stores ciphertext,
// sizes, star flags and dates; titles and authors are inside the ciphertext.

import { api } from "../lib/api.js";
import { summarize } from "../lib/fields.js";
import * as vault from "../lib/vault.js";
import { session } from "./session.js";

function key() {
  if (!session.dataKey) throw new Error("Your library is locked. Enter your password to open it.");
  return session.dataKey;
}

export async function list() {
  const data = await api("/documents");
  const k = key();
  const docs = await Promise.all(data.documents.map(async (d) => {
    try {
      return { ...d, ...(await vault.openJSON(k, d.meta, "meta")), unreadable: false };
    } catch (_) {
      return { ...d, kind: "paper", title: null, filename: "Can't be opened", unreadable: true, fields_found: 0, fields_total: 0 };
    }
  }));
  return { docs, stats: data.stats };
}

export async function open(id) {
  const d = await api(`/documents/${encodeURIComponent(id)}`);
  let result;
  try {
    result = await vault.openJSON(key(), d.body, "body");
  } catch (_) {
    throw new Error("This document can't be opened with your key. It may have been saved by a different account.");
  }
  return { result, saved: { id: d.id, starred: d.starred, created_at: d.created_at, updated_at: d.updated_at } };
}

async function seal(result) {
  const k = key();
  return { meta: await vault.sealJSON(k, summarize(result), "meta"), body: await vault.sealJSON(k, result, "body") };
}

export async function save(result) {
  return api("/documents", { json: await seal(result) });
}

export async function update(id, result) {
  return api(`/documents/${encodeURIComponent(id)}`, { method: "PUT", json: await seal(result) });
}

export const star = (id, starred) => api(`/documents/${encodeURIComponent(id)}`, { method: "PATCH", json: { starred } });
export const remove = (id) => api(`/documents/${encodeURIComponent(id)}`, { method: "DELETE" });

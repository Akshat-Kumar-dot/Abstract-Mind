// The one way the web app talks to the server: JSON in and out of /api/v1,
// cookies only for this site, and a single place that notices an expired
// session.

const BASE = "/api/v1";

export class ApiError extends Error {
  constructor(status, message, fields) {
    super(message);
    this.status = status;
    this.fields = fields || [];
  }
}

let onSignedOut = null;

/** Called when the server says the session is gone. */
export function whenSignedOut(fn) {
  onSignedOut = fn;
}

export async function api(path, { method = "GET", json, headers = {}, quiet = false } = {}) {
  const init = { method, credentials: "same-origin", headers: { ...headers } };
  if (json !== undefined) {
    if (method === "GET") init.method = "POST";
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(json);
  }
  let r;
  try {
    r = await fetch(BASE + path, init);
  } catch (_) {
    throw new ApiError(0, "Abstract Mind can't be reached. Check your connection and try again.");
  }
  const data = await r.json().catch(() => ({}));
  if (r.status === 401 && !quiet && onSignedOut) onSignedOut();
  if (!r.ok) throw new ApiError(r.status, data.detail || `The server answered ${r.status}.`, data.fields);
  return data;
}

/** Sends a file as the raw request body, reporting upload progress (0–1).
 * Raw bodies are read in memory on the server; nothing is written to disk. */
export function uploadFile(file, params, onProgress) {
  return new Promise((resolve, reject) => {
    const x = new XMLHttpRequest();
    x.open("POST", `${BASE}/extract?${new URLSearchParams(params)}`);
    x.setRequestHeader("Content-Type", "application/octet-stream");
    x.setRequestHeader("X-File-Name", encodeURIComponent(file.name));
    x.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    x.upload.onload = () => onProgress(1);
    x.onload = () => {
      let data = {};
      try { data = JSON.parse(x.responseText); } catch (_) { /* not JSON */ }
      if (x.status >= 200 && x.status < 300) resolve(data);
      else reject(new ApiError(x.status, data.detail || `The server answered ${x.status}.`));
    };
    x.onerror = () => reject(new ApiError(0, "Abstract Mind can't be reached. Check your connection and try again."));
    x.send(file);
  });
}

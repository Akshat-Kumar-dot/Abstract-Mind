// Stand-in for the chrome.* APIs the extension popup uses, so the popup can run
// as a normal page at http://localhost:8765/_dev/extension/ (development only).
// Storage lives in memory and is lost on reload, permission requests are
// granted, and scripting does nothing, so "Fill this page" has no effect here.
(() => {
  const area = () => {
    const data = {};
    return {
      async get(keys) {
        const out = {};
        (Array.isArray(keys) ? keys : [keys]).forEach((k) => { if (k in data) out[k] = data[k]; });
        return out;
      },
      async set(values) { Object.assign(data, JSON.parse(JSON.stringify(values))); },
      async remove(keys) { (Array.isArray(keys) ? keys : [keys]).forEach((k) => delete data[k]); },
    };
  };
  window.chrome = {
    storage: { local: area(), session: area() },
    permissions: { request: async () => true },
    tabs: { create: ({ url }) => window.open(url, "_blank"), query: async () => [] },
    runtime: { getURL: (path) => path },
    scripting: { executeScript: async () => [] },
  };
})();

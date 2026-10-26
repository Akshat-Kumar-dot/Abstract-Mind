// Where the Abstract Mind reader runs. The form sends files there only to be
// read (POST /api/v1/extract): nothing is stored. If your Render address is
// different, change it here and in _headers (connect-src).
window.TRUSTNET_CONFIG = {
  api: /^(localhost|127\.0\.0\.1)$/.test(location.hostname)
    ? "http://localhost:8765"                    // trying it locally
    : "https://abstract-mind.onrender.com",
};

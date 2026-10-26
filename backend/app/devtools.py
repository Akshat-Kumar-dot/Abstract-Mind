"""Development only: the Chrome extension's popup as a normal page.

Open http://localhost:8765/_dev/extension/ to try the popup without loading the
extension into Chrome. It is served from this server, so it talks to the same
API and uses the same sign-in as the site. extension-tests/chrome-stub.js
stands in for the chrome.* APIs (storage, permissions, tabs); "Fill this page"
does nothing here, and filling is tested by the pages in extension-tests/.

Never mounted when APP_ENV=production, and the Docker image doesn't contain
the extension folder, so it can't appear on the live site.
"""
from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .settings import ROOT

PREFIX = "/_dev/extension"
EXTENSION_DIR = ROOT / "extension"
STUB = ROOT / "extension-tests" / "chrome-stub.js"


def mount_extension_preview(app: FastAPI) -> None:
    if not (EXTENSION_DIR / "popup.html").is_file() or not STUB.is_file():
        return

    @app.get(f"{PREFIX}/", include_in_schema=False)
    def popup() -> HTMLResponse:
        html = (EXTENSION_DIR / "popup.html").read_text(encoding="utf-8")
        html = html.replace('<script src="shared.js"></script>',
                            '<script src="chrome-stub.js"></script>\n  <script src="shared.js"></script>', 1)
        return HTMLResponse(html)

    @app.get(f"{PREFIX}/chrome-stub.js", include_in_schema=False)
    def stub() -> FileResponse:
        return FileResponse(STUB, media_type="text/javascript")

    app.mount(PREFIX, StaticFiles(directory=EXTENSION_DIR), name="extension-preview")

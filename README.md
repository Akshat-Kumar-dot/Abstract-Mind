# Abstract Mind

Upload a document, get back the details that forms ask for.

- **Research manuscripts** (PDF, Word `.docx`, LaTeX `.tex`): title, abstract, keywords; authors in the printed order with first/last name, email, ORCID, affiliation (department, institution, city, country) and the corresponding-author mark; funding and grant numbers, conflicts of interest, data availability, CRediT roles, ethics; page, word, figure, table and reference counts. For papers that are already published: DOI, publisher (from the DOI prefix), journal, volume and the received/accepted/published dates.
- **UPI receipts** (PDF or screenshot): amount, status, date and time, UTR, the app's own transaction ID, payer and payee names and UPI IDs, bank, last 4 digits, note.

Every field comes with a status (Verified / Check / Review / Not found), where it came from, and the line of the file it was read from. Everything is editable before you copy it.

Sign in with Google, or try it as a guest, to keep a library. Each extraction is encrypted in your browser and saved to your account (the extracted fields, never the uploaded file), edits are saved as you type, and the dashboard shows how many papers and receipts you have extracted. New Google accounts set a password once; it locks the library so only its owner can read it, and is asked for again only on a new device.

## How it works

Every input is turned into the same list of text blocks (with font size and position when the format has them), then:

1. **Zones**: the paper is split into header, abstract, body, declarations and references using headings that every template has. Authors are only read from the header, so cited authors never appear as authors. Journals with no headings at all (Nature, Science, Cell) are handled too: the header ends at the first run of prose, the opening paragraph is taken as the abstract, and the numbered small-type list is taken as the references.
2. **Header**: title by font size; every other line is classified as author, affiliation, email or note.
3. **Linking**: authors to affiliations by superscript markers, side-by-side IEEE blocks, "X is with ..." footnotes, or a single shared affiliation; emails by name similarity. Nothing is linked by guessing from order.
4. **LLM (optional)**: only when the rules leave a required field missing, and only with the header text. Any value the LLM returns that is not in the paper is dropped.
5. **UPI**: OCR for screenshots, app templates (`backend/app/extraction/upi/templates/*.yaml`), then generic rules; checks on the UTR, amount and date. A receipt is never treated as proof of payment.

LaTeX files skip steps 1–4: authors, affiliations and emails come straight from the `\author` commands of IEEEtran, acmart, llncs, elsarticle, svjour3, revtex, authblk and plain article.

## Run it locally

Needs Python 3.10–3.12.

```bash
python -m venv .venv
```

```bash
.venv/Scripts/python -m pip install -r requirements-dev.txt
```

```bash
.venv/Scripts/python -m uvicorn app.main:app --app-dir backend --port 8765
```

Open http://localhost:8765. (On macOS/Linux use `.venv/bin/python`.)

Optional LLM: copy `.env.example` to `.env` and set `GEMINI_API_KEY` or `GROQ_API_KEY`. Without a key the site runs on rules only.

Locally everything is stored in a SQLite file, so no database server is needed. "Continue with Google" stays hidden until `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are set (see [Deploy on Render](#deploy-on-render)); guest accounts work without it.

## Tests

```bash
cd backend && ../.venv/Scripts/python -m pytest -q
```

The tests use a fresh SQLite file each. To run them on Postgres as well, point `TEST_DATABASE_URL` at a database the tests may empty (every table is cleared before each test; `DATABASE_URL` is never used by the tests):

```bash
cd backend && TEST_DATABASE_URL=postgresql://postgres:@127.0.0.1:5432/am_test ../.venv/Scripts/python -m pytest -q tests/api
```

No Postgres installed? `pip install pgserver` runs one from a folder, without Docker or an installer.

`backend/tests/make_fixtures.py` builds synthetic samples with known answers (two-column IEEE-style PDF, LNCS-style PDF, a Word manuscript with a title page, three LaTeX classes, PhonePe/Google Pay screenshots, a Paytm PDF). Add real papers and receipts to `backend/tests/fixtures/` with expected values as you collect them.

## Chrome extension: fill forms for you

`extension/` is a Chrome extension that types Abstract Mind's details into the form you have open: conference and journal submission forms (title, abstract, keywords, each author's name, email, organisation, country, ORCID, corresponding author, funding and other statements, counts) and payment forms (UTR, amount, date, time, payer, bank).

**Install** (once):

1. Open `chrome://extensions` and switch on **Developer mode** (top right).
2. Click **Load unpacked** and choose the `extension` folder.
3. Pin **Abstract Mind Form Filler** from the puzzle-piece menu.

**Use**:

1. Open the form's page.
2. Click the Abstract Mind button. Upload the paper or receipt, or pick it from **Your library**. The library includes the corrections you made on the site.
3. Click **Fill this page**, review what it typed, and submit the form yourself.

**Your library in the extension**: sign in to Abstract Mind in the same Chrome profile, open **Your library**, and enter your Abstract Mind password once. Saved papers are encrypted, and the site's key lives in the site's own storage, which an extension can't read; so the extension opens the key itself from your password. The password is checked inside the extension and never sent. The opened key is kept like the site keeps it (in the extension's storage, usable but not readable), until you click **Lock the library in this extension**. If you change your password on the site, the extension asks for the new one. Guest libraries can't be opened in the extension: their key exists only in the site's tab. When the library is unlocked, a file you upload from the extension is also saved to it, encrypted.

The paper you're filling from is kept in Chrome's session storage, so it survives the popup closing but is cleared when Chrome closes.

How it behaves:

- It only touches a page when you click **Fill this page**, and it never presses Submit.
- It never overwrites text you already typed, unless you tick **Replace text already in the form**.
- Everything it typed is outlined: blue for verified values, amber for values to check. **Clear outlines** removes the outlines.
- If the form shows fewer author blocks than the paper has authors, it tells you how many to add. Press Fill again after adding them; filled fields are kept.
- Fields it can't match are listed under **Left for you**, and **All details** has a Copy button for each value.

The extension talks to `http://localhost:8765` by default. Under **Server**, enter your deployed address (e.g. `https://abstract-mind.onrender.com`); `*.onrender.com` is allowed out of the box, and Chrome asks permission once for any other address, such as a custom domain. After updating the extension's files, press **Reload** on it in `chrome://extensions`.

The extension carries exact copies of three of the site's modules: `vault.js` (encryption), `fields.js` and `keystore.js`. After changing any of them in `web/assets/js/lib/`, run `python scripts/sync_extension.py`; `node --test tests/web/vault.test.mjs` fails while a copy is out of date.

**Tests**: serve the project folder (`python -m http.server 8790 --bind 127.0.0.1`), then open `extension-tests/easychair.html`, `modern.html` and `upi.html`. Each fills a form copied from a real layout and shows PASS or FAIL for every field. Refresh `extension-tests/sample-*.json` after changing the extractor.

**Try the popup without Chrome**: with the app running locally, open http://localhost:8765/_dev/extension/. It's the real popup, served by the local server, so uploading, unlocking and the library work against your local account; `extension-tests/chrome-stub.js` stands in for Chrome's extension APIs, so **Fill this page** does nothing there. This page exists only in development: it isn't served when `APP_ENV=production`, and the Docker image doesn't include the extension.

## Deploy on Render

Render's free web service has no disk that survives a restart, so production keeps its data in Postgres.

1. **Database**: create a Postgres database (Neon, Supabase or Render Postgres) and copy its connection URL.
2. **Code**: push this folder to a GitHub repository.
3. **Service**: in Render, **New → Blueprint**, pick the repository. `render.yaml` creates a Docker web service with a health check on `/api/v1/health`, switches on production mode and generates `APP_SECRET`. When asked, fill in:
   - `DATABASE_URL`: the URL from step 1
   - `PUBLIC_ORIGIN`: the service's address, e.g. `https://abstract-mind.onrender.com`
   - `GEMINI_API_KEY` or `GROQ_API_KEY`, if you want the LLM step
4. **Google sign-in**: in Google Cloud Console, **APIs & Services → Credentials → Create credentials → OAuth client ID → Web application**. Add the authorized redirect URI `https://<your address>/api/v1/auth/google/callback` (and `http://localhost:8765/api/v1/auth/google/callback` for local use). Put the client ID and secret in `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`.
5. **Check**: open `/api/v1/health`. It should say `"database": "postgres"` and `"google": true`.

The free plan sleeps when idle, so the first request after a while is slow. OCR needs a few hundred MB of memory; if large scans fail on the free plan, move to a paid instance.

## Accounts and the database

### Where data is stored

| Where it runs | Database | Set by |
|---|---|---|
| Production (Render) | **PostgreSQL** (Neon, Supabase or Render Postgres) | `DATABASE_URL=postgresql://…` |
| Your laptop and the tests | **SQLite**, one file | nothing to set; the file is `data/abstract_mind.db` (or `DB_PATH`) |

Both hold the same tables. They are created automatically the first time the app connects, and upgraded in place when the schema changes. The schema version is kept in the `schema_version` table on Postgres and in `PRAGMA user_version` on SQLite. The current version is **3**. All database code is in `backend/app/db/`.

`GET /api/v1/health` reports `"database": "postgres"` or `"sqlite"`, so you can check which one a deployment is using.

### What is encrypted

A saved paper is encrypted in the browser before it is sent, with the account's **data key**. The data key is itself locked with a key made from the account's password (PBKDF2 → HKDF), and only that locked copy (`wrapped_key`) reaches the server. So the database never holds:

- a password, or any key that can open a library
- an uploaded file (files are read in memory and dropped)
- any readable extraction: titles, authors, abstracts and edits are all ciphertext

What it does hold is in the tables below.

### Tables

```
users ─┬─< sessions        one account, many signed-in browsers
       └─< documents       one account, many saved papers and receipts
```

Deleting a user deletes their sessions and documents (`ON DELETE CASCADE`).

#### `users`: one row per account

| Column | Postgres type | SQLite type | What it holds |
|---|---|---|---|
| `id` | `BIGINT` identity, primary key | `INTEGER` primary key | Account id |
| `email` | `TEXT UNIQUE` | `TEXT UNIQUE` | Lower-cased email; `NULL` for guests |
| `name` | `TEXT NOT NULL` | `TEXT NOT NULL` | Display name (`Guest` for guests) |
| `is_guest` | `INTEGER` 0/1 | `INTEGER` 0/1 | 1 for a guest account |
| `auth_hash` | `BYTEA` | `BLOB` | scrypt hash of the auth key the browser derives from the password |
| `auth_salt` | `BYTEA` | `BLOB` | Salt for that scrypt hash |
| `kdf_salt` | `BYTEA` | `BLOB` | The browser's PBKDF2 salt (not secret) |
| `kdf_iterations` | `INTEGER` | `INTEGER` | PBKDF2 rounds (600,000 by default; 300,000 to 5,000,000 accepted) |
| `wrapped_key` | `TEXT` | `TEXT` | The data key, encrypted in the browser (base64). The server can't open it |
| `google_sub` | `TEXT UNIQUE` | `TEXT UNIQUE` | Google account id; `NULL` unless the person used "Continue with Google" |
| `created_at` | `DOUBLE PRECISION` | `REAL` | Unix time, in seconds |
| `updated_at` | `DOUBLE PRECISION` | `REAL` | Unix time, in seconds |

The same table holds every kind of account:

| Kind of account | `email` | `google_sub` | `auth_hash`, `kdf_*`, `wrapped_key` | `is_guest` |
|---|---|---|---|---|
| Guest | `NULL` | `NULL` | `NULL`; the key lives only in the browser that made it | 1 |
| Google, password not set yet | set | set | `NULL`; the app asks for a password next | 0 |
| Google | set | set | set | 0 |
| Email and password (older accounts) | set | `NULL` | set | 0 |

#### `sessions`: one row per signed-in browser

| Column | Postgres type | SQLite type | What it holds |
|---|---|---|---|
| `token_hash` | `TEXT` primary key | `TEXT` primary key | SHA-256 of the session cookie. The cookie itself is never stored, so a copy of the database can't be used to sign in |
| `user_id` | `BIGINT` → `users.id` | `INTEGER` → `users.id` | Whose session it is |
| `created_at` | `DOUBLE PRECISION` | `REAL` | Unix time, in seconds |
| `expires_at` | `DOUBLE PRECISION` | `REAL` | Unix time; `SESSION_DAYS` (30) after sign-in |

Index: `sessions_user (user_id)`. Expired sessions are deleted at each new sign-in. A guest whose last session ends is deleted with everything it saved.

#### `documents`: one row per saved paper or receipt

| Column | Postgres type | SQLite type | What it holds |
|---|---|---|---|
| `id` | `TEXT` primary key | `TEXT` primary key | Random 16-character id, so ids reveal nothing |
| `user_id` | `BIGINT` → `users.id` | `INTEGER` → `users.id` | Owner |
| `meta` | `TEXT` | `TEXT` | Ciphertext (base64): title, kind, byline and counts, which the library list shows |
| `body` | `TEXT` | `TEXT` | Ciphertext (base64): the full extraction, including your edits |
| `size` | `INTEGER` | `INTEGER` | `len(meta) + len(body)`, for the size limit |
| `starred` | `INTEGER` 0/1 | `INTEGER` 0/1 | Starred in the library |
| `created_at` | `DOUBLE PRECISION` | `REAL` | Unix time, in seconds |
| `updated_at` | `DOUBLE PRECISION` | `REAL` | Unix time, in seconds |

Index: `documents_user (user_id, created_at DESC)`, for the library list.

#### `schema_version` (Postgres only)

| Column | Type | What it holds |
|---|---|---|
| `version` | `INTEGER` | The schema version the database is on (one row) |

### Choosing a Postgres

Any Postgres 13 or newer works. Copy its connection URL into `DATABASE_URL`:

- **Neon** or **Supabase**: free tiers that don't expire. Use the URL they show; pooled URLs are fine, because the app doesn't use server-side prepared statements.
- **Render Postgres**: in the same dashboard. Check Render's pricing page for how long a free database lasts.

Keep `?sslmode=require` on hosted URLs. `DB_POOL_SIZE` (default 5) sets how many connections each app instance keeps open. Data in a local SQLite file isn't copied to Postgres; production starts empty.

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `LLM_PROVIDER` | `auto` | `auto`, `gemini`, `groq` or `none` |
| `GEMINI_API_KEY` | | Google AI Studio key. Use a paid key for unpublished papers: Google may use free-tier prompts to improve its products. |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Check Google's current model list if calls fail |
| `GROQ_API_KEY` | | console.groq.com key |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Check Groq's current model list if calls fail |
| `MAX_UPLOAD_MB` | `20` | Upload size limit |
| `DATABASE_URL` | | Postgres connection URL. Set it in production; when empty, a SQLite file is used |
| `DB_PATH` | `data/abstract_mind.db` | The SQLite file, when `DATABASE_URL` isn't set |
| `DB_POOL_SIZE` | `5` | Postgres connections kept open per app instance |
| `APP_ENV` | `development` | `production` turns on Secure cookies and HSTS, and requires `APP_SECRET` |
| `APP_SECRET` | | Random secret; `render.yaml` generates one |
| `PUBLIC_ORIGIN` | | The site's public address, e.g. `https://abstract-mind.onrender.com`; used for the Google redirect |
| `GOOGLE_CLIENT_ID` | | OAuth client ID for "Continue with Google" |
| `GOOGLE_CLIENT_SECRET` | | Its secret. The Google button is hidden until both are set |
| `SESSION_DAYS` | `30` | How long a sign-in lasts |

## Layout

```
backend/app/
  main.py            FastAPI app: middleware, /api/v1 routes, serves web/
  settings.py        settings from environment variables and .env
  api/routes/        health, auth (email, guest), google (Continue with Google,
                     first password), account, extract, documents
  db/                database.py (Postgres or SQLite, schema, migrations),
                     users, sessions, documents
  security/          middleware (CSP, same-origin, body limits), passwords, rate limits
  extraction/        service.py (file type -> loader -> paper or UPI pipeline)
    core/            Block/Document/Field, confidence, grounding, file sniffing
    ingest/          pdf, ocr, docx, latex, layout (columns, headers, line numbers)
    paper/           zones, header, linking, authors, names, affiliations,
                     declarations, stats, llm_fill, pipeline
    upi/             rows, apps + templates/, matcher, validators, pipeline
    llm/             Gemini and Groq clients behind one interface
    data/            word lists: affiliation words, countries, particles, banks
web/                 index.html, assets/css, assets/js (main.js, pages/, services/,
                     lib/ with vault.js for encryption); no build step
web/practice/        practice forms for the extension
extension/           Chrome extension that fills submission and payment forms
extension-tests/     browser tests for the extension
tests/web/           Node tests for the encryption (vault.js)
```

## Known limits

- Scanned papers lose superscript markers, so affiliations may need linking by hand.
- UPI templates are a starting point: fit their labels to real (blurred) receipts from each app.
- Word page counts come from Word's last save; files made by other tools may report 1.

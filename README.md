# InvoiceFlow — PDF invoice → explainable decision (Zamp PS-1)

An invoice-processing and decision system. Extraction is only stage one; the product is the
**rule-by-rule, explainable APPROVE / HOLD / REJECT decision**. Runs fully offline by default.

## Setup
```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python make_samples.py                                 # generates 21 demo invoices into ./samples
streamlit run app.py                                   # no API key needed
python test_demo.py                                    # optional: checks every sample's decision
```
Optional: install the Tesseract binary (`brew install tesseract` / `apt install tesseract-ocr`) to read scanned PDFs.
Without it a scanned invoice is routed to HOLD with a clear message (never silently dropped).

**Optional Gemini:** `pip install -r requirements-gemini.txt`, set `GEMINI_API_KEY`, and pick *Auto* or
*Gemini only* in the sidebar. In *Auto*, any Gemini failure (bad key, quota, no package) falls back to the offline rules.

**Administrator access:** the Admin tab uses `INVOICEFLOW_ADMIN_USER` and `INVOICEFLOW_ADMIN_PASSWORD` from the environment or Streamlit secrets. The requested local demo credentials are **`admin` / `admin`**. Before making the app public, set a unique username and strong password in the hosting platform's Secrets settings. A public visitor who knows `admin` / `admin` can change invoice statuses and reset demo history. Status changes are recorded using the existing review audit fields.


## Changing the UI colours

The primary brand colour is `#6FA6D8` in both modes. The application opens in Light mode by default; users can switch to Dark in the sidebar. Change the `accent` value under `[Dark]` and `[Light]` in `colours.txt` to change the brand colour throughout the app. The file uses six-digit sRGB HEX values. Edit `colours.txt` to change the appearance without editing Python or CSS. It contains matching
`[Dark]` and `[Light]` palettes. The project uses **semantic CSS design tokens** (for example,
`background`, `text`, `muted`, `accent`, `table_bg`, and `chart_2`) with six-digit **sRGB HEX**
values in `#RRGGBB` format. Keep the section and token names unchanged; change only the values
after `=`. The `accent` token automatically drives the logo, selected tabs, radio and checkbox
indicators, primary controls, table headers, and first chart series. `theme.py` validates the file
and applies the palette to the page, inputs, tables, risk labels, and charts. See `THEME_GUIDE.md`
for the palette reference and table-rendering note.

## Architecture
| Stage | What happens |
|---|---|
| Ingest | PyMuPDF text layer; too little text → rasterise + Tesseract OCR; (optional) Gemini vision |
| Extract | **Pluggable.** `extract_rules.py` (offline, deterministic, label-driven, per-field confidence) or `extract_gemini.py` (optional). Handles invoices *and* credit notes, bank details, ISO-code currencies. Missing = `null`, never guessed |
| Validate | V1 required fields · V2 date (future/stale) · V3 confidence · V4 approved vendor · V5a same file · V5b same invoice # · V6 arithmetic · **V7 bank details changed** · **V8 tax-rate anomaly** · **V9 credit-note reference** |
| Match PO | P1 PO exists/inferred · P2 vendor · P3 open + **FX-converted currency** · P4 cumulative balance + tolerance · P5 possible duplicate · **P6 invoice predates PO** · **L1 line-level price/qty variance** |
| Decide | reject-fail → REJECT; hold-fail → HOLD; else APPROVE. Adds a **risk score**, the **next owner** (Treasury / Buyer / Tax / AP) and, for approvals, the **sign-off tier** by amount |

Humans stay in the loop: HOLDs land in the **Review queue**, where a reviewer approves/rejects with a note. The
system decision is never overwritten (audit trail), and an approval immediately books against the PO.

Assumptions are listed in `ASSUMPTIONS.md` and inside the app (Procurement data tab).

## Edge cases built in
| # | Scenario | Behaviour | Sample |
|---|---|---|---|
| 1 | **Split PO** | cumulative "invoiced so far"; later invoice that over-bills is held | 02 → 03 → 11 |
| 2 | **Missing invoice number** | HOLD (not reject); duplicate check falls back to vendor+PO+amount | 09 |
| 3 | **Amount mismatch** | % tolerance **and** absolute cap (sliders); internal arithmetic checked separately | 04, 05, 10 |
| 4 | **Duplicate** | same bytes under another name (V5a) *and* same normalised invoice # (V5b) | 07, 12 |
| 5 | **Hidden price variance** | total matches PO exactly, but unit prices don't (one up, one down) | 13 |
| 6 | **Changed bank account** | payment-fraud signal → Treasury must call vendor; risk +30 | 14 |
| 7 | **Foreign currency** | EUR invoice converted to the USD PO's currency, approved with FX warning | 15 |
| 8 | **Credit note** | negative amount, must cite an approved invoice, restores PO balance | 16 |
| 9 | **Wrong tax rate** | arithmetic is consistent but 28% ≠ vendor's registered 20% | 17 |
| 10 | **Predates PO / future-dated** | retroactive-PO red flag; keying error / pre-billing | 18, 19 |
| 11 | **Different vendor layout, tax embedded, bundled line** | free-form letter layout, "Inv. #", written date | 20 |
| 12 | **Missing date + unclear total** | HOLD with both reasons (V1, V2) | 21 |
| 13 | **Scanned + no PO** | OCR; PO inferred from vendor+amount, never auto-approved | 06 |

Failed extractions are never counted as "seen", so retrying a file after fixing config is not flagged as a duplicate.

## Demo order (after "Reset run history")  — or use **Batch → Replay all samples**
01, 02, 03, 11, 04, 05, 06, 07, 12, 08, 09, 10, 13–21. (16 needs 04 approved first, as it credits INI-2210.)
See `DEMO_SCRIPT.md` for a timed 5-minute walkthrough.

## Files
`app.py` UI · `theme.py` shared theme layer · `colours.txt` editable palettes · `pipeline.py` stages + rules · `extract_rules.py` offline extractor · `extract_gemini.py` optional LLM ·
`extract_common.py` shared shape · `db.py` SQLite + mock vendors/POs/FX · `make_samples.py` · `test_demo.py` · `DEMO_SCRIPT.md` · `ASSUMPTIONS.md`

## Deploying a shareable link (Streamlit Community Cloud)

The simplest way to get an HTTPS link that can be opened from other devices is Streamlit Community Cloud. It connects to a GitHub repository and assigns the deployed app a `*.streamlit.app` URL.

1. **Create a GitHub account** at https://github.com/ and sign in.
2. **Create a new repository** (for example, `invoiceflow`). Choose Public if anyone should be able to view the code; a private repository can also be connected, subject to Community Cloud's private-app limits.
3. **Extract this ZIP** on your computer. Open the `invoiceflow/` project folder. The repository root must contain `app.py`, `requirements.txt`, `packages.txt`, `colours.txt`, `theme.py`, the other Python modules, and the `samples/` folder.
4. **Upload the project to GitHub.** On the repository page choose **Add file → Upload files**, drag the *contents* of the `invoiceflow/` folder (not the outer folder itself) into the page, commit the files to the `main` branch. Do not upload `.env`, any database file (`*.db`), API keys, or `secrets.toml`. The supplied `.env.example` is safe to keep as a template.
5. **Open Streamlit Community Cloud** at https://share.streamlit.io/ and sign in using GitHub.
6. Click **Create app**. Select your repository, branch `main`, and main file path `app.py`. Optionally choose an easy-to-remember app subdomain such as `invoiceflow-demo`.
7. Open **Advanced settings → Secrets** before deploying. Add unique admin credentials as TOML, for example:

   ```toml
   INVOICEFLOW_ADMIN_USER = "invoice-admin"
   INVOICEFLOW_ADMIN_PASSWORD = "replace-this-with-a-long-unique-password"
   ```

   Do not use `admin` / `admin` on a public deployment. Anyone can open the public URL and those credentials would let them alter records. Never put real secrets in GitHub. Streamlit's deployment settings keep the secrets separate from the repository.
8. Click **Deploy**. Wait for the build log to finish. When the app opens, copy its `https://....streamlit.app` URL from the address bar. Send that URL to anyone who needs access.
9. To update the hosted app later, upload/commit the changed files to GitHub. Community Cloud detects repository changes and redeploys the app.

**Important limitations before using it for real accounts payable:** this project currently uses a local SQLite file (`invoiceflow.db`) and demo vendor/PO data. On a hosted app, SQLite is stored on the app's local container filesystem, which is not a durable shared database and may be lost when the app is rebuilt or its container is replaced. Multiple users also share the same app instance and data. The Community Cloud link is suitable for a demonstration; for reliable business use, connect the app to a persistent external database and implement proper per-user authentication and access controls first.

Official instructions: [Deploy on Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy) · [Manage deployment secrets](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management) · [Share an app](https://docs.streamlit.io/deploy/streamlit-community-cloud/share-your-app).

## Administrator control centre

After signing in on the **Admin** tab, administrators can:

- Allow or block vendors; add new vendors (new vendors default to blocked).
- Create/amend purchase orders and mark them OPEN, CLOSED or CANCELLED.
- Save persistent default matching tolerances for future runs.
- Change the administrator password from the website (stored as a salted PBKDF2-HMAC-SHA256 hash in the application database).
- Change invoice outcomes, review the administrative audit log, export that log, and clear demo history with explicit confirmation.

Vendor permission changes are applied by the existing V4 approved-vendor validation on the next invoice run. PO status changes are applied by the existing P3 open-PO validation. Saved processing tolerances are defaults for future runs; historical decisions are not recalculated automatically.

**Deployment note:** the default local demo login is `admin` / `admin`. Change it immediately after first login. The website password change is stored in SQLite, so use persistent database storage for hosted deployments if you need the new password and audit records to survive app restarts. Do not use the demo login or local SQLite storage for real financial operations.
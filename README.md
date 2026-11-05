# WorxDB

A self-hosted, browser-based database workspace inspired by Microsoft Works Database, with a classic interface based on the supplied Works screenshots. Docker runs the app and MariaDB together. This is an initial implementation, not a complete Works clone.

## Included

- Multiple named databases, each stored as a real typed MariaDB table.
- Supported Microsoft Works `.wdb` conversion through libwps `wks2csv`, plus CSV/TSV imports.
- Two-step import: review headings, sample records, row counts and field types before committing.
- Original uploads preserved in a persistent volume with SHA-256 provenance recorded on the database.
- Text, number, currency, date and yes/no fields. Text is the default for imports to preserve leading zeroes and original values.
- Record tables, record editing forms, search, filters, numeric/date sorting and pagination.
- Arithmetic calculated fields using earlier field IDs, e.g. `f2 * f3`.
- Saved reports with selected columns, grouping, counts, numeric subtotals, grand totals, optional filters, summary view and landscape printing.
- Browser printing / Save as PDF and CSV export.
- Password-protected workspace, CSRF checks and record revision checks to prevent overwriting another editor's changes.

## Install with Docker Compose

On your Docker VM:

```bash
git clone https://github.com/bl1tzkr13g/WorxDB.git
cd WorxDB
cp .env.example .env
nano .env
docker compose up -d --build
```

Because the repository is private, cloning requires your GitHub account's existing authentication. Set all four password/secret values in `.env` to distinct random values. A session secret can be generated with `openssl rand -hex 32`. The app password is the password you use in the browser.

Visit **http://YOUR-DOCKER-SERVER-IP:8080**. Sign in as `admin` (or your `APP_USER`) with `APP_PASSWORD`. For access outside a trusted local network, put it behind an HTTPS reverse proxy. MariaDB is only available on the internal Compose network.

Compose creates persistent `database` and `imports` volumes. `docker compose down` preserves them; **`docker compose down -v` deletes them**.

For Portainer, use the dedicated [Stack installer](PORTAINER.md). It deploys the repository directly, builds the app automatically, and opens WorxDB on port **8097** by default.

## Import a Works database

1. Keep your original file and make a backup.
2. Choose **Import from Works**, select `.wdb`, `.csv` or `.tsv`, and review the conversion.
3. Confirm that the first row contains column names. If it does not, export a CSV from Works including headings and use that file.
4. Give the database a name. Keep account numbers, phone numbers and ZIP codes as **text**. Choose numeric/date types only when all records use the expected format.
5. Select **Import into MariaDB**. Invalid values stop the whole import; no records are silently skipped.
6. Compare field values and the total record count against Works. Rebuild saved report layouts under **Reports**.

Dates must be ISO `YYYY-MM-DD`. Numbers use a decimal point and no grouping separators or currency symbols. Currency stores two decimal places; number stores six. Blank imported fields become NULL. Wholly blank rows are skipped. Headers are required and must be unique. Limits: 20 MB uploads, 40 MB converted output, 100,000 records, 80 fields.

### WDB compatibility and report migration

libwps documents database support for Works **v1–v2000**, and says it may retrieve the main database contents but **not filters, frames or reports**. Later Works versions are not guaranteed. Source: https://sourceforge.net/p/libwps/wiki/Home/#recognized-formats

Conversion runs on your own server. If the converter rejects your file, open it in Microsoft Works and export CSV. CSV imports do not preserve Works calculated formulas or layout definitions. WorxDB arithmetic fields and reports must be recreated. Keep source formulas and reports separately for comparison. A newly created synthetic `.wdb` containing invented records can help test compatibility. Field definitions and blank or synthetic report examples are enough to guide the build; do not upload the live database. See [the privacy-safe handoff guide](PRIVACY-SAFE-HANDOFF.md).

## Current limits

- One shared administrator account; no individual users, roles or audit trail yet.
- Existing field names can be renamed. Adding/deleting fields or changing their SQL types requires export/reimport. Form Design supports ordering and showing/hiding fields in a two-column layout; free-positioned forms, relationships and joins are not implemented.
- Reports can be created, renamed, duplicated, deleted and printed. Editing an existing report layout is not yet exposed; create a new definition to change the layout.
- Formulas support basic arithmetic only, not the full Works formula language. They are computed on read, not stored as generated MariaDB columns.
- Report layout is a tabular/grouped template. Exact Works layouts, mailing labels, mail merge, embedded images, charts, scripts and macros are not implemented.
- Search, filtering and sorting currently load the selected database into app memory. This version targets small Works-sized datasets, not large SQL administration workloads.
- CSV export prefixes potentially executable spreadsheet strings with an apostrophe for safer opening in Excel/Calc. Use a MariaDB dump for a faithful database backup.
- Failed/abandoned import uploads remain in the imports volume. Manage retention on the host; there is no upload cleanup UI yet.
- No general-purpose SQL console or management of arbitrary existing MariaDB schemas. WorxDB manages databases created/imported through its workspace.

## Backups and updates

Back up both the MariaDB database and original uploads. This produces a dump without exposing the password in your terminal command:

```bash
docker compose exec -T db sh -c 'exec mariadb-dump -u root -p"$MARIADB_ROOT_PASSWORD" --single-transaction worxdb' > worxdb-backup.sql
```

Also back up the Compose imports volume with your normal Docker volume backup system. Keep `.env` securely. Test restoring backups before relying on them.

To update:

```bash
git pull --ff-only
docker compose up -d --build
```

## Verification

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -v
node --check static/app.js
node --check static/classic.js
```

The unit suite runs against SQLite and covers record operations, imports, validation, typed sorting/filtering, formulas, concurrency checks, report rendering and escaping, authentication and CSRF. WDB unit tests mock the converter; they do **not** prove real-file compatibility.

GitHub Actions also builds the Docker image and exercises record operations, calculations, reports and exports against **real MariaDB** using `scripts/docker_smoke.py`. This is separate from validating your actual WDB file. See the Actions run for the current Docker integration result.

This project is independent software and is not affiliated with Microsoft.


## Classic Works-style interface

The screenshot-based desktop shell includes **File, Edit, View, Record, Format, Tools and Help** menus, a compact icon toolbar, font/size selectors, cell value/formula bar and record status bar.

| Area | Working commands |
| --- | --- |
| File | New, Open/import, Close, Save settings, Save As CSV, Page Setup, Print Preview, Print |
| Edit | Grid/batch Undo, cell Cut/Copy/Paste/Clear, visual selection, Find, Replace, Go To, Fill Right/Down/Series |
| View | List, Form, Form Design, Report, toolbar/task pane/gridline visibility, headers/footers, zoom |
| Record | Insert/delete records, sort, mark/unmark, show marked/unmarked, hide records, filter |
| Format | Rename field, display format, alignment, font/style, borders, shading, workspace edit protection, record height, field width |
| Tools | Filters, ReportCreator, rename/delete/duplicate report, Options |

**Unavailable commands remain visible and disabled with tooltips:** Send/email, Insert/Delete Field, Split, manual page breaks, Spelling, Mail Merge, automatic field defaults and Serialized formatting. This is not full Works feature parity.

Display formats include General, Text, Number, Currency (USD), Percent, Exponential, Leading zeros, Fraction and True/False. Date/Time display uses the stored value; locale-specific date/time masks are not implemented. Formatting never changes SQL field types. Settings persist per database and are shared between users of the single workspace account. Workspace field protection is an editing preference, not authorization; it does not prevent API access.

**Selection and batch scope:** clicking a cell selects it; its raw value appears in the value bar. Press Enter or click the checkmark to save. Calculated fields show their formula and are read-only. Double-click a cell to open the record form. Check record boxes before using Replace, Fill Down or Fill Series. These operations affect marked records **on the currently loaded page** only. Fill Right targets later editable fields in the selected record, with confirmation. Edit → Undo reverses the last grid/batch change in this browser session; it does not undo record insertion/deletion, modal form saves, formatting, or schema renames.

Marks and hidden records are persistent workspace view settings, and do not constrain CSV exports or saved reports. Use server-side search/filter rules for those. List print preview prints the visible current page; use Reports for full database printing. Browser printing can override page settings. Browser/system keyboard shortcuts may reserve Ctrl+N, Ctrl+O and similar combinations; menus remain available. Clipboard integration may require HTTPS; the internal clipboard supports copying/pasting within WorxDB.

No personal record contents, source filenames or field-value text from screenshots have been included in the interface or sample databases.

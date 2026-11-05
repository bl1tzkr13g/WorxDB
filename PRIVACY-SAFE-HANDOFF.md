# What to share to match your Works database

Do not upload your live database, its backups, or a copy made by deleting records. Deleting records does not establish that the binary file contains no recoverable personal information.

## 1. Works version

Provide the Microsoft Works version number (typed text is enough). This determines which menus and file features apply.

## 2. Field definitions only

Prefer a manually written list or screenshots tightly cropped to the field-definition dialog, with all record data and identifying window titles excluded. Include:

| Field name | Field type | Length / decimals | Required? | Default | Formula |
| --- | --- | --- | --- | --- | --- |
| Customer ID | Text | 12 | Yes | Blank | None |
| Hours | Number | 2 decimals | No | 0 | None |
| Rate | Currency | 2 decimals | No | Blank | None |
| Amount | Calculated | Currency | No | None | Hours * Rate |

Replace any personal information in field labels, defaults, formulas, file names or paths with generic placeholders. CSV headers alone are useful but do not describe field types, formulas, validation or reports. If obtaining a header-only file, create a NEW text file and type only the column names; do not send a data export that you have not checked.

## 3. Each report's design

Provide its generic title, columns in order, sorting, filtering rules, grouping, subtotals/grand totals and any formulas. Also note paper size, portrait/landscape, margins, header/footer, labels and page numbering. A blank layout sketch or typed description is sufficient.

If a visual example is useful, create a completely NEW database from scratch with the same structure and only invented records, then recreate one report there and print it to PDF. Do not copy real rows into it. Review the PDF's visible content, document properties and filename before sharing. Do not rely on black rectangles or cropping as secure PDF redaction.

If Works offers a report design/settings view, a tightly cropped screenshot of only the settings can be sufficient. Exclude record previews, personal names in filter values, window titles, paths, account details and identifying printer information.

## 4. Record-entry form layout

Share a blank sketch or list showing field order, sections, calculated/display-only fields, dropdown choices and any rules. No populated record view is needed.

## 5. Data size (optional)

Approximate record count and file size, without records, help set import and performance limits.

Start with the Works version, field definitions and ONE representative report. The real-data conversion should be run locally on your own Docker server. Exact validation of a particular WDB file can remain local; share only non-sensitive error text and aggregate counts if troubleshooting is needed.

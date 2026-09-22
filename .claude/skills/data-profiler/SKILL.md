---
name: data-profiler
description: Profile a CSV, TSV or Excel file and write a Markdown data-quality report - columns, row count, data type per column, empty cells per column, and duplicate rows. Use when asked to profile, inspect, summarise, sanity-check, QA or "look at" a data file, check for missing values, blanks, nulls, duplicate rows, or column types, or before analysing a new dataset.
---

# data-profiler

Profiles a CSV/TSV or Excel file and writes a Markdown report covering: column
list, row count, inferred data type per column, empty cells per column, and
duplicate rows — plus a Flags section for the problems worth acting on.

The whole skill is one script: `.claude/skills/data-profiler/profile_data.py`,
committed to this repo so it ships with a clone.
**Python standard library only** — no pandas, no openpyxl, nothing to install.
Excel files are read by unzipping the `.xlsx` OOXML parts directly.

All paths below are relative to the repo root - run them from there.

## Run it

```bash
python .claude/skills/data-profiler/profile_data.py data/wvs-synthetic.csv
```

Writes `data/wvs-synthetic-profile.md` next to the input and prints a one-line
summary:

```
Wrote data/wvs-synthetic-profile.md - 9,329 rows x 15 columns, 885 empty cells, 0 duplicate rows.
```

Common variations, all verified:

```bash
python .claude/skills/data-profiler/profile_data.py data/file.csv -o reports/profile.md
python .claude/skills/data-profiler/profile_data.py data/file.csv --stdout
python .claude/skills/data-profiler/profile_data.py book.xlsx --list-sheets
python .claude/skills/data-profiler/profile_data.py book.xlsx --sheet Regions
python .claude/skills/data-profiler/profile_data.py data/file.csv --stdout --json
```

Other flags: `--delimiter ';'` and `--encoding cp1252` override the sniffing,
`--max-examples N` (default 3) sets example values per column, `--top N`
(default 5) sizes the "Most common values" tables.

**Read the report after generating it** and summarise the Flags section for the
user — that is where the duplicate rows, half-empty columns and null-like
tokens are called out. Don't just announce the file was written.

## What the report contains

| Section | Contents |
|---|---|
| Overview | Source, file size, sheet/encoding/delimiter, row count, column count, total and empty cells, duplicate rows |
| Flags | Duplicate rows, blank rows, ragged rows, repeated column names, empty columns, ≥50%-empty columns, null-like tokens, single-value columns |
| Columns | Per column: position, name, inferred type, empty count and %, distinct count, min/max, mean, example values |
| Type notes | Columns where the type is mixed (e.g. "62.5% of values parse as numbers") |
| Most common values | Top-N value/count table per column |
| Duplicate rows | Count, how many rows would remain after dedupe, and the most-repeated rows |

Inferred types: `integer`, `float`, `boolean`, `date`, `text`, `empty`.
Min/Max means the numeric range for numbers, the date range for dates, and the
**string-length** range for text.

## Smoke test

No data file handy? Generate a deliberately messy 2-sheet workbook (empty
cells, a triplicated row, real Excel date serials, an all-empty column, `NA`
tokens) and profile it:

```bash
python .claude/skills/data-profiler/make_sample_xlsx.py /tmp/sample.xlsx
python .claude/skills/data-profiler/profile_data.py /tmp/sample.xlsx --stdout
```

Expected: 9 rows × 7 columns, 13 empty cells, 2 duplicate rows, `ordered_on`
typed as `date`, `paid` as `boolean`, `notes` as `empty`.

## Gotchas

- **`.xls` (Excel 97–2003) is not supported.** It is a binary format, not a zip
  of XML. The script exits with a message telling you to re-save as `.xlsx`.
  `.xlsx` and `.xlsm` both work.
- **Empty means empty.** A cell containing `NA`, `null`, `-`, `NaN` or `?` is a
  *value*, not a blank — it is counted in the column's distinct values and
  reported separately in Flags as "Null-like text". This is deliberate: silently
  folding them into the empty count hides a real data-quality problem. Nothing
  is auto-converted.
- **Excel omits trailing empty cells**, so a short `<row>` in the XML is normal
  and is *not* flagged as ragged. Ragged-row flagging applies to CSV only,
  where a short row really does mean a malformed file.
- **Excel dates are serial numbers**, not strings. The script reads
  `xl/styles.xml`, works out which style indices carry a date number format,
  and converts those cells from the 1899-12-30 epoch. A date column in a
  workbook with unusual custom formats may come through as a bare number like
  `45324` — if you see that, the number format wasn't recognised as a date.
- **A UTF-8 BOM would otherwise corrupt the first column name.**
  `data/wvs-synthetic.csv` starts with one; reading as `utf-8-sig` (the first
  encoding tried) strips it. Without that, column 1 profiles as `ï»¿country`.
- **Encoding is guessed**: `utf-8-sig` → `cp1252` → `latin-1`, first one that
  decodes wins, and the choice is recorded in the report's Overview. `latin-1`
  never fails, so a badly-encoded file yields mojibake rather than an error —
  check the Overview line. Use `--encoding` to force it.
- **The delimiter is sniffed** from the first 64 KB over `, ; \t |`. Sniffing a
  single-column file falls back to `,` (harmless). Use `--delimiter` if a file
  with commas inside quoted fields gets misread.
- **Whole file is held in memory.** Fine for the ~945 KB / 9,329-row dataset
  here (sub-second); a multi-GB file will not fit.
- **The first non-blank row is the header.** Files with title/banner rows above
  the real header will profile the banner as column names — delete those rows
  first.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'pandas'` | You are running something else. This script imports nothing outside the stdlib. |
| `No sheet named 'X'. Available: Orders, Regions` | Sheet names are case- and space-sensitive; copy one from `--list-sheets`. |
| `UnicodeEncodeError` printing the report | Already handled — stdout is reconfigured to UTF-8 at startup. If you pipe the report through another script, give that one `encoding="utf-8"` too. |
| `<file> is empty.` / `Sheet 'X' ... is empty.` | The file or sheet has no non-blank rows. |
| First column named `ï»¿something` | You forced `--encoding utf-8` on a BOM file. Drop the flag or use `utf-8-sig`. |
| Numbers profiled as `text` with a "mixed" type note | Real: some cells are non-numeric (stray `NA`, units, thousands separators). The type note gives the percentage that do parse. |

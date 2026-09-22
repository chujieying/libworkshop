#!/usr/bin/env python3
"""Profile a CSV or Excel file and write a Markdown report.

Standard library only - no pandas, no openpyxl. Reads .csv/.tsv/.txt with the
`csv` module and .xlsx/.xlsm by unzipping the OOXML parts directly.

    python profile_data.py data/file.csv
    python profile_data.py book.xlsx --sheet Sheet2 -o report.md
    python profile_data.py book.xlsx --list-sheets
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import sys
import zipfile
from collections import Counter
from xml.etree import ElementTree as ET

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
NS_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

NULL_LIKE = {"na", "n/a", "null", "nan", "none", "nil", "-", "--", "#n/a", "?"}

INT_RE = re.compile(r"^[+-]?\d{1,18}$")
FLOAT_RE = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")
BOOL_VALUES = {"true", "false", "yes", "no", "y", "n", "t", "f"}
DATE_FORMATS = (
    "%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%d %b %Y",
    "%d %B %Y", "%b %d, %Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M",
)


# --------------------------------------------------------------------------
# Readers
# --------------------------------------------------------------------------

def read_csv(path, delimiter=None, encoding=None):
    """Return (header, rows, meta). Tries utf-8-sig then cp1252 then latin-1."""
    encodings = [encoding] if encoding else ["utf-8-sig", "cp1252", "latin-1"]
    last_err = None
    for enc in encodings:
        try:
            with open(path, "r", encoding=enc, newline="") as fh:
                sample = fh.read(64 * 1024)
                fh.seek(0)
                delim = delimiter
                if not delim:
                    try:
                        delim = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
                    except csv.Error:
                        delim = "\t" if path.lower().endswith((".tsv", ".tab")) else ","
                reader = csv.reader(fh, delimiter=delim)
                rows = [r for r in reader]
            break
        except UnicodeDecodeError as exc:
            last_err = exc
            continue
    else:
        raise SystemExit("Could not decode {}: {}".format(path, last_err))

    if not rows:
        raise SystemExit("{} is empty.".format(path))
    header = [c.strip() for c in rows[0]]
    body = rows[1:]
    meta = {"encoding": enc, "delimiter": delim}
    return header, body, meta


def _col_index(ref):
    """'BC12' -> 54 (0-based column index)."""
    n = 0
    for ch in ref:
        if ch.isalpha():
            n = n * 26 + (ord(ch.upper()) - 64)
        else:
            break
    return n - 1


def _excel_serial_to_iso(value, is_datetime):
    try:
        num = float(value)
    except ValueError:
        return value
    base = dt.datetime(1899, 12, 30)
    stamp = base + dt.timedelta(days=num)
    if is_datetime and (num % 1):
        return stamp.strftime("%Y-%m-%d %H:%M:%S")
    return stamp.strftime("%Y-%m-%d")


def _date_style_ids(zf):
    """Return set of style indices whose number format is a date/time format."""
    date_ids = set()
    try:
        styles = ET.fromstring(zf.read("xl/styles.xml"))
    except KeyError:
        return date_ids
    builtin_dates = set(range(14, 23)) | set(range(45, 48)) | {27, 30, 36, 50, 57}
    custom = {}
    for numfmt in styles.iter(NS + "numFmt"):
        code = numfmt.get("formatCode", "")
        stripped = re.sub(r'\[[^\]]*\]|"[^"]*"', "", code)
        if re.search(r"[ymdhs]", stripped, re.IGNORECASE):
            custom[int(numfmt.get("numFmtId"))] = True
    cell_xfs = styles.find(NS + "cellXfs")
    if cell_xfs is None:
        return date_ids
    for idx, xf in enumerate(cell_xfs.findall(NS + "xf")):
        fmt_id = int(xf.get("numFmtId", 0))
        if fmt_id in builtin_dates or custom.get(fmt_id):
            date_ids.add(idx)
    return date_ids


def list_sheets(path):
    with zipfile.ZipFile(path) as zf:
        wb = ET.fromstring(zf.read("xl/workbook.xml"))
        return [s.get("name") for s in wb.iter(NS + "sheet")]


def read_xlsx(path, sheet=None):
    with zipfile.ZipFile(path) as zf:
        wb = ET.fromstring(zf.read("xl/workbook.xml"))
        sheets = [(s.get("name"), s.get(NS_REL + "id")) for s in wb.iter(NS + "sheet")]
        if not sheets:
            raise SystemExit("{} has no worksheets.".format(path))
        rels = {}
        try:
            rel_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
            for rel in rel_root:
                rels[rel.get("Id")] = rel.get("Target")
        except KeyError:
            pass

        if sheet is None:
            name, rid = sheets[0]
        else:
            match = [s for s in sheets if s[0] == sheet]
            if not match:
                raise SystemExit(
                    "No sheet named {!r}. Available: {}".format(
                        sheet, ", ".join(s[0] for s in sheets)
                    )
                )
            name, rid = match[0]

        target = rels.get(rid, "worksheets/sheet1.xml")
        target = target[1:] if target.startswith("/") else "xl/" + target.lstrip("/")
        if target not in zf.namelist():
            candidates = [n for n in zf.namelist() if n.startswith("xl/worksheets/sheet")]
            target = sorted(candidates)[0]

        shared = []
        if "xl/sharedStrings.xml" in zf.namelist():
            sst = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in sst.iter(NS + "si"):
                shared.append("".join(t.text or "" for t in si.iter(NS + "t")))

        date_styles = _date_style_ids(zf)
        rows = []
        ws = ET.fromstring(zf.read(target))
        for row in ws.iter(NS + "row"):
            cells = {}
            for cell in row.findall(NS + "c"):
                ref = cell.get("r") or ""
                idx = _col_index(ref) if ref else len(cells)
                ctype = cell.get("t", "n")
                style = cell.get("s")
                if ctype == "inlineStr":
                    is_el = cell.find(NS + "is")
                    value = (
                        "".join(t.text or "" for t in is_el.iter(NS + "t"))
                        if is_el is not None else ""
                    )
                else:
                    v_el = cell.find(NS + "v")
                    value = v_el.text if v_el is not None and v_el.text is not None else ""
                    if ctype == "s" and value != "":
                        value = shared[int(value)]
                    elif ctype == "b":
                        value = "TRUE" if value == "1" else "FALSE"
                    elif ctype == "n" and value != "" and style is not None:
                        if int(style) in date_styles:
                            value = _excel_serial_to_iso(value, is_datetime=True)
                cells[idx] = value
            width = max(cells) + 1 if cells else 0
            rows.append([cells.get(i, "") for i in range(width)])

    while rows and not any(str(c).strip() for c in rows[0]):
        rows.pop(0)
    if not rows:
        raise SystemExit("Sheet {!r} in {} is empty.".format(name, path))
    header = [str(c).strip() for c in rows[0]]
    return header, rows[1:], {"sheet": name, "sheets": [s[0] for s in sheets]}


# --------------------------------------------------------------------------
# Profiling
# --------------------------------------------------------------------------

def is_empty(value):
    return value is None or str(value).strip() == ""


def parse_date(value):
    for fmt in DATE_FORMATS:
        try:
            return dt.datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def infer_type(values):
    """values: list of non-empty stripped strings. Returns (type, detail)."""
    if not values:
        return "empty", "no non-empty values"
    lowered = [v.lower() for v in values]
    if all(INT_RE.match(v) for v in values):
        return "integer", ""
    if all(FLOAT_RE.match(v) for v in values):
        return "float", ""
    if all(v in BOOL_VALUES for v in lowered):
        return "boolean", ""
    if all(parse_date(v) for v in values):
        return "date", ""
    numeric = sum(1 for v in values if FLOAT_RE.match(v))
    if numeric:
        pct = 100.0 * numeric / len(values)
        return "text", "mixed - {:.1f}% of values parse as numbers".format(pct)
    return "text", ""


def profile(header, rows, max_examples=3, top_n=5, flag_ragged=True):
    # Normalise ragged rows to the header width, and flag the ragged ones.
    # Excel legitimately omits trailing empty cells, so only CSV rows are flagged.
    width = len(header)
    ragged = sum(1 for r in rows if len(r) != width) if flag_ragged else 0
    norm = [(list(r) + [""] * width)[:width] for r in rows]

    # Drop trailing fully-empty rows (common in Excel exports).
    while norm and all(is_empty(c) for c in norm[-1]):
        norm.pop()
    blank_rows = sum(1 for r in norm if all(is_empty(c) for c in r))

    columns = []
    for i, name in enumerate(header):
        raw = [r[i] for r in norm]
        stripped = [str(v).strip() for v in raw]
        non_empty = [v for v in stripped if v != ""]
        empty_n = len(stripped) - len(non_empty)
        null_like = sum(1 for v in non_empty if v.lower() in NULL_LIKE)
        ctype, detail = infer_type(non_empty)
        counts = Counter(non_empty)
        col = {
            "position": i + 1,
            "name": name or "(unnamed column {})".format(i + 1),
            "type": ctype,
            "type_detail": detail,
            "empty": empty_n,
            "empty_pct": (100.0 * empty_n / len(stripped)) if stripped else 0.0,
            "null_like": null_like,
            "distinct": len(counts),
            "examples": [v for v, _ in counts.most_common(max_examples)],
            "top_values": counts.most_common(top_n),
        }
        if ctype in ("integer", "float"):
            nums = [float(v) for v in non_empty]
            col["min"] = min(nums)
            col["max"] = max(nums)
            col["mean"] = sum(nums) / len(nums)
        elif ctype == "date":
            dates = sorted(parse_date(v) for v in non_empty)
            col["min"] = dates[0].strftime("%Y-%m-%d")
            col["max"] = dates[-1].strftime("%Y-%m-%d")
        elif ctype == "text" and non_empty:
            lengths = [len(v) for v in non_empty]
            col["min"] = "{} chars".format(min(lengths))
            col["max"] = "{} chars".format(max(lengths))
        columns.append(col)

    seen = Counter(tuple(str(c).strip() for c in r) for r in norm)
    dup_groups = [(row, n) for row, n in seen.items() if n > 1]
    dup_groups.sort(key=lambda x: -x[1])
    dup_extra = sum(n - 1 for _, n in dup_groups)

    dup_headers = [c for c in header if header.count(c) > 1]

    return {
        "row_count": len(norm),
        "column_count": width,
        "columns": columns,
        "blank_rows": blank_rows,
        "ragged_rows": ragged,
        "duplicate_rows": dup_extra,
        "duplicate_groups": len(dup_groups),
        "duplicate_examples": [
            {"count": n, "row": list(row)} for row, n in dup_groups[:max_examples]
        ],
        "duplicate_header_names": sorted(set(dup_headers)),
        "total_cells": len(norm) * width,
        "total_empty": sum(c["empty"] for c in columns),
    }


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

def md_escape(value):
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def format_number(value):
    """Readable numbers: no scientific notation for IDs, no float noise."""
    if value == int(value) and abs(value) < 1e15:
        return "{:,}".format(int(value))
    if abs(value) >= 1e6:
        return "{:,.2f}".format(value)
    if abs(value) >= 1e-4:
        return "{:,.6g}".format(value)
    return "{:.3e}".format(value)


def truncate(value, limit=40):
    text = md_escape(value)
    return text if len(text) <= limit else text[: limit - 1] + "\u2026"


def render(prof, source, meta):
    size = os.path.getsize(source)
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    out = []
    a = out.append

    a("# Data profile \u2014 `{}`".format(os.path.basename(source)))
    a("")
    a("*Generated {} by the `data-profiler` skill.*".format(stamp))
    a("")
    a("## Overview")
    a("")
    a("| | |")
    a("|---|---|")
    a("| Source | `{}` |".format(md_escape(source)))
    a("| File size | {:,} bytes |".format(size))
    for key in ("sheet", "encoding", "delimiter"):
        if key in meta:
            shown = repr(meta[key]) if key == "delimiter" else meta[key]
            a("| {} | `{}` |".format(key.capitalize(), md_escape(shown)))
    if meta.get("sheets") and len(meta["sheets"]) > 1:
        a("| Other sheets | {} |".format(md_escape(", ".join(meta["sheets"]))))
    a("| Rows (excluding header) | {:,} |".format(prof["row_count"]))
    a("| Columns | {:,} |".format(prof["column_count"]))
    a("| Total cells | {:,} |".format(prof["total_cells"]))
    pct = 100.0 * prof["total_empty"] / prof["total_cells"] if prof["total_cells"] else 0.0
    a("| Empty cells | {:,} ({:.2f}%) |".format(prof["total_empty"], pct))
    a("| Duplicate rows | {:,} |".format(prof["duplicate_rows"]))
    a("")

    flags = []
    if prof["duplicate_rows"]:
        flags.append(
            "{:,} duplicate row(s) across {:,} repeated value combination(s).".format(
                prof["duplicate_rows"], prof["duplicate_groups"]
            )
        )
    if prof["blank_rows"]:
        flags.append("{:,} completely blank row(s).".format(prof["blank_rows"]))
    if prof["ragged_rows"]:
        flags.append(
            "{:,} row(s) did not have exactly {} fields "
            "(padded/truncated for this profile).".format(
                prof["ragged_rows"], prof["column_count"]
            )
        )
    if prof["duplicate_header_names"]:
        flags.append("Repeated column names: " + ", ".join(prof["duplicate_header_names"]) + ".")
    empty_cols = [c["name"] for c in prof["columns"] if c["type"] == "empty"]
    if empty_cols:
        flags.append("Entirely empty column(s): " + ", ".join(empty_cols) + ".")
    high_null = [c["name"] for c in prof["columns"] if c["empty_pct"] >= 50 and c["type"] != "empty"]
    if high_null:
        flags.append("Columns at least half empty: " + ", ".join(high_null) + ".")
    null_tok = ["{} ({})".format(c["name"], c["null_like"]) for c in prof["columns"] if c["null_like"]]
    if null_tok:
        flags.append(
            "Null-like text (NA/null/-/\u2026) counted as a value, not as empty: "
            + ", ".join(null_tok) + "."
        )
    const = [c["name"] for c in prof["columns"] if c["distinct"] == 1]
    if const:
        flags.append("Single-value column(s): " + ", ".join(const) + ".")

    a("## Flags")
    a("")
    if flags:
        for f in flags:
            a("- " + f)
    else:
        a("- Nothing unusual found: no duplicate rows, blank rows, or empty columns.")
    a("")

    a("## Columns")
    a("")
    a("| # | Column | Type | Empty | Empty % | Distinct | Min | Max | Mean | Example values |")
    a("|---:|---|---|---:|---:|---:|---|---|---|---|")
    for c in prof["columns"]:
        def fmt(key):
            v = c.get(key)
            if v is None or v == "":
                return "\u2014"
            if isinstance(v, float):
                return format_number(v)
            return md_escape(v)
        examples = ", ".join("`{}`".format(truncate(v, 24)) for v in c["examples"]) or "\u2014"
        a(
            "| {} | `{}` | {} | {:,} | {:.1f}% | {:,} | {} | {} | {} | {} |".format(
                c["position"], md_escape(c["name"]), c["type"], c["empty"],
                c["empty_pct"], c["distinct"], fmt("min"), fmt("max"),
                fmt("mean"), examples,
            )
        )
    a("")
    a("Min/Max is the numeric range for number columns, the date range for date "
      "columns, and the string-length range for text columns.")
    a("")

    detailed = [c for c in prof["columns"] if c["type_detail"]]
    if detailed:
        a("### Type notes")
        a("")
        for c in detailed:
            a("- `{}` \u2014 {}".format(md_escape(c["name"]), c["type_detail"]))
        a("")

    a("## Most common values")
    a("")
    for c in prof["columns"]:
        if not c["top_values"]:
            continue
        a("**`{}`** ({:,} distinct)".format(md_escape(c["name"]), c["distinct"]))
        a("")
        a("| Value | Count |")
        a("|---|---:|")
        for value, count in c["top_values"]:
            a("| `{}` | {:,} |".format(truncate(value), count))
        a("")

    a("## Duplicate rows")
    a("")
    if not prof["duplicate_rows"]:
        a("No duplicate rows: every row is a unique combination of values.")
    else:
        a(
            "{:,} row(s) are repeats of an earlier row ({:,} distinct value "
            "combination(s) occur more than once). Removing the repeats would "
            "leave {:,} rows.".format(
                prof["duplicate_rows"], prof["duplicate_groups"],
                prof["row_count"] - prof["duplicate_rows"],
            )
        )
        a("")
        a("Most repeated combinations:")
        a("")
        a("| Occurrences | Row |")
        a("|---:|---|")
        for ex in prof["duplicate_examples"]:
            cells = ", ".join(truncate(v, 18) for v in ex["row"][:8])
            more = " \u2026" if len(ex["row"]) > 8 else ""
            a("| {:,} | `{}{}` |".format(ex["count"], cells, more))
    a("")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Profile a CSV or Excel file into a Markdown report."
    )
    ap.add_argument("input", help="Path to a .csv/.tsv or .xlsx/.xlsm file")
    ap.add_argument("-o", "--output",
                    help="Report path (default: <input>-profile.md next to the input)")
    ap.add_argument("--sheet", help="Worksheet name (Excel only; default: first sheet)")
    ap.add_argument("--list-sheets", action="store_true", help="Print worksheet names and exit")
    ap.add_argument("--delimiter", help="Force a CSV delimiter instead of sniffing")
    ap.add_argument("--encoding",
                    help="Force a CSV encoding instead of trying utf-8-sig/cp1252/latin-1")
    ap.add_argument("--max-examples", type=int, default=3,
                    help="Example values per column (default 3)")
    ap.add_argument("--top", type=int, default=5,
                    help="Rows in each 'most common values' table (default 5)")
    ap.add_argument("--json", action="store_true", help="Also print the profile as JSON on stdout")
    ap.add_argument("--stdout", action="store_true", help="Print the report instead of writing a file")
    args = ap.parse_args(argv)

    # The report uses em-dashes and ellipses; a cp1252 Windows console would
    # otherwise raise UnicodeEncodeError on --stdout / --list-sheets.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    path = args.input
    if not os.path.exists(path):
        raise SystemExit("No such file: {}".format(path))
    ext = os.path.splitext(path)[1].lower()

    if ext == ".xls":
        raise SystemExit(
            ".xls (Excel 97-2003) is not supported. Re-save it as .xlsx and try again."
        )
    if args.list_sheets:
        if ext not in (".xlsx", ".xlsm"):
            raise SystemExit("--list-sheets only applies to .xlsx/.xlsm files.")
        for name in list_sheets(path):
            print(name)
        return 0

    if ext in (".xlsx", ".xlsm"):
        header, rows, meta = read_xlsx(path, args.sheet)
        flag_ragged = False
    else:
        header, rows, meta = read_csv(path, args.delimiter, args.encoding)
        flag_ragged = True

    prof = profile(header, rows, max_examples=args.max_examples, top_n=args.top,
                   flag_ragged=flag_ragged)
    report = render(prof, path, meta)

    if args.stdout:
        print(report)
    else:
        out = args.output or os.path.splitext(path)[0] + "-profile.md"
        parent = os.path.dirname(os.path.abspath(out))
        os.makedirs(parent, exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(report)
        print(
            "Wrote {} - {:,} rows x {} columns, {:,} empty cells, "
            "{:,} duplicate rows.".format(
                out, prof["row_count"], prof["column_count"],
                prof["total_empty"], prof["duplicate_rows"],
            )
        )
    if args.json:
        print(json.dumps(prof, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())

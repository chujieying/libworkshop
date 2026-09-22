#!/usr/bin/env python3
"""Write a small .xlsx smoke-test fixture using only the standard library.

Deliberately messy so the profiler has something to find: two sheets, empty
cells, a duplicated row, a date column, a boolean column, an all-empty column,
a null-like "NA" token, and a numeric column stored as text.

    python make_sample_xlsx.py out.xlsx
"""

import sys
import zipfile
from xml.sax.saxutils import escape

ROWS = [
    ["order_id", "customer", "ordered_on", "amount", "paid", "notes", "region"],
    ["1001", "Acme Ltd", "2024-01-15", "250.50", "TRUE", "", "APAC"],
    ["1002", "Globex", "2024-01-16", "99.00", "FALSE", "", "EMEA"],
    ["1003", "Initech", "2024-02-01", "", "TRUE", "", "APAC"],
    ["1004", "Acme Ltd", "2024-02-03", "1200.00", "TRUE", "", "NA"],
    ["1004", "Acme Ltd", "2024-02-03", "1200.00", "TRUE", "", "NA"],
    ["1005", "Umbrella", "", "45.25", "FALSE", "", ""],
    ["1006", "Globex", "2024-03-11", "310.75", "TRUE", "", "EMEA"],
    ["1007", "Initech", "2024-03-12", "310.75", "", "", "AMER"],
    ["1004", "Acme Ltd", "2024-02-03", "1200.00", "TRUE", "", "NA"],
]

SHEET2 = [
    ["region", "manager"],
    ["APAC", "Lim"],
    ["EMEA", "Novak"],
    ["AMER", "Reyes"],
]

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>"""

ROOT_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""

WORKBOOK = """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets>
<sheet name="Orders" sheetId="1" r:id="rId1"/>
<sheet name="Regions" sheetId="2" r:id="rId2"/>
</sheets>
</workbook>"""

WORKBOOK_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

# cellXfs index 1 uses numFmtId 14 (m/d/yyyy) so the date column is a real
# Excel date serial, which is what the profiler has to decode.
STYLES = """<?xml version="1.0" encoding="UTF-8"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>
<fills count="1"><fill><patternFill patternType="none"/></fill></fills>
<borders count="1"><border/></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="2">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="14" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
</cellXfs>
</styleSheet>"""


def col_letter(idx):
    letters = ""
    idx += 1
    while idx:
        idx, rem = divmod(idx - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def date_serial(text):
    import datetime as dt
    day = dt.datetime.strptime(text, "%Y-%m-%d")
    return (day - dt.datetime(1899, 12, 30)).days


def sheet_xml(rows, date_col=None):
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
           "<sheetData>"]
    for r, row in enumerate(rows, start=1):
        out.append('<row r="{}">'.format(r))
        for c, value in enumerate(row):
            if value == "":
                continue  # a skipped cell IS an empty cell in xlsx
            ref = "{}{}".format(col_letter(c), r)
            if r > 1 and c == date_col:
                out.append('<c r="{}" s="1"><v>{}</v></c>'.format(ref, date_serial(value)))
            elif r > 1 and value in ("TRUE", "FALSE"):
                out.append('<c r="{}" t="b"><v>{}</v></c>'.format(ref, 1 if value == "TRUE" else 0))
            else:
                # inline strings keep the fixture free of a sharedStrings part
                out.append(
                    '<c r="{}" t="inlineStr"><is><t>{}</t></is></c>'.format(ref, escape(value))
                )
        out.append("</row>")
    out.append("</sheetData></worksheet>")
    return "".join(out)


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "sample.xlsx"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", CONTENT_TYPES)
        zf.writestr("_rels/.rels", ROOT_RELS)
        zf.writestr("xl/workbook.xml", WORKBOOK)
        zf.writestr("xl/_rels/workbook.xml.rels", WORKBOOK_RELS)
        zf.writestr("xl/styles.xml", STYLES)
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml(ROWS, date_col=2))
        zf.writestr("xl/worksheets/sheet2.xml", sheet_xml(SHEET2))
    print("Wrote {} ({} rows on 'Orders', {} on 'Regions')".format(
        out, len(ROWS) - 1, len(SHEET2) - 1))


if __name__ == "__main__":
    main()

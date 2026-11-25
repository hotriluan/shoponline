"""Format fingerprints for the two return-document templates.

The fingerprints record *how* a file looks (fonts, borders, merged cells, row heights, page setup),
never *what* it says, so a baseline can be committed without any customer data. Excel files are
read straight from the OOXML parts, not through ``openpyxl``: the writer used to fill the template
is the same library, and it would not notice what it drops.
"""

from __future__ import annotations

import copy
import hashlib
import io
import re
import zipfile
from pathlib import Path

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS = {"w": W, "s": S}
_RELS_ATTR = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def _q(tag: str) -> str:
    prefix, name = tag.split(":")
    return f"{{{NS[prefix]}}}{name}"


def _canon(el: etree._Element) -> str:
    """Short digest of an element: tag, sorted attributes and children sorted by their own digest.

    Namespace declarations and writer ordering do not matter; rsid attributes record editing
    sessions, not formatting, so they are left out too.
    """

    def text(node: etree._Element) -> str:
        attrs = sorted(
            (etree.QName(k).localname, v) for k, v in node.attrib.items() if "rsid" not in k.lower()
        )
        kids = sorted(text(c) for c in node if isinstance(c.tag, str))
        return f"<{etree.QName(node).localname} {attrs}>{''.join(kids)}</>"

    return hashlib.sha1(text(el).encode()).hexdigest()[:12]


def _read_zip(source: bytes | str | Path) -> zipfile.ZipFile:
    if isinstance(source, bytes):
        return zipfile.ZipFile(io.BytesIO(source))
    return zipfile.ZipFile(source)


# --------------------------------------------------------------------------- Word

_RUN_NOISE = {_q("w:color"), _q("w:lang"), _q("w:noProof")}
_CONTENT = {_q("w:t"), _q("w:tab"), _q("w:br"), _q("w:sym"), _q("w:drawing"), _q("w:pict")}


def _clean_rpr(rpr: etree._Element | None) -> str:
    if rpr is None:
        return ""
    rpr = copy.deepcopy(rpr)
    for child in list(rpr):
        if child.tag in _RUN_NOISE:
            rpr.remove(child)
    for fonts in rpr.iter(_q("w:rFonts")):
        fonts.attrib.pop(_q("w:hint"), None)
    return _canon(rpr)


def _paragraph_print(p: etree._Element) -> dict:
    ppr = p.find(_q("w:pPr"))
    ppr_text = ""
    if ppr is not None:
        ppr = copy.deepcopy(ppr)
        mark = ppr.find(_q("w:rPr"))
        if mark is not None:
            clean = _clean_rpr(mark)
            ppr.remove(mark)
        else:
            clean = ""
        ppr_text = _canon(ppr) + "|mark:" + clean
    segments: list[str] = []
    for r in p.iter(_q("w:r")):
        if not any(c.tag in _CONTENT for c in r):
            continue
        sig = _clean_rpr(r.find(_q("w:rPr")))
        if not segments or segments[-1] != sig:
            segments.append(sig)
    return {"ppr": ppr_text, "runs": segments}


def _table_print(tbl: etree._Element) -> dict:
    rows = []
    for tr in tbl.findall(_q("w:tr")):
        cells = []
        for tc in tr.findall(_q("w:tc")):
            tcpr = tc.find(_q("w:tcPr"))
            cells.append(
                {
                    "tcpr": _canon(tcpr) if tcpr is not None else "",
                    "paragraphs": [_paragraph_print(p) for p in tc.findall(_q("w:p"))],
                }
            )
        trpr = tr.find(_q("w:trPr"))
        rows.append({"trpr": _canon(trpr) if trpr is not None else "", "cells": cells})
    tblpr = tbl.find(_q("w:tblPr"))
    grid = tbl.find(_q("w:tblGrid"))
    return {
        "tblpr": _canon(tblpr) if tblpr is not None else "",
        "grid": _canon(grid) if grid is not None else "",
        "rows": rows,
    }


def docx_format(source: bytes | str | Path) -> dict:
    with _read_zip(source) as z:
        root = etree.fromstring(z.read("word/document.xml"))
        parts = z.namelist()
    body = root.find(_q("w:body"))
    blocks: list[dict] = []
    sect = ""
    for child in body:
        if child.tag == _q("w:p"):
            blocks.append({"p": _paragraph_print(child)})
        elif child.tag == _q("w:tbl"):
            blocks.append({"tbl": _table_print(child)})
        elif child.tag == _q("w:sectPr"):
            sect = _canon(child)
    return {
        "blocks": blocks,
        "sect": sect,
        "drawings": len(list(root.iter(_q("w:drawing")))) + len(list(root.iter(_q("w:pict")))),
        "media_parts": len([p for p in parts if p.startswith("word/media/")]),
    }


def docx_expected(baseline: dict, *, before_extra: int = 0, after_extra: int = 0) -> dict:
    """The baseline with the two item tables' data row repeated, as the generator does."""
    expected = copy.deepcopy(baseline)
    tables = [b["tbl"] for b in expected["blocks"] if "tbl" in b]
    for tbl, extra in zip(tables, (before_extra, after_extra), strict=False):
        data_row = tbl["rows"][1]
        for _ in range(extra):
            tbl["rows"].insert(1, copy.deepcopy(data_row))
    return expected


def compare_docx(expected: dict, actual: dict) -> list[str]:
    diffs: list[str] = []
    if len(expected["blocks"]) != len(actual["blocks"]):
        return [f"block count {len(expected['blocks'])} != {len(actual['blocks'])}"]
    for i, (e, a) in enumerate(zip(expected["blocks"], actual["blocks"], strict=True)):
        if e.keys() != a.keys():
            diffs.append(f"block {i}: kind {list(e)} != {list(a)}")
        elif "p" in e:
            diffs += _diff_paragraph(f"block {i}", e["p"], a["p"])
        else:
            diffs += _diff_table(f"block {i}", e["tbl"], a["tbl"])
    for key in ("sect", "drawings", "media_parts"):
        if expected[key] != actual[key]:
            diffs.append(f"{key} differs")
    return diffs


def _diff_paragraph(where: str, e: dict, a: dict) -> list[str]:
    diffs = []
    if e["ppr"] != a["ppr"]:
        diffs.append(f"{where}: paragraph properties differ")
    if e["runs"] != a["runs"]:
        diffs.append(f"{where}: run formats differ ({len(e['runs'])} vs {len(a['runs'])} segments)")
    return diffs


def _diff_table(where: str, e: dict, a: dict) -> list[str]:
    diffs = []
    for key in ("tblpr", "grid"):
        if e[key] != a[key]:
            diffs.append(f"{where}: table {key} differs")
    if len(e["rows"]) != len(a["rows"]):
        return diffs + [f"{where}: row count {len(e['rows'])} != {len(a['rows'])}"]
    for ri, (er, ar) in enumerate(zip(e["rows"], a["rows"], strict=True)):
        if er["trpr"] != ar["trpr"]:
            diffs.append(f"{where} row {ri}: row properties differ")
        if len(er["cells"]) != len(ar["cells"]):
            diffs.append(f"{where} row {ri}: cell count differs")
            continue
        for ci, (ec, ac) in enumerate(zip(er["cells"], ar["cells"], strict=True)):
            here = f"{where} row {ri} cell {ci}"
            if ec["tcpr"] != ac["tcpr"]:
                diffs.append(f"{here}: cell properties differ")
            if len(ec["paragraphs"]) != len(ac["paragraphs"]):
                diffs.append(f"{here}: paragraph count differs")
                continue
            for pi, (ep, ap) in enumerate(zip(ec["paragraphs"], ac["paragraphs"], strict=True)):
                diffs += _diff_paragraph(f"{here} p{pi}", ep, ap)
    return diffs


# -------------------------------------------------------------------------- Excel

_FORBIDDEN_PARTS = ("xl/drawings/", "xl/media/", "xl/embeddings/")


def _style_table(z: zipfile.ZipFile) -> list[str]:
    """Resolve every cellXfs entry to the canonical text of what it points at."""
    root = etree.fromstring(z.read("xl/styles.xml"))

    def children(tag: str) -> list[etree._Element]:
        node = root.find(f"s:{tag}", NS)
        return list(node) if node is not None else []

    fonts = children("fonts")
    fills = children("fills")
    borders = children("borders")
    num_fmts = {
        int(n.get("numFmtId")): n.get("formatCode")
        for n in (root.find("s:numFmts", NS) if root.find("s:numFmts", NS) is not None else [])
    }
    result = []
    for xf in children("cellXfs"):
        font = _canon(fonts[int(xf.get("fontId", 0))])
        fill = _canon(fills[int(xf.get("fillId", 0))])
        border = _canon(borders[int(xf.get("borderId", 0))])
        fmt_id = int(xf.get("numFmtId", 0))
        fmt = num_fmts.get(fmt_id, str(fmt_id))
        align = xf.find("s:alignment", NS)
        prot = xf.find("s:protection", NS)
        joined = "|".join(
            [
                font,
                fill,
                border,
                fmt,
                _canon(align) if align is not None else "",
                _canon(prot) if prot is not None else "",
            ]
        )
        result.append(hashlib.sha1(joined.encode()).hexdigest()[:12])
    return result


def xlsx_format(source: bytes | str | Path) -> dict:
    with _read_zip(source) as z:
        names = z.namelist()
        styles = _style_table(z)
        sheets = sorted(n for n in names if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n))
        workbook = etree.fromstring(z.read("xl/workbook.xml"))
        sheet = etree.fromstring(z.read(sheets[0]))
    sheet_names = [s.get("name") for s in workbook.iterfind(".//s:sheet", NS)]
    defined = sorted(
        [d.get("name"), d.text] for d in workbook.iterfind(".//s:definedName", NS)
    )
    rows: dict[int, dict] = {}
    for row in sheet.iterfind(".//s:sheetData/s:row", NS):
        cells = {}
        for c in row.iterfind("s:c", NS):
            ref = c.get("r")
            col = re.match(r"[A-Z]+", ref).group(0)
            cells[col] = styles[int(c.get("s", 0))]
        attrs = {
            k: row.get(k)
            for k in ("ht", "customHeight", "hidden", "outlineLevel")
            if row.get(k) is not None
        }
        rows[int(row.get("r"))] = {"attrs": attrs, "cells": cells}

    def one(path: str) -> str:
        el = sheet.find(path, NS)
        if el is None:
            return ""
        el = copy.deepcopy(el)
        el.attrib.pop(_RELS_ATTR, None)
        return _canon(el)

    return {
        "sheet_names": sheet_names,
        "defined_names": defined,
        "cols": one("s:cols"),
        "sheet_pr": one("s:sheetPr"),
        "format_pr": one("s:sheetFormatPr"),
        "margins": one("s:pageMargins"),
        "page_setup": one("s:pageSetup"),
        "print_options": one("s:printOptions"),
        "header_footer": one("s:headerFooter"),
        "protection": one("s:sheetProtection"),
        "merges": sorted(m.get("ref") for m in sheet.iterfind(".//s:mergeCell", NS)),
        "rows": {str(k): v for k, v in rows.items()},
        "forbidden_parts": [n for n in names if n.startswith(_FORBIDDEN_PARTS) or "vml" in n],
        "has_drawing_tag": sheet.find("s:drawing", NS) is not None
        or sheet.find("s:legacyDrawing", NS) is not None,
    }


def _shift_ref(ref: str, first_data_row: int, extra: int) -> str:
    def shift(match: re.Match) -> str:
        row = int(match.group(2))
        return f"{match.group(1)}{row + extra if row > first_data_row else row}"

    return re.sub(r"([A-Z]+)(\d+)", shift, ref)


def xlsx_expected(baseline: dict, *, data_row: int = 14, extra_rows: int = 0) -> dict:
    """The baseline with the item row repeated ``extra_rows`` times and the rest pushed down."""
    expected = copy.deepcopy(baseline)
    if not extra_rows:
        return expected
    rows = {int(k): v for k, v in expected["rows"].items()}
    shifted: dict[int, dict] = {}
    for number, row in rows.items():
        if number <= data_row:
            shifted[number] = row
        else:
            shifted[number + extra_rows] = row
    for k in range(1, extra_rows + 1):
        shifted[data_row + k] = copy.deepcopy(rows[data_row])
    expected["rows"] = {str(k): shifted[k] for k in sorted(shifted)}
    merges = []
    for ref in expected["merges"]:
        merges.append(_shift_ref(ref, data_row, extra_rows))
        first_row = int(re.search(r"\d+", ref).group(0))
        if first_row == data_row:
            for k in range(1, extra_rows + 1):
                merges.append(re.sub(r"\d+", str(data_row + k), ref))
    expected["merges"] = sorted(merges)
    expected["defined_names"] = [
        [name, _shift_ref(text, data_row, extra_rows)] for name, text in expected["defined_names"]
    ]
    return expected


def compare_xlsx(expected: dict, actual: dict) -> list[str]:
    diffs: list[str] = []
    for key in (
        "sheet_names",
        "defined_names",
        "cols",
        "sheet_pr",
        "format_pr",
        "margins",
        "page_setup",
        "print_options",
        "header_footer",
        "protection",
        "merges",
    ):
        if expected[key] != actual[key]:
            diffs.append(f"{key} differs: {expected[key]!r} != {actual[key]!r}")
    if actual["forbidden_parts"] or actual["has_drawing_tag"]:
        diffs.append(f"drawing parts present: {actual['forbidden_parts']}")
    if expected["rows"].keys() != actual["rows"].keys():
        diffs.append("row set differs")
        return diffs
    for number, e_row in expected["rows"].items():
        a_row = actual["rows"][number]
        if e_row["attrs"] != a_row["attrs"]:
            diffs.append(f"row {number}: attributes differ {e_row['attrs']} != {a_row['attrs']}")
        if e_row["cells"].keys() != a_row["cells"].keys():
            diffs.append(f"row {number}: cell set differs")
            continue
        for col, style in e_row["cells"].items():
            if style != a_row["cells"][col]:
                diffs.append(f"row {number} {col}: cell style differs")
    return diffs

"""The two committed templates keep the sample forms' look and carry no customer data."""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

import pytest

from tests.support.format_compare import (
    compare_docx,
    compare_xlsx,
    docx_format,
    xlsx_format,
)

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "src" / "shoponline" / "exports" / "templates"
DOCX = TEMPLATES / "invoice_adjustment.docx"
XLSX = TEMPLATES / "return_request.xlsx"
BASELINE = json.loads(
    (Path(__file__).resolve().parents[1] / "support" / "template_baseline.json").read_text("utf-8")
)
SAMPLES = ROOT / "docs" / "bbdchd"


def _all_parts(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as z:
        return {name: z.read(name) for name in z.namelist()}


def test_docx_template_has_the_sample_format():
    assert compare_docx(BASELINE["docx"], docx_format(DOCX)) == []


def test_xlsx_template_has_the_sample_format():
    assert compare_xlsx(BASELINE["xlsx"], xlsx_format(XLSX)) == []


def test_compare_tools_notice_a_format_change():
    data = DOCX.read_bytes()
    with zipfile.ZipFile(DOCX) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    changed = xml.replace('<w:sz w:val="24"/>', '<w:sz w:val="26"/>', 1)
    assert changed != xml, "fixture has no 24 half-point run to alter"
    import io

    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as zin, zipfile.ZipFile(buffer, "w") as zout:
        for item in zin.infolist():
            payload = zin.read(item.filename)
            if item.filename == "word/document.xml":
                payload = changed.encode("utf-8")
            zout.writestr(item, payload)
    assert compare_docx(BASELINE["docx"], docx_format(buffer.getvalue()))

    broken = json.loads(json.dumps(BASELINE["xlsx"]))
    broken["merges"].pop()
    assert compare_xlsx(broken, xlsx_format(XLSX))


@pytest.mark.parametrize("path", [DOCX, XLSX])
def test_template_has_no_hidden_parts_or_authors(path):
    parts = _all_parts(path)
    assert not [n for n in parts if "thumbnail" in n.lower()]
    assert not [n for n in parts if n.startswith(("xl/drawings", "xl/media", "word/media"))]
    assert not [n for n in parts if "vml" in n.lower() or "printerSettings" in n]
    core = parts["docProps/core.xml"].decode("utf-8")
    for tag in ("creator", "lastModifiedBy"):
        match = re.search(rf"<(?:dc|cp):{tag}>(.*?)</", core)
        assert not match or match.group(1).strip() in ("", "python-docx", "openpyxl")
    if "docProps/app.xml" in parts:
        app = parts["docProps/app.xml"].decode("utf-8")
        assert not re.search(r"<(Company|Manager)>[^<]+<", app)


def test_templates_have_no_red_text():
    document = _all_parts(DOCX)["word/document.xml"].decode("utf-8").upper()
    assert "FF0000" not in document
    styles = _all_parts(XLSX)["xl/styles.xml"].decode("utf-8").upper()
    assert 'RGB="FFFF0000"' not in styles


def test_docx_template_keeps_each_placeholder_in_a_single_run():
    from docx import Document

    doc = Document(str(DOCX))
    paragraphs = list(doc.paragraphs)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                paragraphs.extend(cell.paragraphs)
    texts = [run.text for p in paragraphs for run in p.runs]
    opened = sum(t.count("{{") for t in texts)
    closed = sum(t.count("}}") for t in texts)
    whole = sum(len(re.findall(r"\{\{[^{}]+\}\}", t)) for t in texts)
    assert opened == closed == whole > 0


@pytest.mark.skipif(not SAMPLES.exists(), reason="docs/bbdchd (customer samples) not present")
def test_templates_hold_no_text_from_the_real_samples():
    from docx import Document

    secrets: set[str] = set()
    for sample in SAMPLES.glob("BBDC_*.docx"):
        doc = Document(str(sample))
        pars = list(doc.paragraphs)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    pars.extend(cell.paragraphs)
        for p in pars:
            red = "".join(
                r.text
                for r in p.runs
                if r._r.rPr is not None
                and r._r.rPr.color is not None
                and str(r._r.rPr.color.val) == "FF0000"
            ).strip()
            if len(red) >= 5 and not red.replace(".", "").replace("-", "").isdigit():
                secrets.add(red)
    assert secrets, "no red sample fields found to check against"
    for path in (DOCX, XLSX):
        for name, payload in _all_parts(path).items():
            text = payload.decode("utf-8", errors="ignore")
            for secret in secrets:
                assert secret not in text, f"{path.name}:{name} still holds a sample field"

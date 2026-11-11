"""render.py `.mmd` path: Pele renders offline without a browser, and a diagram
Pele rejects falls back to an SRI-pinned Mermaid page with the source escaped.

These run in the kit CI lane, which has node but no Playwright, so every case
either avoids the browser or proves it is never imported.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent
RENDER = SCRIPTS / "render.py"

VALID = "flowchart LR\n  A[Mermaid text] --> B[SVG]\n"
# Pele has no `notadiagram` type; the label tries to break out of the <pre>.
REJECTED = "notadiagram </pre><script>alert(1)</script>\n"


def _block_playwright(tmp_path: Path) -> dict[str, str]:
    """Environment where importing playwright fails loudly."""
    shim = tmp_path / "shim" / "playwright"
    shim.mkdir(parents=True)
    (shim / "__init__.py").write_text("raise ImportError('playwright must not be imported')\n")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(shim.parent)
    return env


def _render(tmp_path: Path, source: str, *flags: str, env: dict[str, str] | None = None):
    src = tmp_path / "diagram.mmd"
    src.write_text(source, encoding="utf-8")
    out = tmp_path / "out"
    proc = subprocess.run(
        [sys.executable, str(RENDER), "--input", str(src), "--out", str(out), *flags],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    return proc, out


def test_pele_writes_html_and_svg_without_a_browser(tmp_path):
    proc, out = _render(tmp_path, VALID, "--no-png", env=_block_playwright(tmp_path))
    assert proc.returncode == 0, proc.stderr

    html = (out / "diagram.html").read_text(encoding="utf-8")
    assert 'class="pele pele-flowchart"' in html
    assert "<script" not in html
    assert "--pele-bg: var(--ak-diag-paper)" in html

    svg = (out / "diagram.svg").read_text(encoding="utf-8")
    assert svg.startswith("<svg ") and 'class="pele pele-flowchart"' in svg
    assert "ak-diagram:" not in proc.stderr


def test_rejected_diagram_falls_back_to_pinned_mermaid(tmp_path):
    proc, out = _render(tmp_path, REJECTED, "--dry-run")
    assert proc.returncode == 0, proc.stderr
    assert "diagram.mmd" in proc.stderr
    assert "unsupported-diagram at line 0" in proc.stderr
    assert "falling back to Mermaid 11.4.1" in proc.stderr

    html = (out / "diagram.html").read_text(encoding="utf-8")
    assert "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/" in html
    assert 'integrity="sha384-rbtjAdnIQE/aQJGEgXrVUlMibdfTSa4PQju4HDhN3sR2PmaKFzhEafuePsl9H/9I"' in html
    assert 'crossorigin="anonymous"' in html
    assert "&lt;/pre&gt;&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)" not in html


def test_rejected_diagram_without_png_or_svg_skips_the_browser(tmp_path):
    proc, out = _render(
        tmp_path, REJECTED, "--no-png", "--no-svg", env=_block_playwright(tmp_path)
    )
    assert proc.returncode == 0, proc.stderr
    assert (out / "diagram.html").exists()
    assert not (out / "diagram.svg").exists()


def test_missing_node_falls_back_instead_of_crashing(tmp_path):
    env = dict(os.environ)
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    env["PATH"] = str(empty_bin)
    proc, out = _render(tmp_path, VALID, "--dry-run", env=env)
    assert proc.returncode == 0, proc.stderr
    assert "node not found" in proc.stderr
    assert "mermaid@11.4.1" in (out / "diagram.html").read_text(encoding="utf-8")


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("outcome", "reason"),
    [
        (subprocess.CompletedProcess([], 2, "", "render-mermaid: cannot load assets/pele.mjs: gone\n"),
         "Pele bridge failed: render-mermaid: cannot load assets/pele.mjs: gone"),
        (subprocess.CompletedProcess([], 0, "not json", ""), "Pele bridge printed invalid JSON"),
        (subprocess.TimeoutExpired(["node"], 60), "Pele bridge timed out after 60s"),
        (subprocess.CompletedProcess([], 0, '{"ok": false, "error": {"code": "x"}}', ""), "x: "),
    ],
)
def test_bridge_failures_become_fallback_reasons(monkeypatch, outcome, reason):
    render = _load("render")

    def fake_run(*_args, **_kwargs):
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(render.shutil, "which", lambda _name: "/usr/bin/node")
    monkeypatch.setattr(render.subprocess, "run", fake_run)
    assert render._render_with_pele(Path("diagram.mmd")) == (None, reason)


class _FakeTimeout(Exception):
    pass


class _FakePage:
    """Records the fallback loader's waits; `stall` names the wait that times out."""

    def __init__(self, stall: str | None = None, mermaid_err: str | None = None):
        self.stall = stall
        self.mermaid_err = mermaid_err
        self.calls: list[str] = []

    def _step(self, name: str):
        self.calls.append(name)
        if name == self.stall:
            raise _FakeTimeout(name)

    def goto(self, _url, timeout):
        self._step("goto")

    def wait_for_load_state(self, _state, timeout):
        self._step("networkidle")

    def wait_for_function(self, _expr, timeout):
        self._step("rendered")

    def evaluate(self, _expr):
        return self.mermaid_err


def test_fallback_page_hanging_cdn_is_captured_with_a_warning(capsys):
    page = _FakePage(stall="goto")
    _load("render")._load_fallback_page(page, "file:///x.html", _FakeTimeout)
    assert page.calls == ["goto"]
    assert "still loading after 15s" in capsys.readouterr().err


def test_fallback_page_slow_mermaid_render_warns(capsys):
    page = _FakePage(stall="rendered")
    _load("render")._load_fallback_page(page, "file:///x.html", _FakeTimeout)
    assert page.calls == ["goto", "networkidle", "rendered"]
    assert "did not finish rendering" in capsys.readouterr().err


def test_fallback_page_reports_mermaid_errors(capsys):
    page = _FakePage(mermaid_err="Parse error on line 1")
    _load("render")._load_fallback_page(page, "file:///x.html", _FakeTimeout)
    assert "could not render the diagram either: Parse error on line 1" in capsys.readouterr().err


def test_vendor_metadata_rewrite_keeps_extra_vendors(tmp_path, monkeypatch):
    vendor = _load("vendor_from_upstream")

    metadata = tmp_path / "vendoring-metadata.yaml"
    extra = (
        "# Additional MIT vendors not managed by vendor_from_upstream.py:\n"
        "extra_vendors:\n"
        "  - asset: assets/pele.mjs\n"
        "    version: \"1.6.0\"\n"
    )
    metadata.write_text("upstream_repo: old\n\n" + extra + "\ntemplates:\n  - type: old\n", encoding="utf-8")
    monkeypatch.setattr(vendor, "METADATA_FILE", metadata)

    vendor._write_metadata(
        [{"type": "loop", "variant": "light", "source": "s.html", "target": "t.html", "sha256_12": "abc"}],
        "deadbeef",
        {},
    )

    text = metadata.read_text(encoding="utf-8")
    assert extra in text
    assert "upstream_sha: deadbeef" in text
    assert "type: loop" in text and "type: old" not in text

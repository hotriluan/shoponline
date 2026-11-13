"""zrsd001 and zrsd004 reads against the fake SAP GUI, using the repo's screen and popup config."""

import shutil
from pathlib import Path

import pytest

from shoponline.cli import REPO_ROOT
from shoponline.sapjobs import queue
from shoponline.saprobot.errors import NoReportData, RobotError
from shoponline.saprobot.guard import GuardedSession
from shoponline.saprobot.popups import load_rules
from shoponline.saprobot.screen import Screens
from shoponline.saprobot.transactions import read_zrsd001, read_zrsd004
from shoponline.saprobot.worker import TRANSACTIONS, JobContext
from tests.saprobot.fake_sap import FakeSession, Info

SCREENS = Screens.load(REPO_ROOT / "config" / "sap_screens.yaml")
POPUPS = load_rules(REPO_ROOT / "config" / "sap_popups.yaml")
GRID = "wnd[0]/usr/cntlGRID1/shellcont/shell/shellcont[1]/shell"
EXECUTE = "wnd[0]/tbar[1]/btn[8]"
ZRSD001_PAYLOAD = {
    "batch_id": 1,
    "platform": "SHOPEE",
    "sold_to": "1200001145",
    "date_from": "2026-11-12",
    "date_to": "2026-11-12",
    "selection": "complete",
}
ZRSD004_PAYLOAD = {"platform": "SHOPEE", "sold_to": "1200001145", "gi_date": "2026-11-12"}


class FakeSave:
    def __init__(self, target: Path, source: Path | None, error: str | None):
        self.target, self.source, self.error = target, source, error
        self.cancelled = False

    def wait(self) -> Path:
        if self.error:
            raise RobotError(self.error)
        if self.source is not None:
            shutil.copyfile(self.source, self.target)
        return self.target

    def cancel(self) -> None:
        self.cancelled = True


class FakeDesktop:
    """Stands in for the Save As / SAP GUI Security / Excel windows: 'saves' a prepared file."""

    def __init__(self, source: Path | None = None, error: str | None = None):
        self.source, self.error = source, error
        self.saves: list[FakeSave] = []

    def start_save(self, target: Path) -> FakeSave:
        self.saves.append(FakeSave(target, self.source, self.error))
        return self.saves[-1]


def _sap(no_data: bool = False, ask_format: bool = True) -> FakeSession:
    raw = FakeSession(Info("AEP", "300", "AL17016"))

    def on_vkey(key: int) -> None:  # Enter in the command field opens the typed report
        raw.Info.Transaction = raw.text_of("wnd[0]/tbar[0]/okcd")[2:].upper()

    def on_press(element_id: str) -> None:
        if element_id.startswith("wnd[1]/"):
            raw.windows.pop()
        elif element_id == EXECUTE and no_data:
            raw.status.MessageType, raw.status.Text = "S", "No data to display"

    def on_menu_item(item: str) -> None:
        if ask_format:
            raw.popup("Select Spreadsheet")

    raw.on_vkey, raw.on_press, raw.on_menu_item = on_vkey, on_press, on_menu_item
    return raw


def _ctx(raw: FakeSession, payload: dict, tmp_path, desktop: FakeDesktop) -> JobContext:
    return JobContext(
        job_id=7,
        payload=payload,
        gui=GuardedSession(raw),
        screens=SCREENS,
        popups=POPUPS,
        work_dir=tmp_path,
        desktop=desktop,
    )


def _export(tmp_path) -> Path:
    path = tmp_path / "prepared.xlsx"
    path.write_bytes(b"PK fake xlsx")
    return path


def _filled(raw: FakeSession, screen: str) -> dict[str, str]:
    return {
        name: raw.text_of(element_id)
        for name, element_id in SCREENS.elements[screen].items()
        if element_id in raw.elements and raw.text_of(element_id)
    }


def test_both_reads_are_registered_as_read_only():
    assert set(TRANSACTIONS) == {queue.READ_ZRSD001, queue.READ_ZRSD004}
    assert not any(t.writes for t in TRANSACTIONS.values())


def test_zrsd001_complete_fills_the_filter_and_exports_the_result(tmp_path):
    raw, desktop = _sap(), FakeDesktop(_export(tmp_path))
    out = read_zrsd001.run(_ctx(raw, ZRSD001_PAYLOAD, tmp_path, desktop))

    assert out.file == tmp_path / "zrsd001-job-7.xlsx" and out.file.read_bytes() == b"PK fake xlsx"
    assert raw.Info.Transaction == "ZRSD001"
    assert _filled(raw, "zrsd001") == {
        "sales_office": "1401",
        "doc_date": "12.11.2026",
        "sold_to": "1200001145",
    }
    assert raw.actions[-6:] == [
        ("select", "wnd[0]/usr/radP_RAD2"),
        ("press", EXECUTE),
        ("cell", GRID, 0, "BSTNK"),
        ("menu", GRID),
        ("menu_item", GRID, "&XXL"),
        ("press", "wnd[1]/tbar[0]/btn[0]"),  # "Select Spreadsheet" answered from config
    ]
    assert [s.target for s in desktop.saves] == [out.file] and desktop.saves[0].cancelled


def test_zrsd001_open_keeps_the_default_radio_button(tmp_path):
    raw = _sap(ask_format=False)  # "Always Use Selected Format" ticked: no format dialog
    payload = {**ZRSD001_PAYLOAD, "selection": "open"}
    read_zrsd001.run(_ctx(raw, payload, tmp_path, FakeDesktop(_export(tmp_path))))
    assert not any(action[0] == "select" for action in raw.actions)
    assert raw.actions[-1] == ("menu_item", GRID, "&XXL")


def test_zrsd001_open_refuses_a_filter_screen_left_on_complete(tmp_path):
    raw = _sap()
    raw.findById("wnd[0]/usr/radP_RAD2").selected = True
    payload = {**ZRSD001_PAYLOAD, "selection": "open"}
    with pytest.raises(RobotError, match="Open Sales Order"):
        read_zrsd001.run(_ctx(raw, payload, tmp_path, FakeDesktop()))
    assert ("press", EXECUTE) not in raw.actions


@pytest.mark.parametrize("change", [{"selection": "all"}, {"date_to": "2026-11-13"}])
def test_zrsd001_rejects_payloads_the_recording_does_not_cover(tmp_path, change):
    raw = _sap()
    with pytest.raises(RobotError, match="zrsd001"):
        read_zrsd001.run(_ctx(raw, {**ZRSD001_PAYLOAD, **change}, tmp_path, FakeDesktop()))
    assert raw.actions == []


def test_zrsd004_fills_the_filter_and_exports_the_result(tmp_path):
    raw = _sap()
    out = read_zrsd004.run(_ctx(raw, ZRSD004_PAYLOAD, tmp_path, FakeDesktop(_export(tmp_path))))
    assert out.file == tmp_path / "zrsd004-job-7.xlsx"
    assert raw.Info.Transaction == "ZRSD004"
    assert _filled(raw, "zrsd004") == {
        "sales_org": "1000",
        "sold_to": "1200001145",
        "gi_date": "12.11.2026",
    }
    assert ("cell", GRID, 0, "VGBEL") in raw.actions


@pytest.mark.parametrize(
    ("module", "payload"),
    [(read_zrsd001, ZRSD001_PAYLOAD), (read_zrsd004, ZRSD004_PAYLOAD)],
)
def test_no_data_ends_the_read_before_any_export(tmp_path, module, payload):
    desktop = FakeDesktop(_export(tmp_path))
    with pytest.raises(NoReportData, match="không có dữ liệu"):
        module.run(_ctx(_sap(no_data=True), payload, tmp_path, desktop))
    assert desktop.saves == []


def test_a_retried_job_replaces_the_old_export(tmp_path):
    (tmp_path / "zrsd004-job-7.xlsx").write_bytes(b"old")
    raw = _sap()
    out = read_zrsd004.run(_ctx(raw, ZRSD004_PAYLOAD, tmp_path, FakeDesktop(_export(tmp_path))))
    assert out.file.read_bytes() == b"PK fake xlsx"


def test_windows_dialog_failure_fails_the_read(tmp_path):
    desktop = FakeDesktop(error="Không thấy hộp Save As của SAP")
    with pytest.raises(RobotError, match="Save As"):
        read_zrsd004.run(_ctx(_sap(), ZRSD004_PAYLOAD, tmp_path, desktop))
    assert desktop.saves[0].cancelled


def test_missing_file_after_the_dialogs_fails_the_read(tmp_path):
    with pytest.raises(RobotError, match="không tạo file xuất"):
        read_zrsd004.run(_ctx(_sap(), ZRSD004_PAYLOAD, tmp_path, FakeDesktop(source=None)))

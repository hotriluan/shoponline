"""The T-code guard: the robot stays inside ZRSD001 and ZRSD004 and never saves."""

import re
from pathlib import Path

import pytest

import shoponline.saprobot as saprobot_pkg
from shoponline.saprobot import guard
from shoponline.saprobot.errors import GuardViolation
from shoponline.saprobot.guard import (
    COMMAND_FIELD,
    VKEY_ENTER,
    VKEY_F8_EXECUTE,
    VKEY_SAVE,
    GuardedSession,
)
from shoponline.saprobot.popups import PopupRule, handle_popups
from tests.saprobot.fake_sap import FakeSession, Info

NO_DATA = PopupRule("no_data", "Information", "No data", "tbar[0]/btn[0]", "no_data")


def _session(tcode="SESSION_MANAGER") -> FakeSession:
    return FakeSession(Info("AEP", "300", "AL17016", tcode))


def _go_to(gui: FakeSession, tcode: str):
    return lambda *_: setattr(gui.Info, "Transaction", tcode)


def test_allowed_lists_are_pinned_in_code():
    # Widening either list must be a deliberate code change that also edits this test.
    assert {"S000", "SESSION_MANAGER", "ZRSD001", "ZRSD004"} == guard.ALLOWED_TRANSACTIONS
    assert {"ZRSD001", "ZRSD004"} == guard.OPENABLE_TRANSACTIONS
    assert {VKEY_ENTER, VKEY_F8_EXECUTE} == guard.ALLOWED_VKEYS
    assert VKEY_SAVE not in guard.ALLOWED_VKEYS


# ---------------------------------------------------------------- opening T-codes


def test_allowed_report_opens_through_the_command_field():
    raw = _session()
    raw.on_vkey = _go_to(raw, "ZRSD001")
    gui = GuardedSession(raw)
    gui.start_transaction("zrsd001")
    assert raw.text_of(COMMAND_FIELD) == "/nZRSD001"
    assert raw.actions == [("vkey", "wnd[0]", VKEY_ENTER)]
    assert gui.transaction == "ZRSD001" and gui.tripped is None


@pytest.mark.parametrize("tcode", ["VA02", "SE38", "S000", "SESSION_MANAGER", "ZRSD001 ; VA02"])
def test_tcode_outside_the_list_is_refused_and_nothing_reaches_okcd(tcode):
    raw = _session()
    gui = GuardedSession(raw)
    with pytest.raises(GuardViolation, match="không được mở"):
        gui.start_transaction(tcode)
    assert COMMAND_FIELD not in raw.elements and raw.actions == []
    assert gui.tripped


@pytest.mark.parametrize("element_id", [COMMAND_FIELD, "WND[0]/TBAR[0]/OKCD"])
def test_command_field_cannot_be_reached_any_other_way(element_id):
    raw = _session()
    gui = GuardedSession(raw)
    with pytest.raises(GuardViolation, match="ô lệnh"):
        gui.find(element_id)
    assert raw.elements == {}


# ---------------------------------------------------------------- after every action


def test_action_that_lands_on_va02_trips_and_nothing_more_is_pressed():
    raw = _session("ZRSD001")
    raw.on_press = _go_to(raw, "VA02")  # e.g. a grid button opening the sales order
    gui = GuardedSession(raw)
    with pytest.raises(GuardViolation, match="VA02"):
        gui.find("wnd[0]/usr/btnX").press()
    pressed = list(raw.actions)
    with pytest.raises(GuardViolation, match="đã dừng"):
        gui.send_vkey(VKEY_ENTER)
    with pytest.raises(GuardViolation):
        gui.find("wnd[0]/usr/txtY").set_text("x")
    assert raw.actions == pressed  # nothing after the trip
    assert raw.elements["wnd[0]/usr/txtY"].text == ""


def test_foreign_tcode_before_an_action_blocks_the_action():
    raw = _session("VA02")
    gui = GuardedSession(raw)
    with pytest.raises(GuardViolation, match="VA02"):
        gui.find("wnd[0]/usr/txtY").set_text("x")
    assert raw.elements["wnd[0]/usr/txtY"].text == ""


def test_answering_a_popup_that_opens_a_foreign_tcode_is_caught():
    raw = _session("ZRSD001")
    raw.popup("Information", "No data was selected")
    raw.on_press = lambda element_id: (raw.windows.pop(), _go_to(raw, "VA03")())
    gui = GuardedSession(raw)
    with pytest.raises(GuardViolation, match="VA03"):
        handle_popups(gui, [NO_DATA])
    assert gui.tripped


def test_set_text_select_and_press_pass_on_allowed_screens():
    raw = _session("ZRSD001")
    gui = GuardedSession(raw)
    gui.find("wnd[0]/usr/ctxtPO").set_text("A1")
    gui.find("wnd[0]/usr/radCOMPLETE").select()
    gui.send_vkey(VKEY_F8_EXECUTE)
    assert raw.text_of("wnd[0]/usr/ctxtPO") == "A1"
    assert raw.elements["wnd[0]/usr/radCOMPLETE"].selected is True
    assert raw.actions == [
        ("select", "wnd[0]/usr/radCOMPLETE"),
        ("vkey", "wnd[0]", VKEY_F8_EXECUTE),
    ]


def test_spreadsheet_export_menu_is_the_only_context_menu_item():
    assert frozenset({"&XXL"}) == guard.ALLOWED_CONTEXT_MENU_ITEMS
    raw = _session("ZRSD001")
    grid = GuardedSession(raw).find("wnd[0]/usr/grid")
    grid.set_current_cell(0, "BSTNK")
    grid.open_context_menu()
    grid.select_context_menu_item("&XXL")
    assert [a[0] for a in raw.actions] == ["cell", "menu", "menu_item"]


@pytest.mark.parametrize("item", ["&DETAIL", "&PC", "&SEND", ""])
def test_other_context_menu_items_trip_the_guard(item):
    raw = _session("ZRSD001")
    gui = GuardedSession(raw)
    with pytest.raises(GuardViolation, match="mục menu"):
        gui.find("wnd[0]/usr/grid").select_context_menu_item(item)
    assert raw.actions == [] and gui.tripped


def test_export_that_lands_on_a_foreign_tcode_trips():
    raw = _session("ZRSD001")
    raw.on_menu_item = _go_to(raw, "VA03")
    gui = GuardedSession(raw)
    with pytest.raises(GuardViolation, match="VA03"):
        gui.find("wnd[0]/usr/grid").select_context_menu_item("&XXL")


# ---------------------------------------------------------------- keys


@pytest.mark.parametrize("key", [VKEY_SAVE, 3, 12, 15, 86])
def test_save_and_unlisted_keys_are_refused(key):
    raw = _session("ZRSD001")
    gui = GuardedSession(raw)
    with pytest.raises(GuardViolation, match=f"phím {key}"):
        gui.send_vkey(key)
    assert raw.actions == []


def test_save_key_stays_forbidden_even_if_listed(monkeypatch):
    monkeypatch.setattr(guard, "ALLOWED_VKEYS", frozenset({VKEY_ENTER, VKEY_SAVE}))
    raw = _session("ZRSD001")
    with pytest.raises(GuardViolation):
        GuardedSession(raw).send_vkey(VKEY_SAVE)
    assert raw.actions == []


# ---------------------------------------------------------------- reads


class _Grid:
    RowCount = 2  # noqa: N815
    Children = object()  # noqa: N815 - a sub-object, must not leak

    def GetCellValue(self, row, column):  # noqa: N802
        return f"{row}:{column}"

    def doubleClickCurrentCell(self):  # noqa: N802
        raise AssertionError("must never be called")


def test_reads_return_plain_values_only():
    raw = _session("ZRSD001")
    raw.elements["wnd[0]/usr/grid"] = _Grid()
    cell = GuardedSession(raw).find("wnd[0]/usr/grid")
    assert cell.get("RowCount") == 2
    assert cell.call("GetCellValue", 0, "VBELN") == "0:VBELN"
    with pytest.raises(GuardViolation):
        cell.get("Children")
    with pytest.raises(GuardViolation):
        cell.get("doubleClickCurrentCell")
    with pytest.raises(GuardViolation, match="chỉ đọc"):
        cell.call("doubleClickCurrentCell")


def test_screenshot_still_works_after_a_trip(tmp_path):
    raw = _session("VA02")
    gui = GuardedSession(raw)
    with pytest.raises(GuardViolation):
        gui.check()
    gui.hardcopy(str(tmp_path / "x.png"))
    assert (tmp_path / "x.png").is_file()


# ---------------------------------------------------------------- source scan

# Raw SAP GUI calls that only guard.py may make.
RAW_ACCESS = re.compile(
    r"(?i:okcd)|findById|sendVKey|HardCopy|\._raw\b|\.text\s*=(?!=)|\.selected\s*=(?!=)"
)


def test_only_guard_touches_the_raw_session():
    root = Path(saprobot_pkg.__file__).parent
    offenders = []
    for path in sorted(root.rglob("*.py")):
        if path.name == "guard.py" and path.parent == root:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if RAW_ACCESS.search(line):
                offenders.append(f"{path.relative_to(root)}:{number}: {line.strip()}")
    assert offenders == []

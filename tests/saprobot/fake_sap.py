"""A stand-in for the SAP GUI Scripting object model, enough for the robot's logic tests.

It mirrors the shapes the robot uses: engine.Children / connection.Children collections with
Count and call-by-index, session.Info (with Transaction), session.findById, status bar
MessageType/Text, modal windows with Text and PopupDialogText, and HardCopy on the active window.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


class Collection:
    def __init__(self, items: list):
        self.items = items

    @property
    def Count(self) -> int:  # noqa: N802 - SAP GUI API name
        return len(self.items)

    def __call__(self, index: int):
        return self.items[index]


@dataclass
class Info:
    SystemName: str  # noqa: N815
    Client: str  # noqa: N815
    User: str  # noqa: N815
    Transaction: str = "SESSION_MANAGER"  # noqa: N815 - main menu after login


class Element:
    def __init__(self, session: FakeSession, element_id: str):
        self.session = session
        self.id = element_id
        self.text = ""
        self.selected = False

    def press(self) -> None:
        self.session.actions.append(("press", self.id))
        self.session.on_press(self.id)

    def select(self) -> None:
        self.session.actions.append(("select", self.id))
        self.selected = True

    def setCurrentCell(self, row: int, column: str) -> None:  # noqa: N802
        self.session.actions.append(("cell", self.id, row, column))

    def contextMenu(self) -> None:  # noqa: N802
        self.session.actions.append(("menu", self.id))

    def selectContextMenuItem(self, item: str) -> None:  # noqa: N802
        self.session.actions.append(("menu_item", self.id, item))
        self.session.on_menu_item(item)

    def sendVKey(self, key: int) -> None:  # noqa: N802
        self.session.actions.append(("vkey", self.id, key))
        self.session.on_vkey(key)


@dataclass
class StatusBar:
    MessageType: str = ""  # noqa: N815
    Text: str = ""  # noqa: N815


@dataclass
class Window:
    Text: str  # noqa: N815
    PopupDialogText: str = ""  # noqa: N815
    session: FakeSession | None = None

    def HardCopy(self, path: str, image_type: int) -> str:  # noqa: N802
        Path(path).write_bytes(b"\x89PNG fake")
        return path


@dataclass
class FakeSession:
    Info: Info  # noqa: N815
    status: StatusBar = field(default_factory=StatusBar)
    windows: list[Window] = field(default_factory=list)
    elements: dict[str, Element] = field(default_factory=dict)
    actions: list = field(default_factory=list)
    broken: bool = False  # connection dropped: every access raises
    Parent: FakeConnection | None = None  # noqa: N815 - set by the connection holding it

    def __post_init__(self):
        if not self.windows:
            self.windows = [Window("SAP Easy Access", session=self)]

    def __getattribute__(self, name):
        if name == "Info" and object.__getattribute__(self, "broken"):
            raise RuntimeError("The connection to SAP was lost")
        return object.__getattribute__(self, name)

    @property
    def Children(self) -> Collection:  # noqa: N802
        return Collection(self.windows)

    @property
    def ActiveWindow(self) -> Window:  # noqa: N802
        return self.windows[-1]

    def findById(self, element_id: str):  # noqa: N802
        if element_id == "wnd[0]/sbar":
            return self.status
        return self.elements.setdefault(element_id, Element(self, element_id))

    def text_of(self, element_id: str) -> str:
        return self.elements[element_id].text

    # hooks a test can replace
    def on_press(self, element_id: str) -> None:
        if element_id.startswith(f"wnd[{len(self.windows) - 1}]/") and len(self.windows) > 1:
            self.windows.pop()

    def on_vkey(self, key: int) -> None:
        pass

    def on_menu_item(self, item: str) -> None:
        pass

    def popup(self, title: str, text: str = "") -> None:
        self.windows.append(Window(title, text, session=self))


class FakeConnection:
    def __init__(self, sessions: list[FakeSession]):
        self.sessions = sessions
        self.engine: FakeEngine | None = None
        self.closed = False
        for session in sessions:
            session.Parent = self

    @property
    def Children(self) -> Collection:  # noqa: N802
        return Collection(self.sessions)

    def CloseConnection(self) -> None:  # noqa: N802 - logs the user off
        self.closed = True
        if self.engine is not None:
            self.engine.connections.remove(self)
            self.engine.closed.append(self)


class FakeEngine:
    """login_as: identity the next OpenConnection logs in as (None = login fails)."""

    def __init__(
        self, connections: list[FakeConnection] | None = None, login_as: Info | None = None
    ):
        self.connections = connections or []
        self.login_as = login_as
        self.opened: list[str] = []
        self.closed: list[FakeConnection] = []
        for connection in self.connections:
            connection.engine = self

    @property
    def Children(self) -> Collection:  # noqa: N802
        return Collection(self.connections)

    def OpenConnection(self, name: str, sync: bool):  # noqa: N802
        self.opened.append(name)
        session = FakeSession(Info("", "", "", "S000"))  # login screen
        login_as = self.login_as

        def on_vkey(key: int) -> None:
            if login_as is None:
                session.status.MessageType, session.status.Text = (
                    "E",
                    "Name or password is incorrect",
                )
            else:
                session.Info = login_as

        session.on_vkey = on_vkey
        connection = FakeConnection([session])
        connection.engine = self
        self.connections.append(connection)
        return connection


def engine_with(*sessions: FakeSession) -> FakeEngine:
    return FakeEngine([FakeConnection(list(sessions))])

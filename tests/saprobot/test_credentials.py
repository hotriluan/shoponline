"""The robot password store, against a stand-in for pywin32's win32cred."""

import pytest

from shoponline.saprobot import credentials

FALLBACK = {"SHOPONLINE_SAP_PASSWORD": "from-env"}


class FakeWin32Cred:
    CRED_TYPE_GENERIC = 1
    CRED_PERSIST_LOCAL_MACHINE = 2

    def __init__(self):
        self.records: dict[str, dict] = {}

    def CredWrite(self, record, flags):  # noqa: N802
        self.records[record["TargetName"]] = record

    def CredRead(self, name, kind, flags):  # noqa: N802
        if name not in self.records:
            raise RuntimeError("Element not found")
        return {"CredentialBlob": self.records[name]["CredentialBlob"]}


@pytest.fixture
def store(monkeypatch):
    fake = FakeWin32Cred()
    monkeypatch.setattr(credentials, "_win32cred", lambda: fake)
    return fake


def test_stored_value_is_found_by_user_regardless_of_case(store):
    credentials.store_password("al17016", "stored-pw")
    assert credentials.read_password("AL17016", {}) == "stored-pw"
    record = store.records["shoponline-sap:AL17016"]
    assert record["Persist"] == FakeWin32Cred.CRED_PERSIST_LOCAL_MACHINE


def test_stored_value_beats_the_environment_fallback(store):
    credentials.store_password("AL17016", "stored-pw")
    assert credentials.read_password("AL17016", FALLBACK) == "stored-pw"


def test_environment_is_the_fallback_when_nothing_is_stored(store):
    assert credentials.read_password("AL17016", FALLBACK) == "from-env"


def test_nothing_stored_and_no_fallback_is_none(store):
    assert credentials.read_password("AL17016", {}) is None
    assert credentials.read_password("", FALLBACK) is None


def test_bytes_blob_is_decoded_from_utf16(store):
    store.records["shoponline-sap:AL17016"] = {"CredentialBlob": "pw-é".encode("utf-16-le")}
    assert credentials.read_password("AL17016", {}) == "pw-é"


def test_without_pywin32_only_the_environment_is_used(monkeypatch):
    def missing():
        raise credentials.CredentialStoreUnavailable("no pywin32")

    monkeypatch.setattr(credentials, "_win32cred", missing)
    assert credentials.read_password("AL17016", FALLBACK) == "from-env"
    with pytest.raises(credentials.CredentialStoreUnavailable):
        credentials.store_password("AL17016", "x")

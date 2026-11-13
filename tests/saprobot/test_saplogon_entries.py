from shoponline.saprobot.saplogon_entries import EntriesReader, parse_entries

LANDSCAPE = """<?xml version="1.0" encoding="UTF-8"?>
<Landscape version="1"><Workspaces/><Services>
<Service type="SAPGUI" uuid="1" name="SAP PRODUCTION GROUP ALKANA" systemid="AEP" server="ALKANA"/>
<Service type="SAPGUI" uuid="2" name="QAS server" systemid="QAS" server="192.168.18.16:3220"/>
<Service type="SAPGUI" uuid="3" name="QAS server" systemid="QAS"/>
<Service type="SAPWEB" uuid="4" name="A web entry"/>
<Service type="SAPGUI" uuid="5" name=" "/>
</Services></Landscape>"""


def test_lists_each_sapgui_entry_once_sorted(tmp_path):
    path = tmp_path / "SAPUILandscape.xml"
    path.write_text(LANDSCAPE, encoding="utf-8")
    assert parse_entries(path) == ["QAS server", "SAP PRODUCTION GROUP ALKANA"]


def test_reader_reparses_only_when_the_file_changes(tmp_path):
    path = tmp_path / "SAPUILandscape.xml"
    path.write_text(LANDSCAPE, encoding="utf-8")
    reader = EntriesReader(path)
    assert reader.read() == ["QAS server", "SAP PRODUCTION GROUP ALKANA"]

    path.write_text("<not xml", encoding="utf-8")  # same mtime would hide this; force it
    import os

    stat = path.stat()
    os.utime(path, (stat.st_atime, stat.st_mtime + 5))
    assert reader.read() == []  # broken file: empty list, no exception

    path.write_text(LANDSCAPE.replace("QAS server", "DEV"), encoding="utf-8")
    os.utime(path, (stat.st_atime, stat.st_mtime + 10))
    assert reader.read() == ["DEV", "SAP PRODUCTION GROUP ALKANA"]


def test_missing_file_gives_an_empty_list(tmp_path):
    assert EntriesReader(tmp_path / "nope.xml").read() == []

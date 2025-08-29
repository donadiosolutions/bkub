import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bootServer.server import parse_streams

def test_parse_streams_basic():
    inp = {"pxe": {"format": "ipxe"}, "disk": {"location": "coreos.img"}, "raw.xz": "file1"}
    out = parse_streams(inp)
    assert out["pxe.format"] == "ipxe"
    assert out["disk.location"] == "coreos.img"
    assert out["raw.xz"] == "file1"

def test_parse_streams_alternate_raw():
    inp = {"raw": "rawfile", "pxe": {"format": "undionly"}}
    out = parse_streams(inp)
    assert out["raw"] == "rawfile"
    assert out["pxe.format"] == "undionly"
    assert out["raw.xz"] is None

def test_parse_streams_missing_keys():
    inp = {}
    out = parse_streams(inp)
    assert out["pxe.format"] is None
    assert out["disk.location"] is None
    assert out["raw"] is None
    assert out["raw.xz"] is None

def test_parse_streams_disk_as_string():
    inp = {"disk": "diskfile"}
    out = parse_streams(inp)
    assert out["disk.location"] == "diskfile"

"""Parser tests. Golden frames captured from a real BT610 on 2026-07-23."""
import math
import struct

import pytest

from custom_components.bt610.parser import Bt610Event, ParseFailure, parse

# Real captured frame: CURRENT_3, rec 42676, epoch 1784788013, ~0.0569 A
GOLDEN = bytes.fromhex("0100000003c01fb12468b7d51cb4a62db4616aee0e693d00")


def build_frame(record_type=26, record_number=1, epoch=1784787321,
                value=0.0142, proto=0x0001,
                mac=bytes.fromhex("1fb12468b7d5")):
    return (proto.to_bytes(2, "little") + b"\x00\x00" + b"\x03\xc0" + mac
            + bytes([record_type]) + record_number.to_bytes(2, "little")
            + epoch.to_bytes(4, "little") + struct.pack("<f", value) + b"\x00")


def test_parses_golden_frame():
    ev = parse(GOLDEN)
    assert isinstance(ev, Bt610Event)
    assert ev.embedded_mac == "D5:B7:68:24:B1:1F"
    assert ev.record_type == 28
    assert ev.record_number == 42676
    assert ev.epoch == 1784788013
    assert ev.value == pytest.approx(0.0569, abs=1e-4)
    assert ev.flags == 0xC003


def test_parses_battery_frame():
    ev = parse(build_frame(record_type=12, value=3600.0))
    assert ev.record_type == 12
    assert ev.value == pytest.approx(3600.0)


def test_accepts_23_bytes_ignores_reserved():
    assert isinstance(parse(build_frame()[:23]), Bt610Event)


def test_accepts_trailing_bytes():
    assert isinstance(parse(build_frame() + b"\xaa\xbb"), Bt610Event)


@pytest.mark.parametrize("length", range(0, 23))
def test_rejects_short_frames(length):
    r = parse(build_frame()[:length])
    assert isinstance(r, ParseFailure) and r.reason == "too_short"


def test_rejects_unknown_protocol():
    r = parse(build_frame(proto=0x0003))
    assert isinstance(r, ParseFailure) and r.reason == "unsupported_protocol"


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_rejects_non_finite(bad):
    r = parse(build_frame(value=bad))
    assert isinstance(r, ParseFailure) and r.reason == "not_finite"


def test_embedded_mac_is_reversed_bytes():
    ev = parse(build_frame(mac=bytes.fromhex("665544332211")))
    assert ev.embedded_mac == "11:22:33:44:55:66"

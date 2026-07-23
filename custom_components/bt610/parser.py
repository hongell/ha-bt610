"""Pure parser for Laird BT610 BLE advertisement frames (protocol 0x0001).

Frame layout after the 0x0077 company ID (which HA strips):
proto u16 LE | networkId u16 | flags u16 | BLE MAC 6B reversed |
recordType u8 | recordNumber u16 LE | epoch u32 LE | data float32 LE | reserved u8

Source: LairdCP/zephyr_lib ble_common headers + frames captured from a real
device. Minimum accepted length is 23 bytes: the trailing reserved byte is
not needed; extra trailing bytes are tolerated for forward compatibility.
"""
from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from typing import Literal

MIN_FRAME_LEN = 23
PROTOCOL_ID = 0x0001

FailureReason = Literal["too_short", "unsupported_protocol", "not_finite"]


@dataclass(frozen=True, slots=True)
class Bt610Event:
    embedded_mac: str
    flags: int
    record_type: int
    record_number: int
    epoch: int
    value: float


@dataclass(frozen=True, slots=True)
class ParseFailure:
    reason: FailureReason


def parse(payload: bytes) -> Bt610Event | ParseFailure:
    if len(payload) < MIN_FRAME_LEN:
        return ParseFailure("too_short")
    if int.from_bytes(payload[0:2], "little") != PROTOCOL_ID:
        return ParseFailure("unsupported_protocol")
    (value,) = struct.unpack_from("<f", payload, 19)
    if not math.isfinite(value):
        return ParseFailure("not_finite")
    return Bt610Event(
        embedded_mac=":".join(f"{b:02X}" for b in payload[11:5:-1]),
        flags=int.from_bytes(payload[4:6], "little"),
        record_type=payload[12],
        record_number=int.from_bytes(payload[13:15], "little"),
        epoch=int.from_bytes(payload[15:19], "little"),
        value=value,
    )

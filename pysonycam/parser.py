"""
Binary parser for PTP DevicePropInfo datasets returned by Sony's
GetAllExtDevicePropInfo (0x9209) command.

Mirrors the C++ ``parser.cpp`` / ``parser.h`` from the SDK reference
implementation, but uses Python's :mod:`struct` module for unpacking.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Any, Optional

from pysonycam.constants import DataType, DATA_TYPE_SIZE, scalar_type_for_array


@dataclass
class DevicePropInfo:
    """Parsed representation of a single SDIDevicePropInfoDataset."""
    property_code: int = 0
    data_type: int = 0
    get_set: int = 0        # 0 = read-only, 1 = read-write
    is_enable: int = 0      # 0 = invalid, 1 = valid
    form_flag: int = 0      # 0 = None, 1 = Range, 2 = Enumeration

    default_value: Any = None
    current_value: Any = None

    # Range-Form fields (form_flag == 1)
    minimum_value: Any = None
    maximum_value: Any = None
    step_size: Any = None

    # Enumeration-Form fields (form_flag == 2)
    supported_values: list = field(default_factory=list)

    @property
    def is_writable(self) -> bool:
        return self.get_set == 1

    @property
    def is_valid(self) -> bool:
        return self.is_enable != 0

    def __repr__(self) -> str:
        parts = [
            f"DevicePropInfo(code=0x{self.property_code:04X}",
            f"type=0x{self.data_type:04X}",
            f"rw={'RW' if self.is_writable else 'RO'}",
            f"enabled={self.is_valid}",
        ]
        if isinstance(self.current_value, int):
            parts.append(f"value=0x{self.current_value:X}")
        elif isinstance(self.current_value, str):
            parts.append(f'value="{self.current_value}"')
        else:
            parts.append(f"value={self.current_value}")
        if self.form_flag == 1:
            parts.append(f"range=[{self.minimum_value}..{self.maximum_value} step {self.step_size}]")
        elif self.form_flag == 2:
            parts.append(f"enum({len(self.supported_values)} values)")
        parts[-1] += ")"
        return ", ".join(parts)


def _read_ptp_string(data: bytes, offset: int) -> tuple[str, int]:
    """Read a PTP UTF-16LE string (uint8 length prefix, null-terminated).

    Returns (decoded string, number of bytes consumed).
    """
    if offset >= len(data):
        return "", 1
    str_len = data[offset]
    offset += 1
    if str_len == 0:
        return "", 1
    chars = []
    for i in range(str_len):
        if offset + 2 > len(data):
            break
        ch = struct.unpack_from("<H", data, offset)[0]
        offset += 2
        if ch == 0:
            break
        chars.append(chr(ch))
    consumed = 1 + str_len * 2
    return "".join(chars), consumed


def _read_scalar(data: bytes, offset: int, dt: int) -> tuple[Any, int]:
    """Read a scalar value of the given DataType at offset.

    Returns (value, bytes consumed).
    """
    if dt == DataType.STR:
        return _read_ptp_string(data, offset)

    size = DATA_TYPE_SIZE.get(dt)
    if size is None:
        return 0, 0

    if dt in (DataType.INT128, DataType.UINT128):
        lo = struct.unpack_from("<Q", data, offset)[0]
        hi = struct.unpack_from("<Q", data, offset + 8)[0]
        return (hi << 64) | lo, 16

    fmt_map: dict[int, str] = {
        DataType.INT8: "<b", DataType.UINT8: "<B",
        DataType.INT16: "<h", DataType.UINT16: "<H",
        DataType.INT32: "<i", DataType.UINT32: "<I",
        DataType.INT64: "<q", DataType.UINT64: "<Q",
    }
    fmt = fmt_map[dt]
    return struct.unpack_from(fmt, data, offset)[0], size


def _read_array(data: bytes, offset: int, dt: int) -> tuple[list, int]:
    """Read a PTP array (uint32 count, then count × element)."""
    scalar_dt = scalar_type_for_array(dt)
    count = struct.unpack_from("<I", data, offset)[0]
    pos = offset + 4
    values = []
    for _ in range(count):
        val, sz = _read_scalar(data, pos, scalar_dt)
        values.append(val)
        pos += sz
    return values, pos - offset


def parse_device_prop_info(data: bytes, offset: int = 0) -> tuple[DevicePropInfo, int]:
    """Parse one SDIDevicePropInfoDataset from *data* at *offset*.

    Binary layout (matches parser.cpp):
      uint16  DevicePropertyCode
      uint16  DataType
      uint8   GetSet
      uint8   IsEnable
      <T>     DefaultValue   (size depends on DataType)
      <T>     CurrentValue
      uint8   FormFlag       ← comes AFTER the values
      <form>  Form data      (Range or Enumeration, depends on FormFlag)

    Returns (DevicePropInfo, bytes consumed).
    """
    start = offset
    info = DevicePropInfo()

    info.property_code = struct.unpack_from("<H", data, offset)[0]; offset += 2
    info.data_type     = struct.unpack_from("<H", data, offset)[0]; offset += 2
    info.get_set       = data[offset]; offset += 1
    info.is_enable     = data[offset]; offset += 1

    dt = info.data_type
    is_array = 0x4001 <= dt <= 0x400A

    # Default value  (FormFlag not yet read)
    if is_array:
        info.default_value, sz = _read_array(data, offset, dt)
    else:
        info.default_value, sz = _read_scalar(data, offset, dt)
    offset += sz

    # Current value
    if is_array:
        info.current_value, sz = _read_array(data, offset, dt)
    else:
        info.current_value, sz = _read_scalar(data, offset, dt)
    offset += sz

    # FormFlag comes AFTER the values (matches C++ parse() order)
    info.form_flag = data[offset]; offset += 1

    # Form data
    scalar_dt = scalar_type_for_array(dt) if is_array else dt

    if info.form_flag == 1:
        # Range-Form: min, max, step
        info.minimum_value, sz = _read_scalar(data, offset, scalar_dt)
        offset += sz
        info.maximum_value, sz = _read_scalar(data, offset, scalar_dt)
        offset += sz
        info.step_size, sz = _read_scalar(data, offset, scalar_dt)
        offset += sz

    elif info.form_flag == 2:
        # Enumeration-Form first set
        num_values = struct.unpack_from("<H", data, offset)[0]; offset += 2
        for _ in range(num_values):
            val, sz = _read_scalar(data, offset, scalar_dt)
            info.supported_values.append(val)
            offset += sz

        # v3 always has a second enumeration set (may have count 0).
        # Read unconditionally, matching C++ "Added to support ver300" code.
        num_values_2nd = struct.unpack_from("<H", data, offset)[0]; offset += 2
        for _ in range(num_values_2nd):
            val, sz = _read_scalar(data, offset, scalar_dt)
            offset += sz   # consume bytes but discard (second set not exposed)

    return info, offset - start


def parse_all_device_props(data: bytes) -> dict[int, DevicePropInfo]:
    """Parse the full response from GetAllExtDevicePropInfo.

    The payload starts with a uint64 count of datasets.

    Returns a dict mapping property_code -> DevicePropInfo.
    """
    if len(data) < 8:
        return {}

    count = struct.unpack_from("<Q", data, 0)[0]
    offset = 8
    result: dict[int, DevicePropInfo] = {}

    for _ in range(count):
        if offset >= len(data):
            break
        try:
            info, consumed = parse_device_prop_info(data, offset)
            result[info.property_code] = info
            offset += consumed
        except (struct.error, IndexError):
            break

    return result


def parse_liveview_image(data: bytes) -> bytes:
    """Extract the JPEG payload from a LiveView object.

    The LiveView data starts with an 8-byte header:
      - uint32 offset (byte offset to JPEG start)
      - uint32 size   (JPEG payload size)
    """
    if len(data) < 8:
        return b""
    img_offset = struct.unpack_from("<I", data, 0)[0]
    img_size = struct.unpack_from("<I", data, 4)[0]
    return data[img_offset : img_offset + img_size]

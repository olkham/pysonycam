"""Tests for pysonycam.parser — binary PTP data parsing."""

import struct
import pytest

from pysonycam.parser import (
    DevicePropInfo,
    _read_ptp_string,
    _read_scalar,
    _read_array,
    parse_device_prop_info,
    parse_all_device_props,
    parse_liveview_image,
)
from pysonycam.constants import DataType


# ── helpers ────────────────────────────────────────────────────────────────

def _pack_ptp_string(s: str) -> bytes:
    """Build a PTP UTF-16LE string with length prefix and null terminator."""
    chars = s.encode("utf-16-le")
    # length byte includes the null terminator
    length = len(s) + 1
    return struct.pack("B", length) + chars + b"\x00\x00"


def _build_scalar_prop(
    prop_code: int,
    data_type: int,
    get_set: int,
    is_enable: int,
    default_val: int,
    current_val: int,
    form_flag: int,
    *,
    fmt: str = "<H",
    range_vals: tuple | None = None,          # (min, max, step)
    enum_vals: list[int] | None = None,
    enum_vals_2nd: list[int] | None = None,
) -> bytes:
    """Build a binary SDIDevicePropInfoDataset for a scalar property."""
    buf = bytearray()
    buf += struct.pack("<H", prop_code)
    buf += struct.pack("<H", data_type)
    buf += struct.pack("B", get_set)
    buf += struct.pack("B", is_enable)
    buf += struct.pack(fmt, default_val)
    buf += struct.pack(fmt, current_val)
    buf += struct.pack("B", form_flag)

    if form_flag == 1 and range_vals:
        for v in range_vals:
            buf += struct.pack(fmt, v)

    if form_flag == 2 and enum_vals is not None:
        buf += struct.pack("<H", len(enum_vals))
        for v in enum_vals:
            buf += struct.pack(fmt, v)
        # second enumeration set (v3 format)
        second = enum_vals_2nd or []
        buf += struct.pack("<H", len(second))
        for v in second:
            buf += struct.pack(fmt, v)

    return bytes(buf)


# ══════════════════════════════════════════════════════════════════════════
# DevicePropInfo dataclass
# ══════════════════════════════════════════════════════════════════════════

class TestDevicePropInfo:
    def test_default_values(self):
        info = DevicePropInfo()
        assert info.property_code == 0
        assert info.data_type == 0
        assert info.supported_values == []

    def test_is_writable(self):
        info = DevicePropInfo(get_set=1)
        assert info.is_writable is True
        info2 = DevicePropInfo(get_set=0)
        assert info2.is_writable is False

    def test_is_valid(self):
        assert DevicePropInfo(is_enable=1).is_valid is True
        assert DevicePropInfo(is_enable=0).is_valid is False

    def test_repr_int_value(self):
        info = DevicePropInfo(property_code=0x5007, current_value=0x0118)
        r = repr(info)
        assert "0x5007" in r
        assert "0x118" in r

    def test_repr_string_value(self):
        info = DevicePropInfo(current_value="hello")
        assert '"hello"' in repr(info)

    def test_repr_range_form(self):
        info = DevicePropInfo(form_flag=1, minimum_value=1, maximum_value=10, step_size=1)
        assert "range=" in repr(info)

    def test_repr_enum_form(self):
        info = DevicePropInfo(form_flag=2, supported_values=[1, 2, 3])
        assert "enum(3 values)" in repr(info)


# ══════════════════════════════════════════════════════════════════════════
# _read_ptp_string
# ══════════════════════════════════════════════════════════════════════════

class TestReadPTPString:
    def test_empty_string(self):
        data = b"\x00"
        s, consumed = _read_ptp_string(data, 0)
        assert s == ""
        assert consumed == 1

    def test_simple_ascii(self):
        data = _pack_ptp_string("ABC")
        s, consumed = _read_ptp_string(data, 0)
        assert s == "ABC"

    def test_offset_past_end(self):
        s, consumed = _read_ptp_string(b"", 5)
        assert s == ""
        assert consumed == 1


# ══════════════════════════════════════════════════════════════════════════
# _read_scalar
# ══════════════════════════════════════════════════════════════════════════

class TestReadScalar:
    def test_uint8(self):
        val, sz = _read_scalar(b"\xFF", 0, DataType.UINT8)
        assert val == 255
        assert sz == 1

    def test_int8(self):
        val, sz = _read_scalar(b"\x80", 0, DataType.INT8)
        assert val == -128
        assert sz == 1

    def test_uint16(self):
        data = struct.pack("<H", 0x1234)
        val, sz = _read_scalar(data, 0, DataType.UINT16)
        assert val == 0x1234
        assert sz == 2

    def test_int16(self):
        data = struct.pack("<h", -1000)
        val, sz = _read_scalar(data, 0, DataType.INT16)
        assert val == -1000
        assert sz == 2

    def test_uint32(self):
        data = struct.pack("<I", 0xDEADBEEF)
        val, sz = _read_scalar(data, 0, DataType.UINT32)
        assert val == 0xDEADBEEF
        assert sz == 4

    def test_int32(self):
        data = struct.pack("<i", -42)
        val, sz = _read_scalar(data, 0, DataType.INT32)
        assert val == -42
        assert sz == 4

    def test_uint64(self):
        data = struct.pack("<Q", 2**63 + 1)
        val, sz = _read_scalar(data, 0, DataType.UINT64)
        assert val == 2**63 + 1
        assert sz == 8

    def test_int128(self):
        lo, hi = 0x0102030405060708, 0x090A0B0C0D0E0F10
        data = struct.pack("<QQ", lo, hi)
        val, sz = _read_scalar(data, 0, DataType.INT128)
        assert val == (hi << 64) | lo
        assert sz == 16

    def test_string_type(self):
        ptp = _pack_ptp_string("Hi")
        val, sz = _read_scalar(ptp, 0, DataType.STR)
        assert val == "Hi"

    def test_unknown_returns_zero(self):
        val, sz = _read_scalar(b"\x00\x00", 0, DataType.UNDEF)
        assert val == 0
        assert sz == 0

    def test_with_offset(self):
        data = b"\x00\x00" + struct.pack("<H", 999)
        val, sz = _read_scalar(data, 2, DataType.UINT16)
        assert val == 999
        assert sz == 2


# ══════════════════════════════════════════════════════════════════════════
# _read_array
# ══════════════════════════════════════════════════════════════════════════

class TestReadArray:
    def test_empty_array(self):
        data = struct.pack("<I", 0)  # count = 0
        vals, sz = _read_array(data, 0, DataType.AUINT16)
        assert vals == []
        assert sz == 4  # just the count field

    def test_uint16_array(self):
        items = [10, 20, 30]
        data = struct.pack("<I", 3) + b"".join(struct.pack("<H", v) for v in items)
        vals, sz = _read_array(data, 0, DataType.AUINT16)
        assert vals == items
        assert sz == 4 + 3 * 2

    def test_uint32_array(self):
        items = [0x100, 0x200]
        data = struct.pack("<I", 2) + b"".join(struct.pack("<I", v) for v in items)
        vals, sz = _read_array(data, 0, DataType.AUINT32)
        assert vals == items
        assert sz == 4 + 2 * 4

    def test_non_array_type_raises(self):
        with pytest.raises(ValueError):
            _read_array(b"\x00" * 4, 0, DataType.UINT16)


# ══════════════════════════════════════════════════════════════════════════
# parse_device_prop_info
# ══════════════════════════════════════════════════════════════════════════

class TestParseDevicePropInfo:
    def test_no_form(self):
        """Parse a property with form_flag=0 (no range/enum)."""
        data = _build_scalar_prop(
            prop_code=0x5007,
            data_type=DataType.UINT16,
            get_set=1,
            is_enable=1,
            default_val=0x0118,
            current_val=0x0190,
            form_flag=0,
            fmt="<H",
        )
        info, consumed = parse_device_prop_info(data)
        assert info.property_code == 0x5007
        assert info.data_type == DataType.UINT16
        assert info.is_writable is True
        assert info.is_valid is True
        assert info.default_value == 0x0118
        assert info.current_value == 0x0190
        assert info.form_flag == 0
        assert consumed == len(data)

    def test_range_form(self):
        """Parse a property with form_flag=1 (range)."""
        data = _build_scalar_prop(
            prop_code=0xD20F,
            data_type=DataType.UINT16,
            get_set=1,
            is_enable=1,
            default_val=5600,
            current_val=6500,
            form_flag=1,
            fmt="<H",
            range_vals=(2500, 9900, 100),
        )
        info, consumed = parse_device_prop_info(data)
        assert info.form_flag == 1
        assert info.minimum_value == 2500
        assert info.maximum_value == 9900
        assert info.step_size == 100
        assert consumed == len(data)

    def test_enum_form(self):
        """Parse a property with form_flag=2 (enumeration)."""
        data = _build_scalar_prop(
            prop_code=0x5007,
            data_type=DataType.UINT16,
            get_set=1,
            is_enable=1,
            default_val=0x0118,
            current_val=0x0190,
            form_flag=2,
            fmt="<H",
            enum_vals=[0x0118, 0x0190, 0x0320],
            enum_vals_2nd=[],
        )
        info, consumed = parse_device_prop_info(data)
        assert info.form_flag == 2
        assert info.supported_values == [0x0118, 0x0190, 0x0320]
        assert consumed == len(data)

    def test_uint32_property(self):
        """Parse a UINT32 property (e.g. exposure mode)."""
        data = _build_scalar_prop(
            prop_code=0x500E,
            data_type=DataType.UINT32,
            get_set=0,
            is_enable=1,
            default_val=0x00010002,
            current_val=0x00000001,
            form_flag=0,
            fmt="<I",
        )
        info, _ = parse_device_prop_info(data)
        assert info.property_code == 0x500E
        assert info.current_value == 0x00000001
        assert info.is_writable is False

    def test_read_only_disabled(self):
        data = _build_scalar_prop(
            prop_code=0xD20E,
            data_type=DataType.UINT8,
            get_set=0,
            is_enable=0,
            default_val=7,
            current_val=5,
            form_flag=0,
            fmt="B",
        )
        info, _ = parse_device_prop_info(data)
        assert info.is_writable is False
        assert info.is_valid is False


# ══════════════════════════════════════════════════════════════════════════
# parse_all_device_props
# ══════════════════════════════════════════════════════════════════════════

class TestParseAllDeviceProps:
    def test_empty_data(self):
        assert parse_all_device_props(b"") == {}
        assert parse_all_device_props(b"\x00" * 4) == {}

    def test_single_property(self):
        prop = _build_scalar_prop(
            prop_code=0x5007,
            data_type=DataType.UINT16,
            get_set=1,
            is_enable=1,
            default_val=0x0118,
            current_val=0x0190,
            form_flag=0,
            fmt="<H",
        )
        # Header: uint64 count = 1
        data = struct.pack("<Q", 1) + prop
        result = parse_all_device_props(data)
        assert 0x5007 in result
        assert result[0x5007].current_value == 0x0190

    def test_multiple_properties(self):
        prop1 = _build_scalar_prop(
            prop_code=0x5007, data_type=DataType.UINT16,
            get_set=1, is_enable=1, default_val=0x0118, current_val=0x0190,
            form_flag=0, fmt="<H",
        )
        prop2 = _build_scalar_prop(
            prop_code=0xD20E, data_type=DataType.UINT8,
            get_set=0, is_enable=1, default_val=7, current_val=5,
            form_flag=0, fmt="B",
        )
        data = struct.pack("<Q", 2) + prop1 + prop2
        result = parse_all_device_props(data)
        assert len(result) == 2
        assert 0x5007 in result
        assert 0xD20E in result

    def test_truncated_data_graceful(self):
        """Truncated binary data should not crash — just return what we can."""
        prop = _build_scalar_prop(
            prop_code=0x5007, data_type=DataType.UINT16,
            get_set=1, is_enable=1, default_val=0x0118, current_val=0x0190,
            form_flag=0, fmt="<H",
        )
        data = struct.pack("<Q", 5) + prop  # claims 5, only has 1
        result = parse_all_device_props(data)
        assert len(result) == 1  # parsed what it could


# ══════════════════════════════════════════════════════════════════════════
# parse_liveview_image
# ══════════════════════════════════════════════════════════════════════════

class TestParseLiveviewImage:
    def test_empty_data(self):
        assert parse_liveview_image(b"") == b""
        assert parse_liveview_image(b"\x00" * 4) == b""

    def test_extract_jpeg(self):
        jpeg_data = b"\xFF\xD8\xFF\xE0" + b"\x00" * 100  # fake JPEG
        offset = 8  # header is 8 bytes, JPEG starts right after
        size = len(jpeg_data)
        header = struct.pack("<II", offset, size)
        data = header + jpeg_data
        result = parse_liveview_image(data)
        assert result == jpeg_data

    def test_nonzero_offset(self):
        """JPEG payload can start at an arbitrary offset."""
        padding = b"\xAA" * 16
        jpeg = b"\xFF\xD8" + b"\x42" * 50
        header = struct.pack("<II", 8 + len(padding), len(jpeg))
        data = header + padding + jpeg
        result = parse_liveview_image(data)
        assert result == jpeg

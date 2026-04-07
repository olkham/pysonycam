"""Tests for pysonycam.format — human-readable property formatting."""

import pytest

from pysonycam.format import property_name, format_value
from pysonycam.constants import DeviceProperty


# ══════════════════════════════════════════════════════════════════════════
# property_name()
# ══════════════════════════════════════════════════════════════════════════

class TestPropertyName:
    def test_known_property(self):
        assert property_name(DeviceProperty.F_NUMBER) == "F_NUMBER"

    def test_exposure_mode(self):
        assert property_name(DeviceProperty.EXPOSURE_MODE) == "EXPOSURE_MODE"

    def test_iso(self):
        assert property_name(DeviceProperty.ISO) == "ISO"

    def test_unknown_code(self):
        result = property_name(0x9999)
        assert result == "0x9999"

    def test_returns_string(self):
        for prop in DeviceProperty:
            name = property_name(int(prop))
            assert isinstance(name, str)
            assert len(name) > 0


# ══════════════════════════════════════════════════════════════════════════
# format_value() — dict-based formatters
# ══════════════════════════════════════════════════════════════════════════

class TestFormatValueDict:
    def test_f_number(self):
        assert format_value(DeviceProperty.F_NUMBER, 0x0118) == "F2.8"
        assert format_value(DeviceProperty.F_NUMBER, 0x0190) == "F4"

    def test_shutter_speed(self):
        assert format_value(DeviceProperty.SHUTTER_SPEED, 0) == "Bulb"
        assert format_value(DeviceProperty.SHUTTER_SPEED, 0x000100FA) == "1/250"

    def test_iso(self):
        assert format_value(DeviceProperty.ISO, 0x64) == "100"
        assert format_value(DeviceProperty.ISO, 0x00FFFFFF) == "AUTO"

    def test_exposure_mode(self):
        assert "Manual" in format_value(DeviceProperty.EXPOSURE_MODE, 0x00000001)
        assert "Program" in format_value(DeviceProperty.EXPOSURE_MODE, 0x00010002)

    def test_white_balance(self):
        assert format_value(DeviceProperty.WHITE_BALANCE, 0x0002) == "AWB"
        assert format_value(DeviceProperty.WHITE_BALANCE, 0x0004) == "Daylight"

    def test_focus_mode(self):
        assert format_value(DeviceProperty.FOCUS_MODE, 0x0001) == "MF"
        assert format_value(DeviceProperty.FOCUS_MODE, 0x0002) == "AF-S"

    def test_battery_level(self):
        result = format_value(DeviceProperty.BATTERY_LEVEL, 0x07)
        assert "Full" in result or "4/4" in result

    def test_image_size(self):
        assert format_value(DeviceProperty.IMAGE_SIZE, 0x01) == "L"
        assert format_value(DeviceProperty.IMAGE_SIZE, 0x02) == "M"

    def test_file_format(self):
        assert format_value(DeviceProperty.FILE_FORMAT, 0x01) == "RAW"
        assert format_value(DeviceProperty.FILE_FORMAT, 0x03) == "JPEG"

    def test_aspect_ratio(self):
        assert format_value(DeviceProperty.ASPECT_RATIO, 0x01) == "3:2"
        assert format_value(DeviceProperty.ASPECT_RATIO, 0x02) == "16:9"

    def test_on_off_properties(self):
        assert format_value(DeviceProperty.LIVEVIEW_STATUS, 0x01) == "On"
        assert format_value(DeviceProperty.LIVEVIEW_STATUS, 0x00) == "Off"

    def test_button_names(self):
        assert format_value(DeviceProperty.S1_BUTTON, 0x0001) == "Release"
        assert format_value(DeviceProperty.S1_BUTTON, 0x0002) == "Press"

    def test_unknown_value_in_known_formatter(self):
        """Known property but unmapped value should give hex."""
        result = format_value(DeviceProperty.F_NUMBER, 0xFFFF)
        assert result == "0xFFFF"


# ══════════════════════════════════════════════════════════════════════════
# format_value() — callable formatters
# ══════════════════════════════════════════════════════════════════════════

class TestFormatValueCallable:
    def test_exposure_comp_zero(self):
        result = format_value(DeviceProperty.EXPOSURE_COMPENSATION, 0)
        assert "0.0" in result
        assert "EV" in result

    def test_exposure_comp_positive(self):
        result = format_value(DeviceProperty.EXPOSURE_COMPENSATION, 1000)
        assert "+1.0" in result

    def test_exposure_comp_negative(self):
        # -1.0 EV → 0x10000 - 1000 = 0xFC18 (unsigned)
        result = format_value(DeviceProperty.EXPOSURE_COMPENSATION, 0xFC18)
        assert "-1.0" in result

    def test_color_temp(self):
        result = format_value(DeviceProperty.COLOR_TEMP, 5600)
        assert "5600" in result
        assert "K" in result

    def test_zoom_scale(self):
        result = format_value(DeviceProperty.ZOOM_SCALE, 2500)
        assert "2.5" in result


# ══════════════════════════════════════════════════════════════════════════
# format_value() — edge cases
# ══════════════════════════════════════════════════════════════════════════

class TestFormatValueEdgeCases:
    def test_unknown_property_code(self):
        result = format_value(0x9999, 42)
        assert result == "0x2A"

    def test_non_int_value(self):
        result = format_value(DeviceProperty.F_NUMBER, "not_an_int")
        assert result == "'not_an_int'"

    def test_none_value(self):
        result = format_value(DeviceProperty.F_NUMBER, None)
        assert result == "None"

    def test_list_value(self):
        result = format_value(DeviceProperty.F_NUMBER, [1, 2, 3])
        assert "[1, 2, 3]" in result


# ══════════════════════════════════════════════════════════════════════════
# Phase 8 — New formatters
# ══════════════════════════════════════════════════════════════════════════

class TestPictureProfileFormatter:
    def test_uses_enum_key_not_raw_hex(self):
        """PICTURE_PROFILE must be looked up via DeviceProperty enum, not raw hex."""
        assert DeviceProperty.PICTURE_PROFILE == 0xD23F
        result = format_value(DeviceProperty.PICTURE_PROFILE, 0x01)
        assert result == "PP1"

    def test_off(self):
        assert format_value(DeviceProperty.PICTURE_PROFILE, 0x00) == "Off"

    def test_pp10(self):
        assert format_value(DeviceProperty.PICTURE_PROFILE, 10) == "PP10"


class TestFocusAreaXYFormatter:
    def test_positive_coords(self):
        import struct
        # Pack x=100 (0x0064), y=150 (0x0096) as UINT32
        value = struct.unpack("<I", struct.pack("<hh", 100, 150))[0]
        result = format_value(DeviceProperty.FOCUS_AREA_XY, value)
        assert result == "(100, 150)"

    def test_negative_coords(self):
        import struct
        value = struct.unpack("<I", struct.pack("<hh", -50, -80))[0]
        result = format_value(DeviceProperty.FOCUS_AREA_XY, value)
        assert result == "(-50, -80)"

    def test_zero(self):
        result = format_value(DeviceProperty.FOCUS_AREA_XY, 0)
        assert result == "(0, 0)"


class TestSignedSpeedFormatter:
    def test_zoom_range_positive(self):
        import struct
        value = struct.unpack("<H", struct.pack("<h", 10000))[0]
        result = format_value(DeviceProperty.ZOOM_RANGE, value)
        assert result == "+10000"

    def test_zoom_range_negative(self):
        import struct
        value = struct.unpack("<H", struct.pack("<h", -5000))[0]
        result = format_value(DeviceProperty.ZOOM_RANGE, value)
        assert result == "-5000"

    def test_focus_range_zero(self):
        result = format_value(DeviceProperty.FOCUS_RANGE, 0)
        assert result == "+0"

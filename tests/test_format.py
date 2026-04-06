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

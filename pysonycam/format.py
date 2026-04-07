"""
Human-readable formatting for device property codes and values.

Provides two public helpers:

    property_name(code)  -> "F_NUMBER"  or  "0x5007"
    format_value(code, value)  -> "F2.8"  or  "0x118"
"""

from __future__ import annotations

import struct

from pysonycam.constants import (
    DeviceProperty,
    ExposureMode,
    OperatingMode,
    WhiteBalance,
    FocusMode,
    FocusArea,
    ImageSize,
    JpegQuality,
    FileFormat,
    AspectRatio,
    LiveViewMode,
    SaveMedia,
    ZoomSetting,
    MeteringMode,
    BatteryLevel,
    SHUTTER_SPEED_TABLE,
    F_NUMBER_TABLE,
    ISO_TABLE,
)

# ---------------------------------------------------------------------------
# Property-code → name
# ---------------------------------------------------------------------------
_PROP_NAMES: dict[int, str] = {int(p): p.name for p in DeviceProperty}


def property_name(code: int) -> str:
    """Return the name of a property code, e.g. ``"F_NUMBER"``."""
    return _PROP_NAMES.get(code, f"0x{code:04X}")


# ---------------------------------------------------------------------------
# Per-property value formatter tables
# ---------------------------------------------------------------------------

# Simple exposure compensation: raw int16 value / 1000 → EV string
def _fmt_ev(v: int) -> str:
    # value is a signed int16 (stored as unsigned in our parser)
    signed = v if v < 0x8000 else v - 0x10000
    ev = signed / 1000.0
    return f"{ev:+.1f} EV"

def _fmt_flash_comp(v: int) -> str:
    signed = v if v < 0x8000 else v - 0x10000
    ev = signed / 1000.0
    return f"{ev:+.1f} EV"

def _fmt_color_temp(v: int) -> str:
    return f"{v} K"

def _fmt_wb_shift(v: int) -> str:
    # Signed byte centered on 0xC0
    signed = v - 0xC0
    return f"{signed:+d}"

def _fmt_zoom_scale(v: int) -> str:
    return f"x{v / 1000:.1f}"

def _fmt_enum(enum_cls) -> dict[int, str]:
    """Build a {value: name} dict from an IntEnum class."""
    return {int(e): e.name.replace("_", " ").title() for e in enum_cls}

def _fmt_enum_pretty(enum_cls, overrides: dict[int, str] | None = None) -> dict[int, str]:
    d = _fmt_enum(enum_cls)
    if overrides:
        d.update(overrides)
    return d


# Exposure mode pretty names
_EXPOSURE_MODE_NAMES: dict[int, str] = {
    0x00000001: "Manual (M)",
    0x00010002: "Program Auto (P)",
    0x00020003: "Aperture Priority (A)",
    0x00030004: "Shutter Priority (S)",
    0x00048000: "Auto",
    0x00048001: "Auto+",
    0x00058011: "Sports Action",
    0x00058012: "Sunset",
    0x00058013: "Night Scene",
    0x00058014: "Landscape",
    0x00058015: "Macro",
    0x00058016: "Hand-held Twilight",
    0x00058017: "Night Portrait",
    0x00058018: "Anti Motion Blur",
    0x00078050: "Movie (P)",
    0x00078051: "Movie (A)",
    0x00078052: "Movie (S)",
    0x00078053: "Movie (M)",
    0x00078054: "Movie (Auto)",
    0x00098059: "S&Q Movie (P)",
    0x0009805A: "S&Q Movie (A)",
    0x0009805B: "S&Q Movie (S)",
    0x0009805C: "S&Q Movie (M)",
    0x000A8088: "Movie",
    0x000A8089: "Still",
    0x00088080: "HFR (P)",
    0x00088081: "HFR (A)",
    0x00088082: "HFR (S)",
    0x00088083: "HFR (M)",
}

_WB_NAMES: dict[int, str] = {
    0x0001: "Manual", 0x0002: "AWB", 0x0003: "One-push Auto",
    0x0004: "Daylight", 0x0005: "Fluorescent", 0x0006: "Tungsten",
    0x0007: "Flash", 0x8001: "Fluor. Warm White", 0x8002: "Fluor. Cool White",
    0x8003: "Fluor. Day White", 0x8004: "Fluor. Daylight",
    0x8010: "Cloudy", 0x8011: "Shade", 0x8012: "Color Temp.",
    0x8020: "Custom 1", 0x8021: "Custom 2", 0x8022: "Custom 3",
    0x8023: "Custom", 0x8030: "Underwater Auto",
}

_FOCUS_MODE_NAMES: dict[int, str] = {
    0x0001: "MF", 0x0002: "AF-S", 0x8004: "AF-C", 0x8005: "AF-Auto", 0x8006: "DMF",
}

_METERING_NAMES: dict[int, str] = {
    0x8001: "Multi", 0x8002: "Center-weighted", 0x8003: "Entire Screen Avg.",
    0x8004: "Spot: Standard", 0x8005: "Spot: Large", 0x8006: "Highlight",
}

_BATTERY_NAMES: dict[int, str] = {
    0x01: "Dummy Battery", 0x02: "Unusable", 0x03: "Pre-End",
    0x04: "1/4", 0x05: "2/4", 0x06: "3/4", 0x07: "Full (4/4)",
    0x08: "1/3", 0x09: "2/3", 0x0A: "Full (3/3)",
    0x0B: "Pre-End (USB)", 0x0C: "1/4 (USB)", 0x0D: "2/4 (USB)",
    0x0E: "3/4 (USB)", 0x0F: "Full (USB)", 0x10: "USB Power",
}

_FLASH_MODE_NAMES: dict[int, str] = {
    0x0001: "Auto Flash", 0x0002: "Flash Off", 0x0003: "Fill Flash",
    0x0004: "Red-eye Auto", 0x0005: "Red-eye Fill", 0x0006: "External Sync",
    0x8001: "Slow Sync", 0x8003: "Rear Sync", 0x8004: "Wireless",
    0x8021: "SS Auto", 0x8022: "HSS Fill", 0x8024: "HSS Wireless",
}

_FOCUS_AREA_NAMES: dict[int, str] = {
    0x0001: "Wide", 0x0002: "Zone", 0x0003: "Center",
    0x0101: "Flex Spot S", 0x0102: "Flex Spot M", 0x0103: "Flex Spot L",
    0x0104: "Expand Flex Spot",
    0x0201: "Lock-On Wide", 0x0202: "Lock-On Zone", 0x0203: "Lock-On Center",
    0x0204: "Lock-On Flex S", 0x0205: "Lock-On Flex M", 0x0206: "Lock-On Flex L",
    0x0207: "Lock-On Expand Flex",
}

_AF_STATUS_NAMES: dict[int, str] = {
    0x01: "Unlock", 0x02: "[AF-S] Focused / Locked",
    0x03: "[AF-S] Not Focused / Low Contrast",
    0x05: "[AF-C] Tracking", 0x06: "[AF-C] Focused", 0x07: "[AF-C] Not Focused",
}

_MOVIE_FORMAT_NAMES: dict[int, str] = {
    0x03: "AVCHD", 0x04: "MP4", 0x08: "XAVC S 4K", 0x09: "XAVC S HD",
    0x0A: "XAVC HS 8K", 0x0B: "XAVC HS 4K", 0x0C: "XAVC S-L 4K",
    0x0D: "XAVC S-L HD", 0x0E: "XAVC S-I 4K", 0x0F: "XAVC S-I HD",
    0x10: "XAVC I", 0x11: "XAVC L", 0x12: "XAVC Proxy",
    0x13: "XAVC HS HD", 0x18: "X-OCN XT", 0x19: "X-OCN ST", 0x1A: "X-OCN LT",
}

_CREATIVE_STYLE_NAMES: dict[int, str] = {
    0x01: "Standard", 0x02: "Vivid", 0x03: "Portrait", 0x04: "Landscape",
    0x05: "Sunset", 0x06: "B&W", 0x07: "Light", 0x08: "Neutral",
    0x09: "Clear", 0x0A: "Deep", 0x0B: "Night View", 0x0C: "Autumn Leaves",
    0x0D: "Sepia",
}

_DRO_HDR_NAMES: dict[int, str] = {
    0x00: "Off", 0x02: "DRO", 0x10: "DRO +", 0x11: "DRO +1",
    0x12: "DRO +2", 0x13: "DRO +3", 0x14: "DRO +4", 0x15: "DRO +5",
    0x1F: "DRO Auto", 0x20: "HDR Auto", 0x21: "HDR 1EV",
    0x22: "HDR 2EV", 0x23: "HDR 3EV", 0x24: "HDR 4EV",
    0x25: "HDR 5EV", 0x26: "HDR 6EV",
}

_SAVE_MEDIA_NAMES: dict[int, str] = {
    0x0001: "Host", 0x0010: "Camera (Card)", 0x0011: "Host + Camera",
}

_OPERATING_MODE_NAMES: dict[int, str] = {
    0x01: "Standby", 0x02: "Still Rec", 0x03: "Movie Rec",
    0x04: "Contents Transfer",
}

_IMAGE_SIZE_NAMES: dict[int, str] = {0x01: "L", 0x02: "M", 0x03: "S"}
_JPEG_QUALITY_NAMES: dict[int, str] = {
    0x01: "Extra Fine", 0x02: "Fine", 0x03: "Standard", 0x04: "Light",
}
_FILE_FORMAT_NAMES: dict[int, str] = {0x01: "RAW", 0x02: "RAW+JPEG", 0x03: "JPEG"}
_ASPECT_RATIO_NAMES: dict[int, str] = {0x01: "3:2", 0x02: "16:9", 0x03: "4:3", 0x04: "1:1"}
_LIVEVIEW_MODE_NAMES: dict[int, str] = {0x01: "Low", 0x02: "High"}
_ZOOM_SETTING_NAMES: dict[int, str] = {
    0x01: "Optical Only", 0x02: "Smart Zoom", 0x03: "Clear Image Zoom", 0x04: "Digital Zoom",
}
_PICTURE_EFFECTS_NAMES: dict[int, str] = {
    0x8000: "Off", 0x8001: "Toy Camera Normal", 0x8010: "Pop Color",
    0x8020: "Posterization B&W", 0x8021: "Posterization Color",
    0x8030: "Retro Photo", 0x8040: "Soft High Key", 0x8060: "High Contrast Mono",
    0x8090: "Rich Tone Mono",
}
_PICTURE_PROFILE_NAMES: dict[int, str] = {
    0x00: "Off", **{i: f"PP{i}" for i in range(1, 11)},
}
_ON_OFF = {0x00: "Off", 0x01: "On"}
_ON_OFF_PRESS = {0x0001: "Off/Release", 0x0002: "On/Press"}
_NEAR_FAR_NAMES: dict[int, str] = {
    0x0101: "Near Small", 0x0103: "Near Medium", 0x0107: "Near Large",
    0x0201: "Far Small", 0x0203: "Far Medium", 0x0207: "Far Large",
}
_MOVIE_REC_NAMES: dict[int, str] = {
    0x00: "Stopped", 0x01: "Recording", 0x02: "Unable to Record",
}
_BUTTON_NAMES: dict[int, str] = {0x0001: "Release", 0x0002: "Press"}
_AE_LOCK_NAMES: dict[int, str] = {0x0001: "Unlocked", 0x0002: "Locked"}
_VIEW_NAMES: dict[int, str] = {0x01: "On", 0x02: "Off"}


def _fmt_focus_xy(v: int) -> str:
    """Format FOCUS_AREA_XY: unpack two INT16 from a UINT32."""
    data = struct.pack("<I", v & 0xFFFFFFFF)
    x = struct.unpack_from("<h", data, 0)[0]
    y = struct.unpack_from("<h", data, 2)[0]
    return f"({x}, {y})"


def _fmt_signed_speed(v: int) -> str:
    """Format a signed INT16 speed value (ZOOM_RANGE / FOCUS_RANGE)."""
    data = struct.pack("<H", v & 0xFFFF)
    sv = struct.unpack_from("<h", data, 0)[0]
    return f"{sv:+d}"

# ---------------------------------------------------------------------------
# Master dispatch table:  property_code -> callable(value) -> str
# ---------------------------------------------------------------------------
_VALUE_FORMATTERS: dict[int, object] = {
    DeviceProperty.F_NUMBER:             F_NUMBER_TABLE,
    DeviceProperty.SHUTTER_SPEED:        SHUTTER_SPEED_TABLE,
    DeviceProperty.ISO:                  ISO_TABLE,
    DeviceProperty.EXPOSURE_MODE:        _EXPOSURE_MODE_NAMES,
    DeviceProperty.WHITE_BALANCE:        _WB_NAMES,
    DeviceProperty.FOCUS_MODE:           _FOCUS_MODE_NAMES,
    DeviceProperty.METERING_MODE:        _METERING_NAMES,
    DeviceProperty.FLASH_MODE:           _FLASH_MODE_NAMES,
    DeviceProperty.FOCUS_AREA:           _FOCUS_AREA_NAMES,
    DeviceProperty.AF_STATUS:            _AF_STATUS_NAMES,
    DeviceProperty.BATTERY_LEVEL:        _BATTERY_NAMES,
    DeviceProperty.OPERATING_MODE:       _OPERATING_MODE_NAMES,
    DeviceProperty.EXPOSURE_COMPENSATION: _fmt_ev,
    DeviceProperty.FLASH_COMP:           _fmt_flash_comp,
    DeviceProperty.COLOR_TEMP:           _fmt_color_temp,
    DeviceProperty.WB_AB:                _fmt_wb_shift,
    DeviceProperty.WB_GM:                _fmt_wb_shift,
    DeviceProperty.ZOOM_SCALE:           _fmt_zoom_scale,
    DeviceProperty.DRO_HDR_MODE:         _DRO_HDR_NAMES,
    DeviceProperty.IMAGE_SIZE:           _IMAGE_SIZE_NAMES,
    DeviceProperty.JPEG_QUALITY:         _JPEG_QUALITY_NAMES,
    DeviceProperty.FILE_FORMAT:          _FILE_FORMAT_NAMES,
    DeviceProperty.ASPECT_RATIO:         _ASPECT_RATIO_NAMES,
    DeviceProperty.LIVEVIEW_MODE:        _LIVEVIEW_MODE_NAMES,
    DeviceProperty.SAVE_MEDIA:           _SAVE_MEDIA_NAMES,
    DeviceProperty.ZOOM_SETTING:         _ZOOM_SETTING_NAMES,
    DeviceProperty.PICTURE_EFFECTS:      _PICTURE_EFFECTS_NAMES,
    DeviceProperty.CREATIVE_STYLE:       _CREATIVE_STYLE_NAMES,
    DeviceProperty.MOVIE_FORMAT:         _MOVIE_FORMAT_NAMES,
    DeviceProperty.PICTURE_PROFILE:      _PICTURE_PROFILE_NAMES,
    DeviceProperty.NEAR_FAR:             _NEAR_FAR_NAMES,
    DeviceProperty.MOVIE_REC:            _MOVIE_REC_NAMES,
    DeviceProperty.S1_BUTTON:            _BUTTON_NAMES,
    DeviceProperty.S2_BUTTON:            _BUTTON_NAMES,
    DeviceProperty.AE_LOCK:              _AE_LOCK_NAMES,
    DeviceProperty.VIEW:                 _VIEW_NAMES,
    DeviceProperty.LIVEVIEW_STATUS:      _ON_OFF,
    DeviceProperty.WIRELESS_FLASH:       _ON_OFF,
    DeviceProperty.FOCUS_MAGNIFY:        _ON_OFF,
    DeviceProperty.AF_LOCK:              _AF_STATUS_NAMES,
    DeviceProperty.AWB_LOCK:             _ON_OFF,
    DeviceProperty.FOCUS_AREA_XY:        _fmt_focus_xy,
    DeviceProperty.CUSTOM_WB_STANDBY:    _ON_OFF_PRESS,
    DeviceProperty.CUSTOM_WB_STANDBY_CANCEL: _ON_OFF_PRESS,
    DeviceProperty.CUSTOM_WB_EXECUTE:    _ON_OFF_PRESS,
    DeviceProperty.ZOOM_RANGE:           _fmt_signed_speed,
    DeviceProperty.FOCUS_RANGE:          _fmt_signed_speed,
}


def format_value(code: int, value: object) -> str:
    """Return a human-readable string for *value* of property *code*.

    Falls back to a hex representation for unknown codes or unmapped values.
    """
    if not isinstance(value, int):
        return repr(value)

    formatter = _VALUE_FORMATTERS.get(code)

    if formatter is None:
        return f"0x{value:X}"

    if callable(formatter) and not isinstance(formatter, dict):
        return formatter(value)

    # dict lookup
    result = formatter.get(value)          # type: ignore[union-attr]
    if result is not None:
        return result

    return f"0x{value:X}"

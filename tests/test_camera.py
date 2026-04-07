"""Tests for pysonycam.camera — SonyCamera high-level API (mocked transport)."""

import struct
import threading
import time
from unittest.mock import MagicMock, patch, PropertyMock, call

import pytest

from pysonycam.camera import SonyCamera, _EventDispatcher
from pysonycam.constants import (
    DeviceProperty,
    ExposureMode,
    OperatingMode,
    ResponseCode,
    SaveMedia,
    SDIOOpCode,
    SDIOEventCode,
    PTPOpCode,
    DataType,
    SHOT_OBJECT_HANDLE,
    LIVEVIEW_OBJECT_HANDLE,
    SDI_VERSION_V3,
)
from pysonycam.exceptions import (
    PropertyError,
    TransactionError,
    AuthenticationError,
    SonyCameraError,
)
from pysonycam.parser import DevicePropInfo
from pysonycam.ptp import PTPEvent


# ── fixtures ───────────────────────────────────────────────────────────────

def _ok_resp():
    """Return a mock PTPResponse with code=OK."""
    r = MagicMock()
    r.code = ResponseCode.OK
    return r


def _err_resp(code=ResponseCode.GENERAL_ERROR):
    r = MagicMock()
    r.code = code
    return r


def _make_camera() -> SonyCamera:
    """Create a SonyCamera with a fully mocked transport."""
    with patch("pysonycam.camera.PTPTransport") as MockTransport:
        transport = MockTransport.return_value
        transport.is_connected = True
        transport.send.return_value = _ok_resp()
        transport.receive.return_value = (_ok_resp(), b"")
        cam = SonyCamera()
        cam._transport = transport
        cam._authenticated = True
        return cam


def _prop_data_single(
    prop_code: int, data_type: int, value: int, fmt: str = "<H"
) -> bytes:
    """Build a GetAllExtDevicePropInfo payload with a single property."""
    prop = bytearray()
    prop += struct.pack("<H", prop_code)
    prop += struct.pack("<H", data_type)
    prop += struct.pack("B", 1)   # get_set = RW
    prop += struct.pack("B", 1)   # is_enable = valid
    prop += struct.pack(fmt, value)  # default
    prop += struct.pack(fmt, value)  # current
    prop += struct.pack("B", 0)   # form_flag = none
    return struct.pack("<Q", 1) + bytes(prop)


# ══════════════════════════════════════════════════════════════════════════
# Connection lifecycle
# ══════════════════════════════════════════════════════════════════════════

class TestConnectionLifecycle:
    def test_connect_opens_session(self):
        cam = _make_camera()
        cam.connect()
        cam._transport.connect.assert_called_once()
        cam._transport.send.assert_called_once()  # OpenSession

    def test_disconnect(self):
        cam = _make_camera()
        cam.disconnect()
        cam._transport.disconnect.assert_called_once()
        assert cam._authenticated is False

    def test_disconnect_when_not_connected(self):
        cam = _make_camera()
        cam._transport.is_connected = False
        cam.disconnect()  # should not raise
        cam._transport.disconnect.assert_not_called()

    def test_is_connected_delegates(self):
        cam = _make_camera()
        cam._transport.is_connected = True
        assert cam.is_connected is True


# ══════════════════════════════════════════════════════════════════════════
# Property access
# ══════════════════════════════════════════════════════════════════════════

class TestPropertyAccess:
    def test_get_all_properties(self):
        cam = _make_camera()
        data = _prop_data_single(0x5007, DataType.UINT16, 0x0190)
        cam._transport.receive.return_value = (_ok_resp(), data)

        props = cam.get_all_properties()
        assert 0x5007 in props
        assert props[0x5007].current_value == 0x0190

    def test_get_property_found(self):
        cam = _make_camera()
        data = _prop_data_single(0x5007, DataType.UINT16, 0x0118)
        cam._transport.receive.return_value = (_ok_resp(), data)

        info = cam.get_property(0x5007)
        assert info.current_value == 0x0118

    def test_get_property_not_found(self):
        cam = _make_camera()
        data = _prop_data_single(0x5007, DataType.UINT16, 0x0118)
        cam._transport.receive.return_value = (_ok_resp(), data)

        with pytest.raises(PropertyError, match="0x9999"):
            cam.get_property(0x9999)

    def test_set_property_ok(self):
        cam = _make_camera()
        cam._properties = {0x5007: DevicePropInfo(data_type=DataType.UINT16)}
        cam.set_property(0x5007, 0x0190)
        cam._transport.send.assert_called_once()

    def test_set_property_error(self):
        cam = _make_camera()
        cam._transport.send.return_value = _err_resp(ResponseCode.DEVICE_PROP_NOT_SUPPORTED)
        with pytest.raises(PropertyError):
            cam.set_property(0x5007, 0x0190)


# ══════════════════════════════════════════════════════════════════════════
# Control device
# ══════════════════════════════════════════════════════════════════════════

class TestControlDevice:
    def test_control_device_ok(self):
        cam = _make_camera()
        cam.control_device(DeviceProperty.S1_BUTTON, 0x0002)
        cam._transport.send.assert_called_once()

    def test_control_device_error(self):
        cam = _make_camera()
        cam._transport.send.return_value = _err_resp()
        with pytest.raises(TransactionError):
            cam.control_device(DeviceProperty.S1_BUTTON, 0x0002)


# ══════════════════════════════════════════════════════════════════════════
# Convenience setters
# ══════════════════════════════════════════════════════════════════════════

class TestConvenienceSetters:
    def test_set_exposure_mode(self):
        cam = _make_camera()
        cam.set_exposure_mode(ExposureMode.MANUAL)
        args = cam._transport.send.call_args
        assert args[0][1] == [DeviceProperty.EXPOSURE_MODE]

    def test_set_iso(self):
        cam = _make_camera()
        cam.set_iso(400)
        args = cam._transport.send.call_args
        assert args[0][1] == [DeviceProperty.ISO]

    def test_set_aperture(self):
        cam = _make_camera()
        cam.set_aperture(0x0118)
        args = cam._transport.send.call_args
        assert args[0][1] == [DeviceProperty.F_NUMBER]

    def test_set_shutter_speed(self):
        cam = _make_camera()
        cam.set_shutter_speed(0x000100FA)
        args = cam._transport.send.call_args
        assert args[0][1] == [DeviceProperty.SHUTTER_SPEED]


# ══════════════════════════════════════════════════════════════════════════
# set_mode
# ══════════════════════════════════════════════════════════════════════════

class TestSetMode:
    def test_unknown_mode_string(self):
        cam = _make_camera()
        with pytest.raises(ValueError, match="Unknown mode"):
            cam.set_mode("invalid_mode")


# ══════════════════════════════════════════════════════════════════════════
# Zoom / focus
# ══════════════════════════════════════════════════════════════════════════

class TestZoomFocus:
    def test_zoom_in(self):
        cam = _make_camera()
        cam.zoom_in(3)
        args = cam._transport.send.call_args
        assert args[0][1] == [DeviceProperty.ZOOM]

    def test_zoom_out(self):
        cam = _make_camera()
        cam.zoom_out(2)
        cam._transport.send.assert_called_once()

    def test_zoom_stop(self):
        cam = _make_camera()
        cam.zoom_stop()
        cam._transport.send.assert_called_once()

    def test_focus_near(self):
        cam = _make_camera()
        cam.focus_near(3)
        args = cam._transport.send.call_args
        assert args[0][1] == [DeviceProperty.NEAR_FAR]

    def test_focus_far(self):
        cam = _make_camera()
        cam.focus_far(1)
        args = cam._transport.send.call_args
        assert args[0][1] == [DeviceProperty.NEAR_FAR]


# ══════════════════════════════════════════════════════════════════════════
# Movie recording
# ══════════════════════════════════════════════════════════════════════════

class TestMovieRecording:
    def test_start_movie(self):
        cam = _make_camera()
        cam.start_movie()
        args = cam._transport.send.call_args
        assert args[0][1] == [DeviceProperty.MOVIE_REC]

    def test_stop_movie(self):
        cam = _make_camera()
        cam.stop_movie()
        args = cam._transport.send.call_args
        assert args[0][1] == [DeviceProperty.MOVIE_REC]


# ══════════════════════════════════════════════════════════════════════════
# LiveView
# ══════════════════════════════════════════════════════════════════════════

class TestLiveView:
    def test_get_liveview_frame(self):
        cam = _make_camera()
        # Fake liveview data: 8-byte header (offset=8, size=4) + JPEG payload
        jpeg = b"\xFF\xD8\xFF\xE0"
        lv_data = struct.pack("<II", 8, len(jpeg)) + jpeg
        cam._transport.receive.return_value = (_ok_resp(), lv_data)

        frame = cam.get_liveview_frame()
        assert frame == jpeg

    def test_liveview_stream_with_count(self):
        cam = _make_camera()
        jpeg = b"\xFF\xD8\xFF\xE0"
        lv_data = struct.pack("<II", 8, len(jpeg)) + jpeg
        cam._transport.receive.return_value = (_ok_resp(), lv_data)

        frames = list(cam.liveview_stream(count=3))
        assert len(frames) == 3
        assert all(f == jpeg for f in frames)


# ══════════════════════════════════════════════════════════════════════════
# GetObject
# ══════════════════════════════════════════════════════════════════════════

class TestGetObject:
    def test_get_object_success(self):
        cam = _make_camera()
        image = b"\xFF" * 1000
        cam._transport.receive.return_value = (_ok_resp(), image)
        result = cam.get_object(SHOT_OBJECT_HANDLE)
        assert result == image

    def test_get_object_error(self):
        cam = _make_camera()
        cam._transport.receive.return_value = (_err_resp(), b"")
        with pytest.raises(TransactionError):
            cam.get_object(SHOT_OBJECT_HANDLE)


# ══════════════════════════════════════════════════════════════════════════
# Phase 2 — PTP operation methods
# ══════════════════════════════════════════════════════════════════════════

class TestGetDeviceInfo:
    def test_success(self):
        cam = _make_camera()
        cam._transport.receive.return_value = (_ok_resp(), b"\x00" * 20)
        result = cam.get_device_info()
        assert result == b"\x00" * 20
        args = cam._transport.receive.call_args
        assert args[0][0] == PTPOpCode.GET_DEVICE_INFO

    def test_error(self):
        cam = _make_camera()
        cam._transport.receive.return_value = (_err_resp(), b"")
        with pytest.raises(TransactionError):
            cam.get_device_info()


class TestGetStorageInfo:
    def test_success(self):
        cam = _make_camera()
        cam._transport.receive.return_value = (_ok_resp(), b"\x01" * 10)
        result = cam.get_storage_info(0x00010001)
        assert len(result) == 10
        args = cam._transport.receive.call_args
        assert args[0][0] == PTPOpCode.GET_STORAGE_INFO
        assert args[0][1] == [0x00010001]

    def test_error(self):
        cam = _make_camera()
        cam._transport.receive.return_value = (_err_resp(), b"")
        with pytest.raises(TransactionError):
            cam.get_storage_info(1)


class TestGetNumObjects:
    def test_returns_count(self):
        cam = _make_camera()
        payload = struct.pack("<I", 42)
        cam._transport.receive.return_value = (_ok_resp(), payload)
        assert cam.get_num_objects() == 42

    def test_empty_payload(self):
        cam = _make_camera()
        cam._transport.receive.return_value = (_ok_resp(), b"")
        assert cam.get_num_objects() == 0

    def test_error(self):
        cam = _make_camera()
        cam._transport.receive.return_value = (_err_resp(), b"")
        with pytest.raises(TransactionError):
            cam.get_num_objects()


class TestGetThumb:
    def test_success(self):
        cam = _make_camera()
        thumb = b"\xFF\xD8\xFF\xE0" + b"\x00" * 100
        cam._transport.receive.return_value = (_ok_resp(), thumb)
        result = cam.get_thumb(0x00000001)
        assert result == thumb
        args = cam._transport.receive.call_args
        assert args[0][0] == PTPOpCode.GET_THUMB
        assert args[0][1] == [0x00000001]

    def test_error(self):
        cam = _make_camera()
        cam._transport.receive.return_value = (_err_resp(), b"")
        with pytest.raises(TransactionError):
            cam.get_thumb(1)


class TestGetPartialObject:
    def test_forwards_three_params(self):
        cam = _make_camera()
        cam._transport.receive.return_value = (_ok_resp(), b"\xAB" * 512)
        result = cam.get_partial_object(0x1234, 0, 512)
        assert result == b"\xAB" * 512
        args = cam._transport.receive.call_args
        assert args[0][0] == PTPOpCode.GET_PARTIAL_OBJECT
        assert args[0][1] == [0x1234, 0, 512]

    def test_error(self):
        cam = _make_camera()
        cam._transport.receive.return_value = (_err_resp(), b"")
        with pytest.raises(TransactionError):
            cam.get_partial_object(1, 0, 100)


# ══════════════════════════════════════════════════════════════════════════
# Phase 3 — SDIO single-property query
# ══════════════════════════════════════════════════════════════════════════

class TestGetExtDeviceProp:
    def test_round_trip(self):
        cam = _make_camera()
        # Build a minimal DevicePropInfo payload for ISO (0xD21E), UINT32, value=0x190
        prop = bytearray()
        prop += struct.pack("<H", DeviceProperty.ISO)
        prop += struct.pack("<H", DataType.UINT32)
        prop += struct.pack("B", 1)   # get_set = RW
        prop += struct.pack("B", 1)   # is_enable
        prop += struct.pack("<I", 0x190)  # default
        prop += struct.pack("<I", 0x190)  # current
        prop += struct.pack("B", 0)   # form_flag = none
        cam._transport.receive.return_value = (_ok_resp(), bytes(prop))
        info = cam.get_ext_device_prop(DeviceProperty.ISO)
        assert info.property_code == DeviceProperty.ISO
        assert info.current_value == 0x190
        args = cam._transport.receive.call_args
        assert args[0][0] == SDIOOpCode.GET_EXT_DEVICE_PROP
        assert args[0][1] == [DeviceProperty.ISO]

    def test_error(self):
        cam = _make_camera()
        cam._transport.receive.return_value = (_err_resp(), b"")
        with pytest.raises(PropertyError):
            cam.get_ext_device_prop(DeviceProperty.ISO)


# ══════════════════════════════════════════════════════════════════════════
# Phase 4 — Content management
# ══════════════════════════════════════════════════════════════════════════

def _make_content_info_payload(items: list[dict]) -> bytes:
    """Build a minimal GetContentInfoList response payload."""
    buf = struct.pack("<I", len(items))
    for item in items:
        buf += struct.pack("<I", item["content_id"])
        buf += struct.pack("<H", item.get("format_code", 0x3801))
        buf += struct.pack("<I", 0)  # padding
        buf += struct.pack("<Q", item.get("size", 1000))
        # PTP string: char count (uint8) + UTF-16LE pairs + null
        name = item.get("file_name", "IMG_0001.JPG")
        encoded = name.encode("utf-16-le") + b"\x00\x00"
        buf += bytes([len(name) + 1]) + encoded
        dt = item.get("date_time", "20241215T120000")
        encoded_dt = dt.encode("utf-16-le") + b"\x00\x00"
        buf += bytes([len(dt) + 1]) + encoded_dt
    return buf


class TestGetContentInfoList:
    def test_parses_items(self):
        cam = _make_camera()
        payload = _make_content_info_payload([
            {"content_id": 1, "file_name": "IMG_0001.JPG", "size": 5000, "format_code": 0x3801},
            {"content_id": 2, "file_name": "VID_0001.MP4", "size": 500000, "format_code": 0x300D},
        ])
        cam._transport.receive.return_value = (_ok_resp(), payload)
        items = cam.get_content_info_list()
        assert len(items) == 2
        assert items[0]["content_id"] == 1
        assert items[0]["file_name"] == "IMG_0001.JPG"
        assert items[1]["content_id"] == 2

    def test_opcode_sent(self):
        cam = _make_camera()
        cam._transport.receive.return_value = (_ok_resp(), struct.pack("<I", 0))
        cam.get_content_info_list(storage_id=0x1, start_index=0, max_count=10)
        args = cam._transport.receive.call_args
        assert args[0][0] == SDIOOpCode.GET_CONTENT_INFO_LIST
        assert args[0][1] == [0x1, 0, 10]

    def test_error(self):
        cam = _make_camera()
        cam._transport.receive.return_value = (_err_resp(), b"")
        with pytest.raises(TransactionError):
            cam.get_content_info_list()


class TestGetContentData:
    def test_success(self):
        cam = _make_camera()
        data = b"\xFF\xD8" + b"\x00" * 100
        cam._transport.receive.return_value = (_ok_resp(), data)
        result = cam.get_content_data(42)
        assert result == data
        args = cam._transport.receive.call_args
        assert args[0][0] == SDIOOpCode.GET_CONTENT_DATA
        assert args[0][1] == [42]

    def test_error(self):
        cam = _make_camera()
        cam._transport.receive.return_value = (_err_resp(), b"")
        with pytest.raises(TransactionError):
            cam.get_content_data(1)


class TestDeleteContent:
    def test_success(self):
        cam = _make_camera()
        cam._transport.send.return_value = _ok_resp()
        cam.delete_content(99)
        args = cam._transport.send.call_args
        assert args[0][0] == SDIOOpCode.DELETE_CONTENT
        assert args[0][1] == [99]

    def test_error(self):
        cam = _make_camera()
        cam._transport.send.return_value = _err_resp()
        with pytest.raises(TransactionError):
            cam.delete_content(1)


# ══════════════════════════════════════════════════════════════════════════
# Phase 5 — Control helpers
# ══════════════════════════════════════════════════════════════════════════

class TestExposureLockHelpers:
    def test_press_ael(self):
        cam = _make_camera()
        cam.press_ael()
        args = cam._transport.send.call_args
        assert args[0][1] == [DeviceProperty.AE_LOCK]

    def test_release_ael(self):
        cam = _make_camera()
        cam.release_ael()
        args = cam._transport.send.call_args
        assert args[0][1] == [DeviceProperty.AE_LOCK]

    def test_press_awbl(self):
        cam = _make_camera()
        cam.press_awbl()
        args = cam._transport.send.call_args
        assert args[0][1] == [DeviceProperty.AWB_LOCK]

    def test_release_awbl(self):
        cam = _make_camera()
        cam.release_awbl()
        args = cam._transport.send.call_args
        assert args[0][1] == [DeviceProperty.AWB_LOCK]


class TestFocusMagnifierHelpers:
    def test_enable(self):
        cam = _make_camera()
        cam.enable_focus_magnifier()
        args = cam._transport.send.call_args
        assert args[0][1] == [DeviceProperty.FOCUS_MAGNIFIER]

    def test_disable(self):
        cam = _make_camera()
        cam.disable_focus_magnifier()
        args = cam._transport.send.call_args
        assert args[0][1] == [DeviceProperty.FOCUS_MAGNIFIER_CANCEL]

    def test_increase(self):
        cam = _make_camera()
        cam.focus_mag_increase()
        args = cam._transport.send.call_args
        assert args[0][1] == [DeviceProperty.FOCUS_MAG_PLUS]

    def test_decrease(self):
        cam = _make_camera()
        cam.focus_mag_decrease()
        args = cam._transport.send.call_args
        assert args[0][1] == [DeviceProperty.FOCUS_MAG_MINUS]


class TestRemoteKeyHelpers:
    def _assert_press_release(self, cam, prop_code):
        calls = cam._transport.send.call_args_list
        prop_calls = [c for c in calls if c[0][1] == [prop_code]]
        assert len(prop_calls) == 2  # press then release

    def test_up(self):
        cam = _make_camera()
        cam.remote_key_up()
        self._assert_press_release(cam, DeviceProperty.REMOTE_KEY_UP)

    def test_down(self):
        cam = _make_camera()
        cam.remote_key_down()
        self._assert_press_release(cam, DeviceProperty.REMOTE_KEY_DOWN)

    def test_left(self):
        cam = _make_camera()
        cam.remote_key_left()
        self._assert_press_release(cam, DeviceProperty.REMOTE_KEY_LEFT)

    def test_right(self):
        cam = _make_camera()
        cam.remote_key_right()
        self._assert_press_release(cam, DeviceProperty.REMOTE_KEY_RIGHT)


class TestSetFocusPoint:
    def test_packs_xy(self):
        cam = _make_camera()
        cam.set_focus_point(100, 150)
        args = cam._transport.send.call_args
        assert args[0][1] == [DeviceProperty.FOCUS_AREA_XY]
        # Verify data: x=100 (0x0064), y=150 (0x0096)
        data_sent = args[0][2]
        x, y = struct.unpack_from("<hh", data_sent, 0)
        assert x == 100
        assert y == 150

    def test_negative_coords(self):
        cam = _make_camera()
        cam.set_focus_point(-50, -80)
        args = cam._transport.send.call_args
        data_sent = args[0][2]
        x, y = struct.unpack_from("<hh", data_sent, 0)
        assert x == -50
        assert y == -80


class TestCustomWBHelpers:
    def test_standby(self):
        cam = _make_camera()
        cam.custom_wb_standby()
        args = cam._transport.send.call_args
        assert args[0][1] == [DeviceProperty.CUSTOM_WB_STANDBY]

    def test_cancel(self):
        cam = _make_camera()
        cam.custom_wb_cancel()
        args = cam._transport.send.call_args
        assert args[0][1] == [DeviceProperty.CUSTOM_WB_STANDBY_CANCEL]

    def test_execute(self):
        cam = _make_camera()
        cam.custom_wb_execute()
        args = cam._transport.send.call_args
        assert args[0][1] == [DeviceProperty.CUSTOM_WB_EXECUTE]


class TestMovieToggle:
    def test_toggle(self):
        cam = _make_camera()
        cam.toggle_movie()
        args = cam._transport.send.call_args
        assert args[0][1] == [DeviceProperty.MOVIE_REC_TOGGLE]


class TestZoomFocusPresets:
    def test_save(self):
        cam = _make_camera()
        cam.save_zoom_focus_position()
        args = cam._transport.send.call_args
        assert args[0][1] == [DeviceProperty.SAVE_ZOOM_FOCUS_POSITION]

    def test_load(self):
        cam = _make_camera()
        cam.load_zoom_focus_position()
        args = cam._transport.send.call_args
        assert args[0][1] == [DeviceProperty.LOAD_ZOOM_FOCUS_POSITION]


class TestContinuousZoomFocus:
    def test_zoom_continuous_positive(self):
        cam = _make_camera()
        cam.zoom_continuous(10000)
        args = cam._transport.send.call_args
        assert args[0][1] == [DeviceProperty.ZOOM_RANGE]
        val = struct.unpack("<h", args[0][2])[0]
        assert val == 10000

    def test_zoom_continuous_negative(self):
        cam = _make_camera()
        cam.zoom_continuous(-5000)
        args = cam._transport.send.call_args
        val = struct.unpack("<h", args[0][2])[0]
        assert val == -5000

    def test_focus_continuous(self):
        cam = _make_camera()
        cam.focus_continuous(3000)
        args = cam._transport.send.call_args
        assert args[0][1] == [DeviceProperty.FOCUS_RANGE]
        val = struct.unpack("<h", args[0][2])[0]
        assert val == 3000

    def test_clamps_to_int16_range(self):
        cam = _make_camera()
        cam.zoom_continuous(99999)
        args = cam._transport.send.call_args
        val = struct.unpack("<h", args[0][2])[0]
        assert val == 32767


# ══════════════════════════════════════════════════════════════════════════
# Phase 6 — Extended property setters/getters
# ══════════════════════════════════════════════════════════════════════════

class TestFocusAdvanced:
    def test_set_focus_mode_setting(self):
        cam = _make_camera()
        cam.set_focus_mode_setting(0x0002)
        args = cam._transport.send.call_args
        assert args[0][1] == [DeviceProperty.FOCUS_MODE_SETTING]

    def test_set_af_transition_speed(self):
        cam = _make_camera()
        cam.set_af_transition_speed(4)
        args = cam._transport.send.call_args
        assert args[0][1] == [DeviceProperty.AF_TRANSITION_SPEED]

    def test_set_af_subject_shift(self):
        cam = _make_camera()
        cam.set_af_subject_shift_sensitivity(3)
        args = cam._transport.send.call_args
        assert args[0][1] == [DeviceProperty.AF_SUBJECT_SHIFT_SENSITIVITY]

    def test_get_focal_position(self):
        cam = _make_camera()
        data = _prop_data_single(DeviceProperty.FOCAL_POSITION_CURRENT, DataType.UINT16, 0x0200)
        cam._transport.receive.return_value = (_ok_resp(), data)
        val = cam.get_focal_position()
        assert val == 0x0200


class TestWBAdvanced:
    def test_set_wb_preset_color_temp(self):
        cam = _make_camera()
        cam.set_wb_preset_color_temp(5600)
        args = cam._transport.send.call_args
        assert args[0][1] == [DeviceProperty.WB_PRESET_COLOR_TEMP]

    def test_set_wb_r_gain(self):
        cam = _make_camera()
        cam.set_wb_r_gain(0x100)
        args = cam._transport.send.call_args
        assert args[0][1] == [DeviceProperty.WB_R_GAIN]

    def test_set_wb_b_gain(self):
        cam = _make_camera()
        cam.set_wb_b_gain(0x100)
        args = cam._transport.send.call_args
        assert args[0][1] == [DeviceProperty.WB_B_GAIN]


class TestSQMode:
    def test_set_sq_mode(self):
        cam = _make_camera()
        cam.set_sq_mode(0x01)
        args = cam._transport.send.call_args
        assert args[0][1] == [DeviceProperty.SQ_MODE_SETTING]

    def test_set_sq_frame_rate(self):
        cam = _make_camera()
        cam.set_sq_frame_rate(0x05)
        args = cam._transport.send.call_args
        assert args[0][1] == [DeviceProperty.SQ_FRAME_RATE]

    def test_set_sq_record_setting(self):
        cam = _make_camera()
        cam.set_sq_record_setting(0x0A)
        args = cam._transport.send.call_args
        assert args[0][1] == [DeviceProperty.SQ_RECORD_SETTING]


class TestMediaSlotStatus:
    def _make_slots_data(self) -> bytes:
        """Build payload with SLOT1_STATUS=1, SLOT1_REMAINING_SHOTS=250, SLOT1_REMAINING_TIME=300."""
        props = [
            (DeviceProperty.MEDIA_SLOT1_STATUS, DataType.UINT16, 0x0001, "<H"),
            (DeviceProperty.MEDIA_SLOT1_REMAINING_SHOTS, DataType.UINT32, 250, "<I"),
            (DeviceProperty.MEDIA_SLOT1_REMAINING_TIME, DataType.UINT32, 300, "<I"),
        ]
        buf = bytearray()
        for code, dt, val, fmt in props:
            p = bytearray()
            p += struct.pack("<H", code)
            p += struct.pack("<H", dt)
            p += struct.pack("B", 0)  # RO
            p += struct.pack("B", 1)
            p += struct.pack(fmt, val)
            p += struct.pack(fmt, val)
            p += struct.pack("B", 0)
            buf += p
        return struct.pack("<Q", len(props)) + bytes(buf)

    def test_get_media_slot1_status(self):
        cam = _make_camera()
        cam._transport.receive.return_value = (_ok_resp(), self._make_slots_data())
        result = cam.get_media_slot1_status()
        assert result["status"] == 0x0001
        assert result["remaining_shots"] == 250
        assert result["remaining_time_s"] == 300


class TestBatteryInfo:
    def _make_battery_data(self) -> bytes:
        props = [
            (DeviceProperty.BATTERY_REMAINING_MINUTES, DataType.UINT16, 45, "<H"),
            (DeviceProperty.BATTERY_REMAINING_VOLTAGE, DataType.UINT16, 0x1A4, "<H"),
            (DeviceProperty.TOTAL_BATTERY_REMAINING, DataType.UINT16, 80, "<H"),
            (DeviceProperty.POWER_SOURCE, DataType.UINT8, 0x01, "B"),
        ]
        buf = bytearray()
        for code, dt, val, fmt in props:
            p = bytearray()
            p += struct.pack("<H", code)
            p += struct.pack("<H", dt)
            p += struct.pack("B", 0)
            p += struct.pack("B", 1)
            p += struct.pack(fmt, val)
            p += struct.pack(fmt, val)
            p += struct.pack("B", 0)
            buf += p
        return struct.pack("<Q", len(props)) + bytes(buf)

    def test_returns_dict(self):
        cam = _make_camera()
        cam._transport.receive.return_value = (_ok_resp(), self._make_battery_data())
        result = cam.get_battery_info()
        assert result["remaining_minutes"] == 45
        assert result["total_remaining"] == 80


class TestSystemInfo:
    def test_get_software_version(self):
        cam = _make_camera()
        # Build a string property for SOFTWARE_VERSION
        prop_code = DeviceProperty.SOFTWARE_VERSION
        version_str = "1.00"
        encoded = version_str.encode("utf-16-le") + b"\x00\x00"
        str_payload = bytes([len(version_str) + 1]) + encoded
        p = bytearray()
        p += struct.pack("<H", prop_code)
        p += struct.pack("<H", DataType.STR)
        p += struct.pack("B", 0)
        p += struct.pack("B", 1)
        p += str_payload  # default
        p += str_payload  # current
        p += struct.pack("B", 0)
        data = struct.pack("<Q", 1) + bytes(p)
        cam._transport.receive.return_value = (_ok_resp(), data)
        result = cam.get_software_version()
        assert result == "1.00"


# ══════════════════════════════════════════════════════════════════════════
# Phase 7 — Event system
# ══════════════════════════════════════════════════════════════════════════

class TestEventDispatcher:
    def _make_transport(self):
        t = MagicMock()
        return t

    def test_dispatches_event_to_callback(self):
        transport = self._make_transport()
        received: list[PTPEvent] = []

        prop_event = PTPEvent(
            code=SDIOEventCode.PROPERTY_CHANGED,
            session_id=1,
            transaction_id=1,
            params=[DeviceProperty.ISO, 0, 0, 0, 0],
        )
        # First call times out, second returns event, all subsequent time out
        from pysonycam.exceptions import TimeoutError as CamTimeout
        call_count = [0]

        def _wait_event(timeout_ms):
            call_count[0] += 1
            if call_count[0] == 1:
                raise CamTimeout("timeout")
            if call_count[0] == 2:
                return prop_event
            raise CamTimeout("timeout")

        transport.wait_event.side_effect = _wait_event

        dispatcher = _EventDispatcher(transport)
        dispatcher.register(SDIOEventCode.PROPERTY_CHANGED, received.append)
        dispatcher.start()

        # Wait until callback fires
        deadline = time.monotonic() + 2.0
        while not received and time.monotonic() < deadline:
            time.sleep(0.05)

        dispatcher.stop()
        assert len(received) == 1
        assert received[0].code == SDIOEventCode.PROPERTY_CHANGED
        assert received[0].params[0] == DeviceProperty.ISO

    def test_thread_stops_cleanly(self):
        transport = self._make_transport()
        from pysonycam.exceptions import TimeoutError as CamTimeout
        transport.wait_event.side_effect = CamTimeout("timeout")

        dispatcher = _EventDispatcher(transport)
        dispatcher.start()
        assert dispatcher.is_running
        dispatcher.stop()
        assert not dispatcher.is_running

    def test_camera_on_event_interface(self):
        cam = _make_camera()
        events: list = []
        cam.on_event(SDIOEventCode.PROPERTY_CHANGED, events.append)
        assert SDIOEventCode.PROPERTY_CHANGED in cam._event_dispatcher._callbacks

    def test_camera_start_stop_listener(self):
        cam = _make_camera()
        from pysonycam.exceptions import TimeoutError as CamTimeout
        cam._transport.wait_event.side_effect = CamTimeout("timeout")
        cam.start_event_listener()
        assert cam._event_dispatcher.is_running
        cam.stop_event_listener()
        assert not cam._event_dispatcher.is_running

    def test_disconnect_stops_listener(self):
        cam = _make_camera()
        from pysonycam.exceptions import TimeoutError as CamTimeout
        cam._transport.wait_event.side_effect = CamTimeout("timeout")
        cam.start_event_listener()
        cam.disconnect()
        assert not cam._event_dispatcher.is_running


# ══════════════════════════════════════════════════════════════════════════
# Phase 9 — Medium-priority SDIO operations
# ══════════════════════════════════════════════════════════════════════════

class TestGetVendorCodeVersion:
    def test_returns_version(self):
        cam = _make_camera()
        cam._transport.receive.return_value = (_ok_resp(), struct.pack("<H", 0x012C))
        version = cam.get_vendor_code_version()
        assert version == 0x012C
        args = cam._transport.receive.call_args
        assert args[0][0] == SDIOOpCode.GET_VENDOR_CODE_VERSION

    def test_empty_payload(self):
        cam = _make_camera()
        cam._transport.receive.return_value = (_ok_resp(), b"")
        assert cam.get_vendor_code_version() == 0


class TestOperationResultsSupported:
    def test_supported(self):
        cam = _make_camera()
        cam._transport.send.return_value = _ok_resp()
        assert cam.operation_results_supported() is True

    def test_not_supported(self):
        cam = _make_camera()
        cam._transport.send.return_value = _err_resp(ResponseCode.OPERATION_NOT_SUPPORTED)
        assert cam.operation_results_supported() is False


class TestGetLensInformation:
    def test_success(self):
        cam = _make_camera()
        cam._transport.receive.return_value = (_ok_resp(), b"\x01" * 32)
        result = cam.get_lens_information()
        assert len(result) == 32
        args = cam._transport.receive.call_args
        assert args[0][0] == SDIOOpCode.GET_LENS_INFORMATION

    def test_error(self):
        cam = _make_camera()
        cam._transport.receive.return_value = (_err_resp(), b"")
        with pytest.raises(TransactionError):
            cam.get_lens_information()

"""Tests for pysonycam.camera — SonyCamera high-level API (mocked transport)."""

import struct
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from pysonycam.camera import SonyCamera
from pysonycam.constants import (
    DeviceProperty,
    ExposureMode,
    OperatingMode,
    ResponseCode,
    SaveMedia,
    SDIOOpCode,
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

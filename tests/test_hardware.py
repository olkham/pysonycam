"""Hardware integration tests — require a real Sony camera connected via USB.

These tests are SKIPPED by default. Run them with:

    pytest tests/test_hardware.py -v --run-hardware

The camera must be:
  1. Powered on and connected via USB
  2. Set to "PC Remote" or "Remote Shooting" USB mode
  3. Using the WinUSB driver (installed via Zadig on Windows)

WARNING: These tests will control the camera — they may take photos, change
settings, and stream LiveView frames.  Make sure the lens cap is off and
the camera is in a safe state.
"""

from __future__ import annotations

import logging
import os
import tempfile
import time
from pathlib import Path

import pytest

from pysonycam import SonyCamera, DeviceProperty, format_value, property_name
from pysonycam.constants import (
    DataType,
    ExposureMode,
    OperatingMode,
    SaveMedia,
    SHUTTER_SPEED_TABLE,
    F_NUMBER_TABLE,
    ISO_TABLE,
)
from pysonycam.exceptions import SonyCameraError, PropertyError
from pysonycam.parser import DevicePropInfo

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def camera():
    """Connect to the camera once for the entire test module.

    Yields a connected and authenticated SonyCamera instance.
    Disconnects automatically after all tests in this module complete.
    """
    cam = SonyCamera()
    try:
        cam.connect()
    except SonyCameraError as exc:
        pytest.skip(f"Cannot connect to camera: {exc}")
    try:
        cam.authenticate()
    except SonyCameraError as exc:
        cam.disconnect()
        pytest.skip(f"Authentication failed: {exc}")

    yield cam

    cam.disconnect()


@pytest.fixture
def tmp_output(tmp_path):
    """Provide a temporary directory for captured images."""
    return tmp_path


# ══════════════════════════════════════════════════════════════════════════
# Connection & Authentication
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.hardware
class TestConnection:
    def test_camera_is_connected(self, camera: SonyCamera):
        assert camera.is_connected is True

    def test_camera_is_authenticated(self, camera: SonyCamera):
        assert camera._authenticated is True


# ══════════════════════════════════════════════════════════════════════════
# Property Reading
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.hardware
class TestPropertyReading:
    def test_get_all_properties_returns_dict(self, camera: SonyCamera):
        props = camera.get_all_properties()
        assert isinstance(props, dict)
        assert len(props) > 0
        logger.info("Camera reports %d properties", len(props))

    def test_all_properties_are_device_prop_info(self, camera: SonyCamera):
        props = camera.get_all_properties()
        for code, info in props.items():
            assert isinstance(code, int)
            assert isinstance(info, DevicePropInfo)

    def test_battery_level_readable(self, camera: SonyCamera):
        info = camera.get_property(DeviceProperty.BATTERY_LEVEL)
        assert info is not None
        assert isinstance(info.current_value, int)
        assert info.current_value > 0
        logger.info(
            "Battery: %s", format_value(DeviceProperty.BATTERY_LEVEL, info.current_value)
        )

    def test_exposure_mode_readable(self, camera: SonyCamera):
        info = camera.get_property(DeviceProperty.EXPOSURE_MODE)
        assert info is not None
        assert isinstance(info.current_value, int)
        logger.info(
            "Exposure mode: %s",
            format_value(DeviceProperty.EXPOSURE_MODE, info.current_value),
        )

    def test_f_number_readable(self, camera: SonyCamera):
        info = camera.get_property(DeviceProperty.F_NUMBER)
        assert info is not None
        logger.info(
            "F-number: %s", format_value(DeviceProperty.F_NUMBER, info.current_value)
        )

    def test_shutter_speed_readable(self, camera: SonyCamera):
        info = camera.get_property(DeviceProperty.SHUTTER_SPEED)
        assert info is not None
        logger.info(
            "Shutter: %s",
            format_value(DeviceProperty.SHUTTER_SPEED, info.current_value),
        )

    def test_iso_readable(self, camera: SonyCamera):
        info = camera.get_property(DeviceProperty.ISO)
        assert info is not None
        logger.info("ISO: %s", format_value(DeviceProperty.ISO, info.current_value))

    def test_nonexistent_property_raises(self, camera: SonyCamera):
        with pytest.raises(PropertyError):
            camera.get_property(0x0001)  # invalid code

    def test_property_formatting(self, camera: SonyCamera):
        """All readable properties should format without errors."""
        props = camera.get_all_properties()
        for code, info in props.items():
            name = property_name(code)
            assert isinstance(name, str)
            formatted = format_value(code, info.current_value)
            assert isinstance(formatted, str)


# ══════════════════════════════════════════════════════════════════════════
# LiveView
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.hardware
class TestLiveView:
    def test_liveview_status(self, camera: SonyCamera):
        info = camera.get_property(DeviceProperty.LIVEVIEW_STATUS)
        logger.info("LiveView status: %s", info.current_value)

    def test_get_single_frame(self, camera: SonyCamera):
        """Grab a single LiveView frame — should be a valid JPEG."""
        # Ensure camera is in still mode with LiveView active
        camera.set_mode("still")
        camera._wait_for_liveview()

        # The first few frames after LiveView starts can be empty while the
        # camera's preview pipeline warms up — retry up to 10 times.
        frame = b""
        for attempt in range(10):
            frame = camera.get_liveview_frame()
            if frame:
                break
            time.sleep(0.3)

        assert isinstance(frame, bytes)
        assert len(frame) > 0, "LiveView frame is empty after 10 retries"
        # JPEG files begin with FFD8
        assert frame[:2] == b"\xFF\xD8", "Frame is not a valid JPEG"
        logger.info("LiveView frame: %d bytes", len(frame))

    def test_liveview_stream_multiple(self, camera: SonyCamera):
        """Stream 5 LiveView frames."""
        camera.set_mode("still")
        camera._wait_for_liveview()

        frames = list(camera.liveview_stream(count=5))
        assert len(frames) == 5
        for i, f in enumerate(frames):
            assert len(f) > 0
            assert f[:2] == b"\xFF\xD8"
            logger.info("Frame %d: %d bytes", i, len(f))

    def test_liveview_frame_save(self, camera: SonyCamera, tmp_output):
        """Grab a frame and save it as a file."""
        camera.set_mode("still")
        camera._wait_for_liveview()

        frame = b""
        for attempt in range(10):
            frame = camera.get_liveview_frame()
            if frame:
                break
            time.sleep(0.3)

        assert len(frame) > 0, "LiveView frame is empty after retries"
        out = tmp_output / "liveview_test.jpg"
        out.write_bytes(frame)
        assert out.exists()
        assert out.stat().st_size > 0
        logger.info("Saved LiveView frame to %s (%d bytes)", out, len(frame))


# ══════════════════════════════════════════════════════════════════════════
# Photo Capture
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.hardware
class TestCapture:
    def test_capture_returns_image_data(self, camera: SonyCamera, tmp_output):
        """Take a photo and verify we get JPEG data back."""
        camera.set_mode("still")
        camera._wait_for_liveview()

        out_file = tmp_output / "test_capture.jpg"
        data = camera.capture(output_path=str(out_file), fast_mode=True)

        assert isinstance(data, bytes)
        assert len(data) > 1000, "Image data too small — likely not a real photo"
        # JPEG or raw — check for JPEG SOI marker
        if data[:2] == b"\xFF\xD8":
            logger.info("Captured JPEG: %d bytes", len(data))
        else:
            logger.info("Captured non-JPEG (RAW?): %d bytes", len(data))

        assert out_file.exists()
        assert out_file.stat().st_size == len(data)
        logger.info("Saved to %s", out_file)

    def test_capture_to_memory_only(self, camera: SonyCamera):
        """Capture without saving to disk — just return bytes."""
        camera.set_mode("still")
        camera._wait_for_liveview()

        data = camera.capture(fast_mode=True)
        assert isinstance(data, bytes)
        assert len(data) > 1000
        logger.info("Capture to memory: %d bytes", len(data))


# ══════════════════════════════════════════════════════════════════════════
# Zoom Control (only runs if camera supports zoom)
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.hardware
class TestZoom:
    def test_zoom_in_and_stop(self, camera: SonyCamera):
        """Send zoom-in then stop — should not raise."""
        try:
            camera.zoom_in(1)
            import time
            time.sleep(0.5)
            camera.zoom_stop()
        except SonyCameraError:
            pytest.skip("Camera may not support motorized zoom")

    def test_zoom_out_and_stop(self, camera: SonyCamera):
        try:
            camera.zoom_out(1)
            import time
            time.sleep(0.5)
            camera.zoom_stop()
        except SonyCameraError:
            pytest.skip("Camera may not support motorized zoom")


# ══════════════════════════════════════════════════════════════════════════
# Property Summary (diagnostic, always passes)
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.hardware
class TestDiagnostics:
    def test_print_camera_summary(self, camera: SonyCamera):
        """Print a full property dump — useful for debugging."""
        props = camera.get_all_properties()
        lines = []
        for code, info in sorted(props.items()):
            name = property_name(code)
            val = format_value(code, info.current_value)
            rw = "RW" if info.is_writable else "RO"
            en = "OK" if info.is_valid else "--"
            lines.append(f"  0x{code:04X}  {name:30s}  {val:25s}  [{rw}] [{en}]")
        summary = "\n".join(lines)
        logger.info("Camera Property Dump (%d props):\n%s", len(props), summary)
        assert len(props) > 0

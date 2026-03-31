"""
High-level Sony camera control API.

Provides a Pythonic interface for:
- Connecting / disconnecting via USB
- Sony SDIO authentication
- Reading and writing camera properties (exposure, ISO, aperture, etc.)
- Capturing still images and downloading them
- Streaming LiveView JPEG frames
- Controlling zoom, focus, movie recording, and more

Usage::

    from sony_camera_control import SonyCamera

    with SonyCamera() as camera:
        camera.authenticate()
        camera.set_mode("still")

        # Read settings
        print(camera.get_all_properties())

        # Change settings
        camera.set_exposure_mode(ExposureMode.APERTURE_PRIORITY)
        camera.set_iso(400)

        # Capture a photo
        camera.capture("photo.jpg")

        # Stream LiveView
        for frame in camera.liveview_stream(count=10):
            with open("frame.jpg", "wb") as f:
                f.write(frame)
"""

from __future__ import annotations

import logging
import struct
import time
from pathlib import Path
from typing import Iterator, Optional, Union

from sony_camera_control.constants import (
    DeviceProperty,
    ExposureMode,
    LiveViewMode,
    OperatingMode,
    PTPOpCode,
    ResponseCode,
    SDIOEventCode,
    SDIOOpCode,
    SDI_VERSION_V3,
    SHOT_OBJECT_HANDLE,
    LIVEVIEW_OBJECT_HANDLE,
    SaveMedia,
    DATA_TYPE_SIZE,
    SHUTTER_SPEED_TABLE,
    F_NUMBER_TABLE,
    ISO_TABLE,
)
from sony_camera_control.exceptions import (
    AuthenticationError,
    PropertyError,
    SonyCameraError,
    TransactionError,
)
from sony_camera_control.parser import (
    DevicePropInfo,
    parse_all_device_props,
    parse_liveview_image,
)
from sony_camera_control.ptp import PTPTransport, PTPResponse

logger = logging.getLogger(__name__)


class SonyCamera:
    """High-level interface for controlling a Sony camera over PTP/USB.

    Can be used as a context manager for automatic connection cleanup::

        with SonyCamera() as cam:
            cam.authenticate()
            cam.capture("photo.jpg")

    Parameters
    ----------
    bus : int, optional
        USB bus number (0 = auto-detect first Sony camera).
    device : int, optional
        USB device address (0 = auto-detect).
    timeout_ms : int, optional
        USB transfer timeout in milliseconds (default 5000).
    version : int, optional
        SDIO extension version to negotiate (default = v3, 0x012C).
    """

    def __init__(
        self,
        bus: int = 0,
        device: int = 0,
        timeout_ms: int = 5000,
        version: int = SDI_VERSION_V3,
    ):
        self._transport = PTPTransport(bus=bus, device=device, timeout_ms=timeout_ms)
        self._version = version
        self._properties: dict[int, DevicePropInfo] = {}
        self._authenticated = False

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> SonyCamera:
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.disconnect()

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Open a USB connection and start a PTP session."""
        self._transport.connect()
        self._open_session()

    def disconnect(self) -> None:
        """Close the PTP session and USB connection."""
        if self._transport.is_connected:
            try:
                self._close_session()
            except SonyCameraError:
                pass
            self._transport.disconnect()
        self._authenticated = False

    @property
    def is_connected(self) -> bool:
        return self._transport.is_connected

    # ------------------------------------------------------------------
    # Session & authentication
    # ------------------------------------------------------------------

    def _open_session(self, session_id: int = 1) -> None:
        """Send PTP OpenSession command."""
        resp = self._transport.send(PTPOpCode.OPEN_SESSION, [session_id])
        if resp.code != ResponseCode.OK:
            raise TransactionError(
                f"OpenSession failed: 0x{resp.code:04X}", resp.code
            )
        logger.info("PTP session opened (id=%d)", session_id)

    def _close_session(self) -> None:
        """Send PTP CloseSession command."""
        self._transport.send(PTPOpCode.CLOSE_SESSION)
        logger.info("PTP session closed")

    def authenticate(self) -> None:
        """Perform the Sony SDIO authentication handshake.

        This must be called after :meth:`connect` (or entering the context
        manager) before any camera control commands will work.

        Raises
        ------
        AuthenticationError
            If the handshake fails or times out.
        """
        try:
            # Phase 1: SDIOConnect param=1
            self._transport.receive(SDIOOpCode.CONNECT, [1, 0, 0])

            # Phase 2: SDIOConnect param=2
            self._transport.receive(SDIOOpCode.CONNECT, [2, 0, 0])

            # Phase 3: Poll SDIOGetExtDeviceInfo until version matches
            version = 0
            max_attempts = 60
            for _ in range(max_attempts):
                resp, data = self._transport.receive(
                    SDIOOpCode.GET_EXT_DEVICE_INFO, [self._version]
                )
                if len(data) >= 2:
                    version = struct.unpack_from("<H", data, 0)[0]
                if version == self._version:
                    break
                time.sleep(0.05)
            else:
                raise AuthenticationError(
                    f"Version negotiation failed (wanted 0x{self._version:04X}, "
                    f"last got 0x{version:04X})"
                )

            # Phase 4: SDIOConnect param=3
            self._transport.receive(SDIOOpCode.CONNECT, [3, 0, 0])

            self._authenticated = True
            logger.info("Authentication successful (version=0x%04X)", self._version)

        except SonyCameraError:
            raise
        except Exception as exc:
            raise AuthenticationError(f"Authentication failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Property access
    # ------------------------------------------------------------------

    def get_all_properties(self) -> dict[int, DevicePropInfo]:
        """Read all device properties from the camera.

        Returns a dict mapping property code (int) -> DevicePropInfo.

        Example::

            props = camera.get_all_properties()
            for code, info in props.items():
                print(f"0x{code:04X}: {info}")
        """
        resp, data = self._transport.receive(SDIOOpCode.GET_ALL_EXT_DEVICE_INFO)
        self._properties = parse_all_device_props(data)
        return self._properties

    def get_property(self, prop_code: int) -> DevicePropInfo:
        """Read a single device property.

        Fetches all properties and returns the one matching *prop_code*.

        Parameters
        ----------
        prop_code : int
            A :class:`DeviceProperty` code.

        Raises
        ------
        PropertyError
            If the property is not found in the response.
        """
        self.get_all_properties()
        info = self._properties.get(prop_code)
        if info is None:
            raise PropertyError(f"Property 0x{prop_code:04X} not found")
        return info

    def set_property(self, prop_code: int, value: int, size: int = 0) -> None:
        """Set a device property value.

        Uses SDIOSetExtDevicePropValue (0x9205).

        Parameters
        ----------
        prop_code : int
            The property code from :class:`DeviceProperty`.
        value : int
            The value to set.
        size : int, optional
            Override the data size in bytes. If 0, auto-detected from property.
        """
        if size == 0:
            info = self._properties.get(prop_code)
            if info:
                size = DATA_TYPE_SIZE.get(info.data_type, 4)
            else:
                size = 4

        if size == 1:
            data = struct.pack("<B", value & 0xFF)
        elif size == 2:
            data = struct.pack("<H", value & 0xFFFF)
        else:
            data = struct.pack("<I", value & 0xFFFFFFFF)

        resp = self._transport.send(
            SDIOOpCode.SET_EXT_DEVICE_PROP_VALUE,
            [prop_code],
            data,
        )
        if resp.code != ResponseCode.OK:
            raise PropertyError(
                f"Failed to set property 0x{prop_code:04X}: response 0x{resp.code:04X}",
            )
        logger.debug("Set property 0x%04X = 0x%X (size=%d)", prop_code, value, size)

    def control_device(self, prop_code: int, value: int, size: int = 2) -> None:
        """Send a ControlDevice command (0x9207).

        Used for button presses (S1, S2, AE lock, etc.).

        Parameters
        ----------
        prop_code : int
            Property code for the control (e.g., DeviceProperty.S1_BUTTON).
        value : int
            Control value (e.g., 0x0002 = Press, 0x0001 = Release).
        size : int
            Payload size in bytes (default 2).
        """
        if size == 1:
            data = struct.pack("<B", value & 0xFF)
        elif size == 2:
            data = struct.pack("<H", value & 0xFFFF)
        else:
            data = struct.pack("<I", value & 0xFFFFFFFF)

        resp = self._transport.send(
            SDIOOpCode.CONTROL_DEVICE,
            [prop_code],
            data,
        )
        if resp.code != ResponseCode.OK:
            raise TransactionError(
                f"ControlDevice 0x{prop_code:04X} failed: 0x{resp.code:04X}",
                resp.code,
            )

    # ------------------------------------------------------------------
    # Convenience property setters
    # ------------------------------------------------------------------

    def set_mode(self, mode: Union[str, int, OperatingMode]) -> None:
        """Set the camera operating mode.

        Parameters
        ----------
        mode : str or int or OperatingMode
            One of ``"still"`` / ``"movie"`` / ``"transfer"`` / ``"standby"``,
            or an :class:`OperatingMode` enum value.
        """
        mode_map = {
            # STANDBY (0x01) is the host-control "ready to shoot stills" state.
            # STILL_REC (0x02) is the transient active-capture state, not set directly.
            "still": OperatingMode.STANDBY,
            "movie": OperatingMode.MOVIE_REC,
            "transfer": OperatingMode.CONTENTS_TRANSFER,
            "standby": OperatingMode.STANDBY,
        }
        if isinstance(mode, str):
            mode_val = mode_map.get(mode.lower())
            if mode_val is None:
                raise ValueError(
                    f"Unknown mode '{mode}'. Use: {', '.join(mode_map)}"
                )
        else:
            mode_val = int(mode)

        # Set dial to host control first
        self.set_property(DeviceProperty.POSITION_KEY, 0x01, size=1)

        # Wait for operating mode to become writable
        self._wait_for_property_enabled(DeviceProperty.OPERATING_MODE)

        # Set the mode
        self.set_property(DeviceProperty.OPERATING_MODE, mode_val, size=4)

        # Wait for the change to take effect
        self._wait_for_property_value(DeviceProperty.OPERATING_MODE, mode_val)
        logger.info("Camera mode set to %s", mode)

    def set_exposure_mode(self, mode: Union[int, ExposureMode]) -> None:
        """Set the exposure mode (M, P, A, S, Auto, etc.)."""
        self.set_property(DeviceProperty.EXPOSURE_MODE, int(mode), size=4)

    def set_iso(self, iso: int) -> None:
        """Set the ISO value. Use 0x00FFFFFF for AUTO."""
        self.set_property(DeviceProperty.ISO, iso, size=4)

    def set_aperture(self, f_number_code: int) -> None:
        """Set the aperture (F-number code from F_NUMBER_TABLE)."""
        self.set_property(DeviceProperty.F_NUMBER, f_number_code, size=2)

    def set_shutter_speed(self, shutter_code: int) -> None:
        """Set the shutter speed (code from SHUTTER_SPEED_TABLE)."""
        self.set_property(DeviceProperty.SHUTTER_SPEED, shutter_code, size=4)

    def set_white_balance(self, wb: int) -> None:
        """Set white balance mode."""
        self.set_property(DeviceProperty.WHITE_BALANCE, wb, size=2)

    def set_exposure_compensation(self, value: int) -> None:
        """Set exposure compensation (signed int16 code)."""
        self.set_property(DeviceProperty.EXPOSURE_COMPENSATION, value, size=2)

    def set_save_media(self, media: Union[int, SaveMedia] = SaveMedia.HOST) -> None:
        """Set where captured images are saved (host, camera, or both)."""
        self.set_property(DeviceProperty.SAVE_MEDIA, int(media), size=2)

    # ------------------------------------------------------------------
    # Photo capture
    # ------------------------------------------------------------------

    def capture(
        self,
        output_path: Optional[Union[str, Path]] = None,
        save_to_camera: bool = False,
        timeout: float = 30.0,
        fast_mode: bool = False,
    ) -> bytes:
        """Capture a still image and optionally save it to a file.

        The camera must be in Still Rec mode with LiveView active.

        Parameters
        ----------
        output_path : str or Path, optional
            File path to save the captured JPEG/RAW image.
        save_to_camera : bool, optional
            If True, images are saved to the camera's memory card.
            If False (default), images are transferred to the host.
        timeout : float
            Maximum seconds to wait for capture to complete.

        Returns
        -------
        bytes
            The raw image data.

        Example::

            # Capture and save
            camera.capture("photo.jpg")

            # Capture to memory
            data = camera.capture()
        """
        if not save_to_camera:
            self.set_save_media(SaveMedia.HOST)
            self._wait_for_property_value(DeviceProperty.SAVE_MEDIA, SaveMedia.HOST)

        # Wait for LiveView to be ready
        self._wait_for_liveview()

        # Shutter sequence: press S1 (half-press) -> press S2 (full) -> release
        # 1.5s delays match the reference scripts to ensure AF/AE settle and
        # the camera registers each button state before the next command.
        if not fast_mode:
            self.control_device(DeviceProperty.S1_BUTTON, 0x0002) # Half-press S1
            time.sleep(1.5)
            self.control_device(DeviceProperty.S2_BUTTON, 0x0002) # Press S2 (full shutter)
            time.sleep(1.5)
            self.control_device(DeviceProperty.S2_BUTTON, 0x0001) # Release S2
            time.sleep(1.5)
            self.control_device(DeviceProperty.S1_BUTTON, 0x0001) # Release S1
        else:
            self.control_device(DeviceProperty.S1_BUTTON, 0x0002) # Half-press S1
            time.sleep(0.1)
            self.control_device(DeviceProperty.S2_BUTTON, 0x0002) # Press S2 (full shutter)
            time.sleep(0.1)
            self.control_device(DeviceProperty.S2_BUTTON, 0x0001) # Release S2
            time.sleep(0.1)
            self.control_device(DeviceProperty.S1_BUTTON, 0x0001) # Release S1

        # Wait for capture completion (bit 15 = 0x8000 in ShootingFileInfo).
        # Log initial value so we can detect stale flags from previous sessions.
        initial_info = self.get_property(DeviceProperty.SHOOTING_FILE_INFO)
        initial_val = initial_info.current_value if isinstance(initial_info.current_value, int) else 0
        logger.debug("SHOOTING_FILE_INFO before capture: 0x%04X", initial_val)

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            info = self.get_property(DeviceProperty.SHOOTING_FILE_INFO)
            val = info.current_value if isinstance(info.current_value, int) else 0
            logger.debug("SHOOTING_FILE_INFO poll: 0x%04X", val)
            if val & 0x8000:
                break
            time.sleep(0.2)
        else:
            raise SonyCameraError("Capture timed out waiting for image")

        logger.info("Capture complete (SHOOTING_FILE_INFO=0x%04X), downloading image", val)

        # GetObjectInfo must be called before GetObject (required by Sony protocol).
        self.get_object_info(SHOT_OBJECT_HANDLE)

        # Download the image
        image_data = self.get_object(SHOT_OBJECT_HANDLE)

        if output_path is not None:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(image_data)
            logger.info("Image saved to %s (%d bytes)", path, len(image_data))

        return image_data

    def get_object(self, handle: int) -> bytes:
        """Download an object (image) from the camera by handle.

        Parameters
        ----------
        handle : int
            Object handle (e.g., ``SHOT_OBJECT_HANDLE = 0xFFFFC001``).

        Returns
        -------
        bytes
            The raw object data.
        """
        resp, data = self._transport.receive(PTPOpCode.GET_OBJECT, [handle])
        if resp.code != ResponseCode.OK:
            raise TransactionError(
                f"GetObject failed: 0x{resp.code:04X}", resp.code
            )
        return data

    def get_object_info(self, handle: int) -> bytes:
        """Get metadata about an object (before downloading it)."""
        resp, data = self._transport.receive(PTPOpCode.GET_OBJECT_INFO, [handle])
        return data

    # ------------------------------------------------------------------
    # LiveView
    # ------------------------------------------------------------------

    def get_liveview_frame(self) -> bytes:
        """Capture a single LiveView JPEG frame.

        Returns
        -------
        bytes
            A JPEG-encoded image of the current live preview.
        """
        resp, data = self._transport.receive(
            PTPOpCode.GET_OBJECT, [LIVEVIEW_OBJECT_HANDLE]
        )
        return parse_liveview_image(data)

    def liveview_stream(
        self,
        count: int = 0,
        interval: float = 0.0,
    ) -> Iterator[bytes]:
        """Yield LiveView JPEG frames as a generator.

        Parameters
        ----------
        count : int
            Number of frames to yield (0 = infinite).
        interval : float
            Minimum seconds between frames.

        Yields
        ------
        bytes
            JPEG image data for each frame.

        Example::

            for i, frame in enumerate(camera.liveview_stream(count=100)):
                with open(f"frame_{i:04d}.jpg", "wb") as f:
                    f.write(frame)
        """
        i = 0
        while count == 0 or i < count:
            try:
                frame = self.get_liveview_frame()
                if frame:
                    yield frame
                    i += 1
            except SonyCameraError:
                pass
            if interval > 0:
                time.sleep(interval)

    # ------------------------------------------------------------------
    # Zoom control
    # ------------------------------------------------------------------

    def zoom_in(self, speed: int = 1) -> None:
        """Zoom in (tele). Speed: 1=slow … 7=fast (signed byte, positive = tele)."""
        self.control_device(DeviceProperty.ZOOM, speed & 0x7F, size=1)

    def zoom_out(self, speed: int = 1) -> None:
        """Zoom out (wide). Speed: 1=slow … 7=fast (signed byte, negative = wide: 0xFF=-1)."""
        self.control_device(DeviceProperty.ZOOM, (-speed) & 0xFF, size=1)

    def zoom_stop(self) -> None:
        """Stop zooming."""
        self.control_device(DeviceProperty.ZOOM, 0x00, size=1)

    # ------------------------------------------------------------------
    # Focus control
    # ------------------------------------------------------------------

    def focus_near(self, step: int = 1) -> None:
        """Focus nearer. Step: 1=small, 3=medium, 7=large."""
        self.control_device(DeviceProperty.NEAR_FAR, 0x0200 | (step & 0xFF))

    def focus_far(self, step: int = 1) -> None:
        """Focus farther. Step: 1=small, 3=medium, 7=large."""
        self.control_device(DeviceProperty.NEAR_FAR, 0x0100 | (step & 0xFF))

    # ------------------------------------------------------------------
    # Movie recording
    # ------------------------------------------------------------------

    def start_movie(self) -> None:
        """Start movie recording (camera must be in Movie Rec mode)."""
        self.control_device(DeviceProperty.MOVIE_REC, 0x0002)

    def stop_movie(self) -> None:
        """Stop movie recording."""
        self.control_device(DeviceProperty.MOVIE_REC, 0x0001)

    # ------------------------------------------------------------------
    # Status helpers
    # ------------------------------------------------------------------

    @property
    def battery_level(self) -> DevicePropInfo | None:
        """Read the current battery level, or None if not supported."""
        try:
            return self.get_property(DeviceProperty.BATTERY_LEVEL)
        except PropertyError:
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _wait_for_property_enabled(
        self, prop_code: int, timeout: float = 10.0
    ) -> None:
        """Poll until a property's IsEnable flag becomes 1."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            info = self.get_property(prop_code)
            if info.is_valid:
                return
            time.sleep(0.1)
        raise PropertyError(
            f"Timed out waiting for property 0x{prop_code:04X} to become enabled"
        )

    def _wait_for_property_value(
        self, prop_code: int, expected: int, timeout: float = 10.0
    ) -> None:
        """Poll until a property's CurrentValue matches *expected*."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            info = self.get_property(prop_code)
            if info.current_value == expected:
                return
            time.sleep(0.1)
        raise PropertyError(
            f"Timed out waiting for property 0x{prop_code:04X} = 0x{expected:X}"
        )

    def _wait_for_liveview(self, timeout: float = 15.0) -> None:
        """Wait until LiveView status becomes active."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            info = self.get_property(DeviceProperty.LIVEVIEW_STATUS)
            if info.current_value == 0x01:
                return
            time.sleep(0.1)
        raise SonyCameraError("Timed out waiting for LiveView to become active")

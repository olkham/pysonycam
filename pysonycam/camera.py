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

    from pysonycam import SonyCamera

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

from pysonycam.constants import (
    DeviceProperty,
    DriveMode,
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
from pysonycam.exceptions import (
    AuthenticationError,
    PropertyError,
    SonyCameraError,
    TimeoutError,
    TransactionError,
)
from pysonycam.parser import (
    DevicePropInfo,
    parse_all_device_props,
    parse_liveview_image,
)
from pysonycam.ptp import PTPTransport, PTPResponse

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
        """Open a USB connection and start a PTP session.

        If the initial connection fails (e.g. stale session from a crash),
        a USB device reset is attempted before retrying.
        """
        self._transport.connect()
        try:
            self._open_session()
        except (TransactionError, TimeoutError) as exc:
            logger.warning("Session open failed (%s), resetting USB device...", exc)
            try:
                self._transport.reset_device()
            except Exception:
                pass
            time.sleep(2.0)
            self._transport.disconnect()
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

    def sdio_open_session(
        self, session_id: int = 1, function_mode: int = 0
    ) -> None:
        """Open a Sony SDIO session with a specific function mode.

        Uses SDIO_OpenSession (0x9210) instead of standard PTP OpenSession.
        This is required to enable Content Transfer Mode on the camera.

        Parameters
        ----------
        session_id : int
            PTP session ID (default 1).
        function_mode : int
            0 = Remote Control Mode (default),
            1 = Content Transfer Mode,
            2 = Remote Control with Transfer Mode (model-dependent).
        """
        # Reset transport state for new session (same as standard OpenSession)
        self._transport._session_id = 0
        self._transport._transaction_id = 0

        resp = self._transport.send(
            SDIOOpCode.SDIO_OPEN_SESSION, [session_id, function_mode]
        )
        if resp.code != ResponseCode.OK:
            raise TransactionError(
                f"SDIO_OpenSession failed: 0x{resp.code:04X}", resp.code
            )
        logger.info(
            "SDIO session opened (id=%d, function_mode=%d)",
            session_id,
            function_mode,
        )

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

        # Ensure no stale 0x8000 flag from a previous capture before firing the
        # shutter.  If the flag is already set, wait for it to clear first.
        self._wait_for_shooting_file_info_clear(timeout=timeout)

        self._fire_shutter(fast=fast_mode)

        # Now wait for SHOOTING_FILE_INFO bit 15 to be set (image ready on host).
        deadline = time.monotonic() + timeout
        val = 0
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

    def _fire_shutter(self, fast: bool = False) -> None:
        """Send the S1→S2→release sequence to the camera."""
        delay = 0.1 if fast else 1.5
        self.control_device(DeviceProperty.S1_BUTTON, 0x0002)
        time.sleep(delay)
        self.control_device(DeviceProperty.S2_BUTTON, 0x0002)
        time.sleep(delay)
        self.control_device(DeviceProperty.S2_BUTTON, 0x0001)
        time.sleep(delay)
        self.control_device(DeviceProperty.S1_BUTTON, 0x0001)

    def _wait_for_shooting_file_info_clear(self, timeout: float = 10.0) -> None:
        """Wait until SHOOTING_FILE_INFO bit 15 is clear (no stale image flag)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            info = self.get_property(DeviceProperty.SHOOTING_FILE_INFO)
            val = info.current_value if isinstance(info.current_value, int) else 0
            if not (val & 0x8000):
                return
            time.sleep(0.1)
        # Non-fatal: log a warning and proceed — the camera may clear it after shutter.
        logger.warning("SHOOTING_FILE_INFO did not clear before shutter (current=0x%04X)", val)

    def _get_storage_ids(self) -> list[int]:
        """Return the list of storage IDs reported by the camera."""
        resp, data = self._transport.receive(PTPOpCode.GET_STORAGE_ID)
        if resp.code != ResponseCode.OK:
            return []
        if len(data) < 4:
            return []
        count = struct.unpack_from("<I", data, 0)[0]
        if count == 0:
            return []
        return list(struct.unpack_from(f"<{count}I", data, 4))

    def _get_object_handles(
        self,
        storage_id: int = 0xFFFFFFFF,
        format_code: int = 0x00000000,
        parent_handle: int = 0xFFFFFFFF,
    ) -> list[int]:
        """Return the list of all object handles on the camera."""
        resp, data = self._transport.receive(
            PTPOpCode.GET_OBJECT_HANDLES,
            [storage_id, format_code, parent_handle],
        )
        if resp.code != ResponseCode.OK:
            logger.debug("GetObjectHandles returned 0x%04X — no objects or store unavailable", resp.code)
            return []
        if len(data) < 4:
            return []
        count = struct.unpack_from("<I", data, 0)[0]
        if count == 0:
            return []
        return list(struct.unpack_from(f"<{count}I", data, 4))

    # ------------------------------------------------------------------
    # Burst capture
    # ------------------------------------------------------------------

    def burst_capture(
        self,
        count: int,
        output_dir: Optional[Union[str, Path]] = None,
        af_lock_time: float = 0.5,
        timeout_per_shot: float = 30.0,
    ) -> list[bytes]:
        """Fire *count* shots as fast as possible and return all images.

        S1 (half-press / AF lock) is held down for the entire burst so AF and
        AE are solved only once.  S2 is pulsed per shot.  Each image is
        downloaded immediately after the camera signals it is ready — Sony's
        SDIO host-control protocol exposes only a single fixed object handle
        (0xFFFFC001) so deferred bulk-download is not possible.

        Typical cycle time after the first shot: ~1 s per frame.

        Parameters
        ----------
        count : int
            Number of shots to take.
        output_dir : str or Path, optional
            Directory to save images as ``burst_0000.jpg``, ``burst_0001.jpg``, …
        af_lock_time : float
            Seconds to hold S1 before the first S2 press so AF/AE can lock
            (default 0.5 s).
        timeout_per_shot : float
            Maximum seconds to wait for any single shot to complete.

        Returns
        -------
        list[bytes]
            Raw image data for each shot, in order.
        """
        self.set_save_media(SaveMedia.HOST)
        self._wait_for_property_value(DeviceProperty.SAVE_MEDIA, int(SaveMedia.HOST))

        # LiveView must be active before we start.
        self._wait_for_liveview()

        # Clear any stale flag before the burst starts.
        self._wait_for_shooting_file_info_clear(timeout=10.0)

        out_path = Path(output_dir) if output_dir else None
        if out_path:
            out_path.mkdir(parents=True, exist_ok=True)

        images: list[bytes] = []

        # Hold S1 for the entire burst — AF/AE locks once and stays locked.
        # Poll AF_LOCK_INDICATION instead of using a blind sleep so the first
        # shot fires as soon as the camera reports focus is locked, and we still
        # proceed even if the camera can't lock (e.g. MF mode).
        self.control_device(DeviceProperty.S1_BUTTON, 0x0002)
        logger.info("S1 held — waiting for AF lock (max %.1fs)…", af_lock_time)
        deadline = time.monotonic() + af_lock_time
        while time.monotonic() < deadline:
            try:
                af = self.get_property(DeviceProperty.AF_LOCK_INDICATION)
                if af.current_value:
                    logger.info("AF locked")
                    break
            except Exception:
                pass
            time.sleep(0.05)
        else:
            logger.warning("AF did not lock within %.1fs — proceeding anyway", af_lock_time)

        try:
            for i in range(count):
                logger.info("Burst shot %d/%d", i + 1, count)

                # Ensure flag from the previous download has cleared.
                if i > 0:
                    self._wait_for_shooting_file_info_clear(timeout=timeout_per_shot)

                # Pulse S2 to fire the shutter (S1 already held).
                self.control_device(DeviceProperty.S2_BUTTON, 0x0002)
                time.sleep(0.1)
                self.control_device(DeviceProperty.S2_BUTTON, 0x0001)

                # Wait for SHOOTING_FILE_INFO bit 15 (image ready on host).
                deadline = time.monotonic() + timeout_per_shot
                val = 0
                while time.monotonic() < deadline:
                    info = self.get_property(DeviceProperty.SHOOTING_FILE_INFO)
                    val = info.current_value if isinstance(info.current_value, int) else 0
                    if val & 0x8000:
                        break
                    time.sleep(0.1)
                else:
                    raise SonyCameraError(
                        f"Burst shot {i + 1}/{count} timed out waiting for image"
                    )

                logger.info("Shot %d ready, downloading…", i + 1)

                self.get_object_info(SHOT_OBJECT_HANDLE)
                data = self.get_object(SHOT_OBJECT_HANDLE)
                images.append(data)
                logger.info("Downloaded shot %d/%d  %d bytes", i + 1, count, len(data))

                if out_path:
                    filename = out_path / f"burst_{i:04d}.jpg"
                    filename.write_bytes(data)
                    logger.info("Saved → %s", filename)

        finally:
            # Always release S1, even if an exception occurs mid-burst.
            self.control_device(DeviceProperty.S1_BUTTON, 0x0001)

        logger.info("Burst complete — %d image(s)", len(images))
        return images

    def rapid_fire(
        self,
        count: int,
        output_dir: Optional[Union[str, Path]] = None,
        timeout_per_shot: float = 30.0,
    ) -> list[bytes]:
        """Fire *count* shots using a full S1→S2 cycle per shot.

        Unlike :meth:`burst_capture` (which holds S1 for the entire burst),
        this method performs a complete shutter cycle for every frame:

        1. S1 press  (half-press — autofocus + metering)
        2. S2 press  (shutter fires)
        3. S2 release
        4. S1 release
        5. Wait for the image, download it
        6. Repeat

        The delays are kept to the minimum (200 ms S2 hold, matching the Sony
        C++ SDK example).  This avoids a state where the camera "hangs" after
        the first shot because S1 was never released between shots.

        Parameters
        ----------
        count : int
            Number of shots to take.
        output_dir : str or Path, optional
            Directory to save images as ``rapid_0000.jpg``, …
        timeout_per_shot : float
            Maximum seconds to wait for each image to appear.

        Returns
        -------
        list[bytes]
            Raw image data for each shot, in order.
        """
        self.set_save_media(SaveMedia.HOST)
        self._wait_for_property_value(DeviceProperty.SAVE_MEDIA, int(SaveMedia.HOST))
        self._wait_for_liveview()
        self._wait_for_shooting_file_info_clear(timeout=10.0)

        out_path = Path(output_dir) if output_dir else None
        if out_path:
            out_path.mkdir(parents=True, exist_ok=True)

        images: list[bytes] = []

        for i in range(count):
            logger.info("Rapid-fire shot %d/%d", i + 1, count)

            # --- Full shutter cycle ---
            self.control_device(DeviceProperty.S1_BUTTON, 0x0002)   # S1 press
            time.sleep(0.3)                                         # AF + AE settle
            self.control_device(DeviceProperty.S2_BUTTON, 0x0002)   # S2 press
            time.sleep(0.2)                                         # matches C++ SDK
            self.control_device(DeviceProperty.S2_BUTTON, 0x0001)   # S2 release
            time.sleep(0.1)
            self.control_device(DeviceProperty.S1_BUTTON, 0x0001)   # S1 release

            # --- Wait for image ---
            deadline = time.monotonic() + timeout_per_shot
            while time.monotonic() < deadline:
                info = self.get_property(DeviceProperty.SHOOTING_FILE_INFO)
                val = info.current_value if isinstance(info.current_value, int) else 0
                if val & 0x8000:
                    break
                time.sleep(0.05)
            else:
                raise SonyCameraError(
                    f"Shot {i + 1}/{count} timed out waiting for image"
                )

            logger.info("Shot %d ready — downloading…", i + 1)
            self.get_object_info(SHOT_OBJECT_HANDLE)
            data = self.get_object(SHOT_OBJECT_HANDLE)
            images.append(data)
            logger.info("Downloaded shot %d/%d  (%d bytes)", i + 1, count, len(data))

            if out_path:
                fname = out_path / f"rapid_{i:04d}.jpg"
                fname.write_bytes(data)
                logger.info("Saved → %s", fname)

            # Let the camera clear the stale flag before next shot.
            if i < count - 1:
                self._wait_for_shooting_file_info_clear(timeout=10.0)

        logger.info("Rapid-fire complete — %d image(s)", len(images))
        return images

    # ------------------------------------------------------------------
    # Continuous-burst capture  (native fps, deferred download)
    # ------------------------------------------------------------------

    def set_drive_mode(self, mode: Union[int, DriveMode]) -> None:
        """Set the drive mode (single, continuous Hi/Lo, self-timer, …).

        This writes to the Still Capture Mode property (0x5013).
        The camera must be in still-shooting mode.

        .. note::

           :meth:`set_mode` also writes to this register (0x5013) and will
           reset the drive mode to Single.  Always call ``set_drive_mode()``
           **after** ``set_mode("still")``.

        Parameters
        ----------
        mode : int or DriveMode
            A :class:`DriveMode` value, e.g. ``DriveMode.CONTINUOUS_HI``.
        """
        code = DeviceProperty.STILL_CAPTURE_MODE
        val = int(mode)

        # Wait for the property to become writable (the camera may still be
        # settling after a set_mode call).
        self._wait_for_property_enabled(code, timeout=5.0)
        time.sleep(0.3)

        # Write with size=4 — this matches how set_mode writes to the
        # same register and is what the camera expects.
        self.set_property(code, val, size=4)

        # Verify the camera accepted it — retry once if it didn't take.
        time.sleep(0.3)
        info = self.get_property(code)
        actual = info.current_value if isinstance(info.current_value, int) else None
        if actual != val:
            logger.info(
                "Drive mode first attempt: sent 0x%04X, got 0x%04X — retrying",
                val, actual or 0,
            )
            time.sleep(0.5)
            self._wait_for_property_enabled(code, timeout=5.0)
            self.set_property(code, val, size=4)
            time.sleep(0.3)
            info = self.get_property(code)
            actual = info.current_value if isinstance(info.current_value, int) else None

        if actual != val:
            logger.warning(
                "Drive mode NOT accepted: sent 0x%04X, camera reports 0x%04X. "
                "You may need to set it on the camera body.",
                val, actual or 0,
            )
        else:
            logger.info("Drive mode set to 0x%04X (confirmed)", val)

    def continuous_burst(
        self,
        hold_seconds: float = 2.0,
        drive_mode: Union[int, DriveMode] = DriveMode.CONTINUOUS_HI,
        output_dir: Optional[Union[str, Path]] = None,
        download_timeout: float = 60.0,
    ) -> list[bytes]:
        """Shoot a continuous burst at native fps, then download all images.

        This leverages the camera's hardware continuous-shooting drive mode.
        S2 is **held down** for *hold_seconds*, letting the camera fire at its
        full mechanical/electronic burst rate (often 5–20 fps depending on
        model and drive-mode setting).  After the burst, all queued images are
        downloaded one-by-one from the camera's transfer buffer.

        The drive mode is set automatically by this method.  You do **not**
        need to call :meth:`set_drive_mode` first.

        Sequence
        --------
        1. Set save-media to HOST, set drive mode to *drive_mode*
        2. S1 press  (AF + AE lock)
        3. S2 press  (camera starts continuous shooting)
        4. Hold for *hold_seconds*
        5. S2 release → S1 release
        6. Poll ``SHOOTING_FILE_INFO`` and download every queued image
           via ``GetObjectInfo`` + ``GetObject(0xFFFFC001)`` until the count
           reaches zero.

        Parameters
        ----------
        hold_seconds : float
            How long to hold S2 down (burst duration). 1.0 s at 10 fps ≈ 10 shots.
        drive_mode : int or DriveMode
            Which continuous-shooting variant to use (default:
            ``DriveMode.CONTINUOUS_HI``).
        output_dir : str or Path, optional
            Directory to save images as ``cont_0000.jpg``, …
        download_timeout : float
            Maximum total seconds to spend downloading all queued images.

        Returns
        -------
        list[bytes]
            Raw image data for each shot, in capture order.
        """
        self.set_save_media(SaveMedia.HOST)
        self._wait_for_property_value(DeviceProperty.SAVE_MEDIA, int(SaveMedia.HOST))
        self._wait_for_liveview()
        self._wait_for_shooting_file_info_clear(timeout=10.0)

        # Set the drive mode — this MUST happen after set_mode("still")
        # because set_mode writes 0x01 (Normal/Single) to the same register.
        self.set_drive_mode(drive_mode)

        out_path = Path(output_dir) if output_dir else None
        if out_path:
            out_path.mkdir(parents=True, exist_ok=True)

        # --- S1 press → AF lock ---
        self.control_device(DeviceProperty.S1_BUTTON, 0x0002)
        logger.info("S1 held — waiting for AF…")

        # Poll Focus Indication (0xD213) which is more reliable than
        # AF_LOCK_INDICATION for deciding when to fire.
        # 0x02 = focused (AF-S), 0x06 = focused (AF-C)
        af_deadline = time.monotonic() + 3.0
        af_ok = False
        while time.monotonic() < af_deadline:
            try:
                fi = self.get_property(DeviceProperty.AF_STATUS)
                fv = fi.current_value if isinstance(fi.current_value, int) else 0
                if fv in (0x02, 0x05, 0x06):
                    logger.info("Focus confirmed (0x%02X)", fv)
                    af_ok = True
                    break
            except Exception:
                pass
            time.sleep(0.05)

        if not af_ok:
            logger.warning("AF focus not confirmed — burst may be limited")

        # --- S2 hold → burst ---
        logger.info("S2 held — burst for %.1fs…", hold_seconds)
        self.control_device(DeviceProperty.S2_BUTTON, 0x0002)
        time.sleep(hold_seconds)
        self.control_device(DeviceProperty.S2_BUTTON, 0x0001)
        logger.info("S2 released")
        time.sleep(0.1)
        self.control_device(DeviceProperty.S1_BUTTON, 0x0001)
        logger.info("S1 released")

        # --- Download all queued images ---
        images: list[bytes] = []
        dl_deadline = time.monotonic() + download_timeout
        idx = 0

        # Short settle time — the camera needs a moment after S2 release
        # to finalize the last images in the queue.
        time.sleep(0.3)

        while time.monotonic() < dl_deadline:
            info = self.get_property(DeviceProperty.SHOOTING_FILE_INFO)
            val = info.current_value if isinstance(info.current_value, int) else 0

            if val & 0x8000:
                # Image ready — download it
                self.get_object_info(SHOT_OBJECT_HANDLE)
                data = self.get_object(SHOT_OBJECT_HANDLE)
                images.append(data)
                logger.info("Downloaded image %d  (%d bytes)", idx + 1, len(data))

                if out_path:
                    fname = out_path / f"cont_{idx:04d}.jpg"
                    fname.write_bytes(data)
                    logger.info("Saved → %s", fname)
                idx += 1
                # Immediately check for more images (don't sleep)
                continue

            # No image with MSB set.  Check if any files remain (lower bits).
            remaining = val & 0x7FFF
            if remaining == 0 and idx > 0:
                # All images downloaded.
                break

            # Files still being processed by the camera — wait a bit.
            time.sleep(0.05)
        else:
            logger.warning("Download timed out after %d image(s)", idx)

        logger.info("Continuous burst complete — %d image(s)", len(images))
        return images

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

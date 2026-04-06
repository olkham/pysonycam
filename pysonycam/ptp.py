"""
PTP transport layer for Sony cameras over USB.

Handles the low-level PTP bulk container framing, USB endpoint I/O, session
management, and transaction sequencing using python-libusb1 (libusb1).
"""

from __future__ import annotations

import logging
import struct
import time
from dataclasses import dataclass, field

import usb1  # python-libusb1

from pysonycam.constants import ContainerType, ResponseCode
from pysonycam.exceptions import (
    ConnectionError,
    DeviceNotFoundError,
    TimeoutError,
    TransactionError,
)

logger = logging.getLogger(__name__)

# PTP over USB constants
_SONY_VENDOR_ID = 0x054C  # Sony Corporation
_PTP_INTERFACE_CLASS = 6   # Still Imaging
_BULK_MAX_PACKET = 512
_BULK_BUFFER_SIZE = 10 * 1024 * 1024  # 10 MB max receive
_DEFAULT_TIMEOUT_MS = 5000
_HEADER_SIZE = 12  # GenericBulkContainerHeader: u32 length + u16 type + u16 code + u32 transaction_id
_HEADER_FMT = "<IHHI"  # length(u32), type(u16), code(u16), transaction_id(u32)


@dataclass
class PTPResponse:
    """Parsed PTP response container."""
    code: int = 0
    session_id: int = 0
    transaction_id: int = 0
    params: list[int] = field(default_factory=list)


@dataclass
class PTPEvent:
    """Parsed PTP event container."""
    code: int = 0
    session_id: int = 0
    transaction_id: int = 0
    params: list[int] = field(default_factory=list)


class PTPTransport:
    """Low-level PTP/USB transport for Sony cameras.

    Manages USB device discovery, endpoint communication, and PTP container
    framing.  Not typically used directly — see :class:`SonyCamera` for the
    high-level API.

    Parameters
    ----------
    bus : int, optional
        USB bus number (0 = auto-detect).
    device : int, optional
        USB device address (0 = auto-detect).
    timeout_ms : int, optional
        USB transfer timeout in milliseconds.
    """

    def __init__(
        self,
        bus: int = 0,
        device: int = 0,
        timeout_ms: int = _DEFAULT_TIMEOUT_MS,
    ):
        self._bus = bus
        self._device = device
        self._timeout_ms = timeout_ms

        self._context: usb1.USBContext | None = None
        self._handle: usb1.USBDeviceHandle | None = None
        self._interface: int = 0
        self._ep_in: int = 0
        self._ep_out: int = 0
        self._ep_int: int = 0

        self._session_id: int = 0
        self._transaction_id: int = 0

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Open a USB connection to the first Sony PTP camera found."""
        self._context = usb1.USBContext()
        self._context.open()

        dev = self._find_device()
        if dev is None:
            raise DeviceNotFoundError(
                "No Sony PTP camera found. Is the camera connected and in "
                "PC Remote mode?"
            )

        self._handle = dev.open()

        # Detach kernel driver if active (Linux)
        try:
            if self._handle.kernelDriverActive(self._interface):
                self._handle.detachKernelDriver(self._interface)
        except usb1.USBError:
            pass

        try:
            self._handle.claimInterface(self._interface)
        except usb1.USBErrorAccess:
            import sys
            if sys.platform == "win32":
                raise ConnectionError(
                    "Cannot claim the USB interface — access denied.\n\n"
                    "On Windows you must replace the camera's driver with WinUSB "
                    "using Zadig (https://zadig.akeo.ie/):\n"
                    "  1. Connect your Sony camera and set it to PC Remote mode\n"
                    "  2. Download and run Zadig\n"
                    "  3. In Zadig, go to Options → List All Devices\n"
                    "  4. Select your Sony camera from the dropdown\n"
                    "  5. Set the target driver to 'WinUSB' and click 'Replace Driver'\n"
                    "  6. Re-run this script\n\n"
                    "NOTE: This replaces the MTP driver. To restore MTP, use "
                    "Device Manager → Update Driver → Search Automatically."
                ) from None
            raise ConnectionError(
                "Cannot claim the USB interface — permission denied.\n"
                "On Linux, run as root or add a udev rule:\n"
                '  echo \'SUBSYSTEM=="usb", ATTR{idVendor}=="054c", MODE="0666"\' | '
                "sudo tee /etc/udev/rules.d/99-sony-camera.rules\n"
                "  sudo udevadm control --reload-rules && sudo udevadm trigger"
            ) from None
        except usb1.USBErrorBusy:
            raise ConnectionError(
                "USB interface is busy — another program may be using the camera.\n"
                "Close any photo management software (e.g., Sony Imaging Edge, "
                "Windows Photos) and retry."
            ) from None

        logger.info(
            "Connected to Sony camera on bus %d device %d",
            dev.getBusNumber(),
            dev.getDeviceAddress(),
        )

    def disconnect(self) -> None:
        """Release USB resources and close the connection."""
        if self._handle is not None:
            try:
                self._handle.releaseInterface(self._interface)
            except usb1.USBError:
                pass
            self._handle.close()
            self._handle = None
        if self._context is not None:
            self._context.close()
            self._context = None
        self._session_id = 0
        self._transaction_id = 0
        logger.info("Disconnected from camera")

    @property
    def is_connected(self) -> bool:
        return self._handle is not None

    # ------------------------------------------------------------------
    # PTP transactions
    # ------------------------------------------------------------------

    def send(
        self,
        opcode: int,
        params: list[int] | None = None,
        data: bytes | None = None,
    ) -> PTPResponse:
        """Execute a sending PTP transaction (command [+ data] + response).

        Parameters
        ----------
        opcode : int
            PTP operation code.
        params : list of int, optional
            Up to 5 uint32 parameters.
        data : bytes, optional
            Data payload for the data phase.

        Returns
        -------
        PTPResponse
            The parsed response from the camera.
        """
        if params is None:
            params = []

        # Handle OpenSession specially: reset IDs
        if opcode == 0x1002:
            self._session_id = 0
            self._transaction_id = 0

        self._send_command(opcode, params)

        if data is not None and len(data) > 0:
            self._send_data(opcode, data)

        response = self._read_response()
        self._transaction_id += 1
        return response

    def receive(
        self,
        opcode: int,
        params: list[int] | None = None,
    ) -> tuple[PTPResponse, bytes]:
        """Execute a receiving PTP transaction (command + data + response).

        Returns
        -------
        tuple of (PTPResponse, bytes)
            The response and the received data payload.
        """
        if params is None:
            params = []

        self._send_command(opcode, params)
        data = self._read_data()
        response = self._read_response()
        self._transaction_id += 1
        return response, data

    def wait_event(self, timeout_ms: int | None = None) -> PTPEvent:
        """Block until a PTP event arrives on the interrupt endpoint.

        Parameters
        ----------
        timeout_ms : int, optional
            Override the default timeout (0 = infinite wait).
        """
        if timeout_ms is None:
            timeout_ms = self._timeout_ms

        buf = self._read_interrupt(timeout_ms)
        if len(buf) < _HEADER_SIZE:
            raise TransactionError("Event packet too short")

        length, ctype, code, tid = struct.unpack_from(_HEADER_FMT, buf, 0)
        if ctype != ContainerType.EVENT:
            raise TransactionError(
                f"Expected Event container (0x0004), got 0x{ctype:04X}"
            )

        param_bytes = buf[_HEADER_SIZE:]
        n_params = len(param_bytes) // 4
        params = list(struct.unpack_from(f"<{n_params}I", param_bytes))

        event = PTPEvent(
            code=code,
            session_id=self._session_id,
            transaction_id=tid,
            params=params,
        )
        logger.debug("Event: code=0x%04X params=%s", code, params)
        return event

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _find_device(self) -> usb1.USBDevice | None:
        """Locate a Sony PTP device on the USB bus."""
        for dev in self._context.getDeviceList():
            if dev.getVendorID() != _SONY_VENDOR_ID:
                continue

            # If specific bus/device requested, check those
            if self._bus and dev.getBusNumber() != self._bus:
                continue
            if self._device and dev.getDeviceAddress() != self._device:
                continue

            # Look for PTP interface (class 6)
            for cfg in dev:
                for iface in cfg:
                    for setting in iface:
                        if setting.getClass() == _PTP_INTERFACE_CLASS:
                            self._interface = setting.getNumber()
                            self._detect_endpoints(setting)
                            return dev
        return None

    def _detect_endpoints(self, setting) -> None:
        """Detect bulk-in, bulk-out, and interrupt-in endpoints."""
        for ep in setting:
            addr = ep.getAddress()
            attr = ep.getAttributes()
            is_in = bool(addr & 0x80)
            transfer_type = attr & 0x03

            if transfer_type == 2:  # Bulk
                if is_in:
                    self._ep_in = addr
                else:
                    self._ep_out = addr
            elif transfer_type == 3:  # Interrupt
                if is_in:
                    self._ep_int = addr

        logger.debug(
            "Endpoints: OUT=0x%02X  IN=0x%02X  INT=0x%02X",
            self._ep_out, self._ep_in, self._ep_int,
        )

    def _bulk_write(self, data: bytes) -> int:
        """Write data to the bulk-out endpoint."""
        try:
            return self._handle.bulkWrite(self._ep_out, data, self._timeout_ms)
        except usb1.USBErrorTimeout as exc:
            raise TimeoutError("USB bulk write timed out") from exc
        except usb1.USBErrorNoDevice as exc:
            raise ConnectionError("Camera disconnected") from exc
        except usb1.USBError as exc:
            raise ConnectionError(f"USB write error: {exc}") from exc

    def _bulk_read(self, size: int = _BULK_BUFFER_SIZE) -> bytes:
        """Read data from the bulk-in endpoint."""
        try:
            return self._handle.bulkRead(self._ep_in, size, self._timeout_ms)
        except usb1.USBErrorTimeout as exc:
            raise TimeoutError("USB bulk read timed out") from exc
        except usb1.USBErrorNoDevice as exc:
            raise ConnectionError("Camera disconnected") from exc
        except usb1.USBError as exc:
            raise ConnectionError(f"USB read error: {exc}") from exc

    def _read_interrupt(self, timeout_ms: int = 0) -> bytes:
        """Read data from the interrupt-in endpoint."""
        try:
            return self._handle.interruptRead(
                self._ep_int, _BULK_MAX_PACKET, timeout_ms or self._timeout_ms
            )
        except usb1.USBErrorTimeout as exc:
            raise TimeoutError("USB interrupt read timed out") from exc
        except usb1.USBErrorNoDevice as exc:
            raise ConnectionError("Camera disconnected") from exc
        except usb1.USBError as exc:
            raise ConnectionError(f"USB interrupt error: {exc}") from exc

    def _send_command(self, opcode: int, params: list[int]) -> None:
        """Build and send a PTP Command Block."""
        n = len(params)
        length = _HEADER_SIZE + 4 * n
        buf = struct.pack(_HEADER_FMT, length, ContainerType.COMMAND, opcode,
                          self._transaction_id)
        for p in params:
            buf += struct.pack("<I", p)
        self._bulk_write(buf)
        logger.debug(
            "CMD  -> opcode=0x%04X tid=%d params=%s",
            opcode, self._transaction_id,
            [f"0x{p:08X}" for p in params],
        )

    def _send_data(self, opcode: int, data: bytes) -> None:
        """Build and send a PTP Data Block."""
        length = _HEADER_SIZE + len(data)
        header = struct.pack(
            _HEADER_FMT, length, ContainerType.DATA, opcode,
            self._transaction_id,
        )
        self._bulk_write(header + data)
        logger.debug("DATA -> opcode=0x%04X size=%d", opcode, len(data))

    def _read_data(self) -> bytes:
        """Read a PTP Data Block, handling multi-packet transfers."""
        raw = self._bulk_read()
        if len(raw) < _HEADER_SIZE:
            raise TransactionError("Data packet too short")

        length, ctype, code, tid = struct.unpack_from(_HEADER_FMT, raw, 0)

        if ctype != ContainerType.DATA:
            # No data phase — this is probably the response; push it back
            # by returning empty and let _read_response handle it
            raise TransactionError(
                f"Expected Data container (0x0002), got 0x{ctype:04X}"
            )

        payload = bytearray(raw[_HEADER_SIZE:])

        # Continue reading if more data expected
        while len(payload) + _HEADER_SIZE < length:
            chunk = self._bulk_read(length - len(payload) - _HEADER_SIZE)
            payload.extend(chunk)

        logger.debug("DATA <- size=%d", len(payload))
        return bytes(payload)

    def _read_response(self) -> PTPResponse:
        """Read a PTP Response Block."""
        raw = self._bulk_read()
        if len(raw) < _HEADER_SIZE:
            raise TransactionError("Response packet too short")

        length, ctype, code, tid = struct.unpack_from(_HEADER_FMT, raw, 0)

        if ctype != ContainerType.RESPONSE:
            raise TransactionError(
                f"Expected Response container (0x0003), got 0x{ctype:04X}"
            )

        param_bytes = raw[_HEADER_SIZE:length]
        n_params = len(param_bytes) // 4
        params = list(struct.unpack_from(f"<{n_params}I", param_bytes)) if n_params else []

        resp = PTPResponse(
            code=code,
            session_id=self._session_id,
            transaction_id=tid,
            params=params,
        )
        logger.debug(
            "RESP <- code=0x%04X params=%s",
            code, [f"0x{p:08X}" for p in params],
        )
        return resp

    def clear_halt(self) -> None:
        """Clear HALT/STALL on all endpoints (recovery after errors)."""
        if self._handle is None:
            return
        for ep in (self._ep_in, self._ep_out, self._ep_int):
            if ep:
                try:
                    self._handle.clearHalt(ep)
                except usb1.USBError:
                    pass

    def reset(self) -> None:
        """Reset the USB device (last resort recovery)."""
        if self._handle is not None:
            self._handle.resetDevice()

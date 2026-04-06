"""Custom exceptions for Sony camera control."""


class SonyCameraError(Exception):
    """Base exception for all Sony camera errors."""


class ConnectionError(SonyCameraError):
    """Failed to connect to the camera via USB."""


class DeviceNotFoundError(ConnectionError):
    """No Sony PTP camera found on the USB bus."""


class AuthenticationError(SonyCameraError):
    """SDIO authentication handshake failed."""


class TransactionError(SonyCameraError):
    """PTP transaction failed (unexpected response type or code)."""

    def __init__(self, message: str, response_code: int = 0):
        super().__init__(message)
        self.response_code = response_code


class TimeoutError(SonyCameraError):
    """Operation timed out waiting for camera response."""


class PropertyError(SonyCameraError):
    """Error reading or writing a device property."""

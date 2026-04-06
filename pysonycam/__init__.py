"""
Sony Camera Remote Control via PTP/USB.

A Pythonic library for controlling Sony cameras using the PTP (Picture Transfer
Protocol) with Sony's proprietary SDIO extensions. Supports session management,
authentication, property reading/writing, photo capture, and LiveView streaming.

Basic usage::

    from pysonycam import SonyCamera

    with SonyCamera() as camera:
        camera.authenticate()
        camera.set_mode("still")
        camera.capture("photo.jpg")
"""

from pysonycam.camera import SonyCamera
from pysonycam.constants import (
    DeviceProperty,
    DriveMode,
    ExposureMode,
    OperatingMode,
    WhiteBalance,
    FocusMode,
    FocusArea,
)
from pysonycam.format import property_name, format_value
from pysonycam.exceptions import (
    SonyCameraError,
    ConnectionError,
    AuthenticationError,
    TransactionError,
    TimeoutError,
    DeviceNotFoundError,
)

__version__ = "1.0.0"
__all__ = [
    "SonyCamera",
    "DeviceProperty",
    "DriveMode",
    "ExposureMode",
    "OperatingMode",
    "WhiteBalance",
    "FocusMode",
    "FocusArea",
    "property_name",
    "format_value",
    "SonyCameraError",
    "ConnectionError",
    "AuthenticationError",
    "TransactionError",
    "TimeoutError",
    "DeviceNotFoundError",
]

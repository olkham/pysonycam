# Sony Camera Control — Python Library

A Pythonic library for controlling Sony cameras over USB using PTP (Picture Transfer Protocol) with Sony's proprietary SDIO extensions.

Built from the [Sony Camera Remote Command SDK](https://developer.sony.com/) C/C++ reference implementation, this library provides the same functionality in a clean, easy-to-use Python package.

## Features

- **Connect** to Sony cameras via USB (auto-detects Sony PTP devices)
- **Authenticate** using the Sony SDIO handshake (v2 and v3 protocols)
- **Read all camera properties** — exposure mode, ISO, aperture, shutter speed, white balance, battery level, and 50+ more
- **Change settings** — set exposure mode, ISO, aperture, shutter speed, white balance, image quality, save media, and more
- **Capture photos** — full shutter control with image download to host
- **LiveView streaming** — get real-time JPEG preview frames
- **Zoom and focus control** — optical zoom in/out, manual focus near/far
- **Movie recording** — start/stop video recording
- **Context manager** support for safe connection handling
- **Comprehensive enums** — human-readable constants for all settings

## Requirements

- **Python 3.10+**
- **libusb 1.0** — USB backend
- **A Sony camera** with USB connection in PC Remote mode

## Installation

### Quick Install (pip)

```bash
cd python/
pip install -e .
```

### Using the Setup Scripts

**Linux / macOS:**
```bash
cd python/
chmod +x install.sh
./install.sh
```

**Windows:**
```cmd
cd python\
install.bat
```

### System Dependencies

#### Linux (Ubuntu/Debian)
```bash
sudo apt install libusb-1.0-0 libusb-1.0-0-dev
```

To use without root, add a udev rule:
```bash
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="054c", MODE="0666"' | \
  sudo tee /etc/udev/rules.d/99-sony-camera.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```

#### macOS
```bash
brew install libusb
```

#### Windows
Install a WinUSB driver for your camera using [Zadig](https://zadig.akeo.ie/):
1. Connect your Sony camera
2. Run Zadig
3. Select your camera device
4. Install the WinUSB driver

## Quick Start

```python
from sony_camera_control import SonyCamera

# Connect and authenticate
with SonyCamera() as camera:
    camera.authenticate()

    # Read all properties
    props = camera.get_all_properties()
    for code, info in sorted(props.items()):
        print(f"0x{code:04X}: {info}")
```

## Usage Examples

### Capture a Photo

```python
from sony_camera_control import SonyCamera

with SonyCamera() as camera:
    camera.authenticate()
    camera.set_mode("still")
    camera.capture("photo.jpg")
```

### Change Camera Settings

```python
from sony_camera_control import SonyCamera, ExposureMode, WhiteBalance

with SonyCamera() as camera:
    camera.authenticate()
    camera.set_mode("still")

    # Set to Aperture Priority
    camera.set_exposure_mode(ExposureMode.APERTURE_PRIORITY)

    # Set ISO to 400
    camera.set_iso(0x00000190)

    # Set aperture to F2.8
    camera.set_aperture(0x0118)

    # Set white balance to Daylight
    camera.set_white_balance(WhiteBalance.DAYLIGHT)
```

### LiveView Streaming

```python
from sony_camera_control import SonyCamera

with SonyCamera() as camera:
    camera.authenticate()
    camera.set_mode("still")

    # Get 100 LiveView frames
    for i, frame in enumerate(camera.liveview_stream(count=100)):
        with open(f"frame_{i:04d}.jpg", "wb") as f:
            f.write(frame)
```

### Zoom Control

```python
import time
from sony_camera_control import SonyCamera

with SonyCamera() as camera:
    camera.authenticate()
    camera.set_mode("still")

    camera.zoom_in(speed=3)   # speed: 1=slow, 3=medium, 7=fast
    time.sleep(2)
    camera.zoom_stop()
```

### Movie Recording

```python
import time
from sony_camera_control import SonyCamera

with SonyCamera() as camera:
    camera.authenticate()
    camera.set_mode("movie")

    camera.start_movie()
    time.sleep(10)  # Record for 10 seconds
    camera.stop_movie()
```

### Read a Specific Property

```python
from sony_camera_control import SonyCamera
from sony_camera_control.constants import DeviceProperty, ISO_TABLE

with SonyCamera() as camera:
    camera.authenticate()
    camera.set_mode("still")

    info = camera.get_property(DeviceProperty.ISO)
    print(f"ISO: {ISO_TABLE.get(info.current_value, 'Unknown')}")
    print(f"Writable: {info.is_writable}")
    print(f"Supported values: {[ISO_TABLE.get(v) for v in info.supported_values]}")
```

## API Reference

### `SonyCamera`

| Method | Description |
|--------|-------------|
| `connect()` | Open USB connection and PTP session |
| `disconnect()` | Close session and USB connection |
| `authenticate()` | Perform Sony SDIO authentication handshake |
| `get_all_properties()` | Read all device properties → `dict[int, DevicePropInfo]` |
| `get_property(code)` | Read a single property → `DevicePropInfo` |
| `set_property(code, value)` | Write a property value |
| `set_mode(mode)` | Set operating mode: `"still"`, `"movie"`, `"transfer"`, `"standby"` |
| `set_exposure_mode(mode)` | Set exposure mode (M, P, A, S, Auto...) |
| `set_iso(value)` | Set ISO (use `0x00FFFFFF` for AUTO) |
| `set_aperture(code)` | Set F-number |
| `set_shutter_speed(code)` | Set shutter speed |
| `set_white_balance(wb)` | Set white balance mode |
| `set_exposure_compensation(value)` | Set EV compensation |
| `set_save_media(media)` | Set save destination (host/camera/both) |
| `capture(path)` | Capture a photo and save to file → `bytes` |
| `get_liveview_frame()` | Get one LiveView JPEG frame → `bytes` |
| `liveview_stream(count)` | Yield LiveView frames as a generator |
| `zoom_in(speed)` / `zoom_out(speed)` / `zoom_stop()` | Zoom control |
| `focus_near(step)` / `focus_far(step)` | Manual focus control |
| `start_movie()` / `stop_movie()` | Movie recording control |
| `battery_level` | Read battery level (property) |

### `DevicePropInfo`

Returned by `get_property()` and `get_all_properties()`:

| Attribute | Type | Description |
|-----------|------|-------------|
| `property_code` | `int` | Property code (hex) |
| `data_type` | `int` | PTP data type code |
| `is_writable` | `bool` | True if read-write |
| `is_valid` | `bool` | True if property is currently valid |
| `current_value` | `int\|str\|list` | Current value |
| `default_value` | `int\|str\|list` | Factory default value |
| `supported_values` | `list` | Enumeration of supported values (if applicable) |
| `minimum_value` | `int` | Min of range (if applicable) |
| `maximum_value` | `int` | Max of range (if applicable) |
| `step_size` | `int` | Step size (if applicable) |

### Constants & Enums

All constants are importable from `sony_camera_control.constants`:

- `DeviceProperty` — all property codes (EXPOSURE_MODE, ISO, F_NUMBER, etc.)
- `ExposureMode` — Manual, Program Auto, Aperture Priority, Shutter Priority, Auto, etc.
- `OperatingMode` — Standby, Still Rec, Movie Rec, Contents Transfer
- `WhiteBalance` — AWB, Daylight, Cloudy, Tungsten, Flash, Custom, etc.
- `FocusMode` — Manual, AF-S, AF-C, AF-Auto, DMF
- `FocusArea` — Wide, Zone, Center, Flexible Spot, Lock-On AF
- `ImageSize` — Large, Medium, Small
- `JpegQuality` — Extra Fine, Fine, Standard, Light
- `FileFormat` — RAW, RAW+JPEG, JPEG
- `AspectRatio` — 3:2, 16:9, 4:3, 1:1
- `SaveMedia` — Host, Camera, Host and Camera
- `SHUTTER_SPEED_TABLE` — hex code → human-readable string
- `F_NUMBER_TABLE` — hex code → "F2.8" etc.
- `ISO_TABLE` — hex code → "100", "200", "AUTO" etc.

## Logging

Enable detailed protocol logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Log levels:
- `INFO` — connection events, authentication, mode changes
- `DEBUG` — every PTP command, response, and data transfer

## Project Structure

```
python/
├── sony_camera_control/
│   ├── __init__.py         # Package exports
│   ├── camera.py           # High-level SonyCamera API
│   ├── ptp.py              # PTP/USB transport layer
│   ├── parser.py           # Binary protocol parser
│   ├── constants.py        # All opcodes, property codes, enums
│   └── exceptions.py       # Custom exception hierarchy
├── examples/
│   ├── basic_usage.py      # Read properties
│   ├── capture_photo.py    # Take a photo
│   ├── liveview_stream.py  # Stream LiveView frames
│   ├── change_settings.py  # Modify camera settings
│   └── zoom_control.py     # Zoom in/out
├── pyproject.toml           # Package metadata & build config
├── requirements.txt         # Dependencies
├── install.sh               # Linux/macOS setup script
├── install.bat              # Windows setup script
└── README.md                # This file
```

## Supported Cameras

This library should work with Sony cameras that support the Camera Remote Command SDK via PTP/USB.
Tested protocol versions:
- **v2** (SDK version 0x00C8 / 200)
- **v3** (SDK version 0x012C / 300)

To use v2, pass `version=0x00C8` when creating the camera:
```python
from sony_camera_control.constants import SDI_VERSION_V2
camera = SonyCamera(version=SDI_VERSION_V2)
```

## Relationship to C/C++ SDK

This Python library is a clean-room reimplementation of the protocol used in Sony's Camera Remote Command SDK examples:
- `example-v2-linux/` and `example-v3-linux/` — C++ with libusb
- `example-v2-windows/` and `example-v3-windows/` — C++ MFC application

The Python version provides the same functionality with a simpler API.

## License

MIT License. See [LICENSE](LICENSE) for details.

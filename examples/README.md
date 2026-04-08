# pysonycam — Examples

This directory contains runnable example scripts demonstrating the `pysonycam`
library.  Each script connects to the camera over USB, authenticates via the
Sony SDIO protocol, and exercises a specific area of the API.

## Setup

```bash
# 1. Install the library (from the repo root)
pip install -e .

# 2. Install core example dependencies (only libusb1 — already pulled in by step 1)
# Nothing extra needed for most examples.

# 3. For the four examples that use OpenCV (live_viewfinder, timelapse,
#    astrophotography, hfr_slow_motion):
pip install -r examples/requirements.txt
```

---

## Example index

### Capture & Shooting

| Script | Summary |
|---|---|
| [capture_photo.py](capture_photo.py) | Take a single still photo and save it to disk. Uses `fast_mode=True` and loops for 5 shots to show rapid multi-shot capture. **Start here for the simplest end-to-end example.** |
| [burst_capture.py](burst_capture.py) | Fire N frames sequentially by pulsing S2 once per shot while holding S1. Downloads each frame before the next shot. |
| [rapid_fire.py](rapid_fire.py) | Fire N frames with a full S1→S2→release cycle per shot — the pattern recommended by the SDK reference for preventing camera lock-up. |
| [continuous_burst.py](continuous_burst.py) | Hold S2 solid for a wall-clock duration and download all frames after. Captures at the camera's native burst fps. |
| [interactive_shutter.py](interactive_shutter.py) | AF+AE lock the camera then press **SPACE** to fire. Uses Windows `msvcrt` for keypress polling. Waits for each image before allowing the next shot. |

### Movie & Slow Motion

| Script | Summary |
|---|---|
| [hfr_slow_motion.py](hfr_slow_motion.py) | Control HFR (High Frame Rate) recording. Auto-loop mode records clips unattended; interactive mode responds to keyboard (SPACE=standby, R=record, S=status, Q=quit). Optional OpenCV status HUD. |
| [sq_mode_capture.py](sq_mode_capture.py) | Configure S&Q (Slow & Quick) mode, start/stop recording with `toggle_movie()`, and wait for the `MOVIE_REC_OPERATION_RESULTS` event confirming the clip was written. Optional card-content verification with `get_content_info_list()`. |

### Live View

| Script | Summary |
|---|---|
| [live_viewfinder.py](live_viewfinder.py) | Real-time OpenCV preview window. **1** captures a single shot shown inline; **2** fires a 9-shot burst displayed as a 3×3 grid; **q** quits. Requires `opencv-python`. |

### Content Management (SDIO Content API)

| Script | Summary |
|---|---|
| [browse_and_download.py](browse_and_download.py) | Browse the camera card with `get_content_info_list()`, download full files or proxy previews, and optionally delete items after download. CLI flags: `--list`, `--filter EXT`, `--proxy`, `--delete`, `--all`, `--index N`. |
| [download_videos.py](download_videos.py) | Download MP4 video files using three progressive fallback strategies: bare PTP (no auth) → SDIO content-transfer session → authenticated SDIO session. Handles folder recursion and interactive index selection. |

### Camera Configuration & Status

| Script | Summary |
|---|---|
| [basic_usage.py](basic_usage.py) | Connect, authenticate, and enumerate every device property with its raw and human-readable value. Reference starting point for exploring what properties your camera reports. |
| [change_settings.py](change_settings.py) | Read current exposure settings and modify ISO, aperture, exposure mode, and white balance. Compact reference for the property-write workflow. |
| [camera_status.py](camera_status.py) | Print a full diagnostic report: firmware version, SDIO vendor code version, lens metadata, battery info, media slot status (remaining shots/time), total object count, and async-results support flag. `--verbose` dumps all device properties. |
| [zoom_control.py](zoom_control.py) | Zoom in and out at a given speed using `zoom_in()` / `zoom_out()` / `zoom_stop()`. Reads the zoom scale property before and after each move. |

### Focus Control

| Script | Summary |
|---|---|
| [advanced_focus.py](advanced_focus.py) | Five selectable focus demos: focus-point placement (`set_focus_point`), magnifier on/off with zoom levels, continuous focus drive near/far (`focus_continuous`), zoom/focus position presets (save/load), and AF transition speed + subject-shift sensitivity settings. Run with `--demo NAME` or `--all` (default). |

### White Balance

| Script | Summary |
|---|---|
| [custom_white_balance.py](custom_white_balance.py) | Full custom WB measurement sequence: enter standby, execute the measurement, wait for the `CWB_CAPTURED_RESULT` event, and optionally apply R/B gain offsets. Demonstrates event-driven confirmation with `on_event()`. |

### Long Exposure & Time Lapse

| Script | Summary |
|---|---|
| [timelapse.py](timelapse.py) | Capture N frames at a fixed interval. Headless mode runs silently; live mode shows an OpenCV HUD with countdown, frame progress, and SPACE-to-shoot early. Optional automatic MP4 assembly using OpenCV VideoWriter (no ffmpeg needed). Requires `opencv-python` for live mode and video assembly. |
| [astrophotography.py](astrophotography.py) | Long-exposure astrophotography with three sub-modes: **fixed** (standard shutter code), **bulb** (exposures > 30 s via `BULB_START`/`BULB_STOP`), and **live** (OpenCV HUD with on-the-fly ISO/shutter/aperture/WB/focus adjustments). Requires `opencv-python` for live mode. |

### Event System

| Script | Summary |
|---|---|
| [event_listener.py](event_listener.py) | Register callbacks for `PROPERTY_CHANGED` and `CAPTURED_EVENT`, start the background event listener, and print incoming events for 30 seconds. Minimal reference for the `on_event()` / `start_event_listener()` API. |

---

## Dependency overview

| Dependency | Required by |
|---|---|
| `libusb1` | All scripts (via `pysonycam`) |
| `opencv-python` | `live_viewfinder.py`, `timelapse.py` (live/video mode), `astrophotography.py` (live mode), `hfr_slow_motion.py` (status HUD) |
| `numpy` | Same four scripts as `opencv-python` |

Install the optional dependencies:

```bash
pip install -r examples/requirements.txt
```

Scripts that use `cv2` / `numpy` import them inside a `try/except ImportError`
block and degrade gracefully — they will still run in headless mode without
those packages installed.

---

## Redundancy notes

The following decisions were made to keep the example set focused:

- **`liveview_stream.py` was removed** — it was a minimal wrapper around
  `liveview_stream()` that saved JPEG frames to disk. `live_viewfinder.py`
  covers the same API with a richer interactive workflow.
- **`burst_capture.py` and `rapid_fire.py` both remain** — although they look
  similar at a glance, they demonstrate *different* shutter-button patterns:
  burst pulses S2 while holding S1; rapid_fire does a full S1+S2 press/release
  cycle per shot. Both patterns appear in the SDK reference.
- **`download_videos.py` and `browse_and_download.py` both remain** — they
  operate at different layers. `download_videos.py` works without SDIO
  authentication (bare PTP / MTP mode); `browse_and_download.py` requires an
  authenticated SDIO session and uses the richer content-info API.

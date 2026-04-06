"""
Astrophotography: long-exposure, bulb mode, and live viewfinder.

Three modes are supported:

  fixed   — set a specific shutter speed (up to 30") in Manual mode and
             fire the shutter normally.
  bulb    — hold the shutter open for an arbitrary duration via S2 button.
             Use for exposures longer than 30s.
  live    — interactive OpenCV viewfinder with on-screen settings HUD and
             keyboard controls.  Press SPACE to capture.

Live mode keyboard controls
---------------------------
  i / I    ISO up / down
  s / S    Shutter slower (longer exposure) / faster (shorter)
  a / A    Aperture wider (lower F) / narrower (higher F)
  w / W    White balance next / previous preset
  f / F    Manual focus step near / far
  SPACE    Capture — fixed shutter fires immediately;
           Bulb mode: SPACE opens the shutter, SPACE again closes it early
           (or it closes automatically after --bulb-seconds)
  q        Quit

Recommended astrophotography settings
--------------------------------------
  Exposure mode  : Manual (set by this script)
  Focus mode     : Manual (set by this script — pre-focus on a bright star)
  ISO            : 3200–12800 (higher = more noise; test your sensor)
  Aperture       : Widest available (lowest F-number)
  Shutter speed  : 15–30s fixed; or Bulb for anything longer
  White balance  : Daylight or Color Temp (avoid AWB — it shifts between frames)

The 500 rule gives the max exposure before stars trail:
  max_shutter_s = 500 / (crop_factor * focal_length_mm)

Usage
-----
    python examples/astrophotography.py [--mode fixed|bulb|live] [options]

    --mode           'fixed' (default), 'bulb', or 'live'
    --exposure       Shutter speed in seconds for fixed mode (default: 25)
    --bulb-seconds   Default bulb duration in seconds (default: 60)
    --iso            ISO as decimal integer (default: 6400)
    --aperture       F-number code in hex (default: 0x0118 = F2.8)
    --frames         Number of frames for fixed/bulb modes (default: 1)
    --interval       Seconds between frames in a sequence (default: 5)
    --output         Output directory (default: astro_output/)
    --timeout        Override download timeout in seconds (0 = auto)
"""

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

# cv2 and numpy are optional — only required for --mode live
try:
    import cv2
    import numpy as np
    _CV2_AVAILABLE = True
except ImportError:
    _CV2_AVAILABLE = False

from pysonycam import SonyCamera, ExposureMode
from pysonycam.constants import (
    BatteryLevel,
    DeviceProperty,
    FocusMode,
    SaveMedia,
    WhiteBalance,
    SHOT_OBJECT_HANDLE,
    SHUTTER_SPEED_TABLE,
    F_NUMBER_TABLE,
    ISO_TABLE,
)
from pysonycam.exceptions import SonyCameraError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Ordered setting lists  (used for keyboard stepping in live mode)
# ---------------------------------------------------------------------------

# ISO: ascending by numeric value (index 0 = lowest ISO, last = highest)
_ISO_LIST: list[tuple[int, str]] = sorted(
    [(code, label) for code, label in ISO_TABLE.items() if label != "AUTO"],
    key=lambda x: x[0],
)

# Shutter speeds: parse all labelled values, sort fastest → slowest, append Bulb
BULB_CODE = 0x00000000


def _parse_shutter_secs(label: str) -> float | None:
    try:
        if label.endswith('"'):
            return float(label[:-1])
        if label.startswith("1/"):
            return 1.0 / float(label[2:])
        return None
    except (ValueError, ZeroDivisionError):
        return None


_SHUTTER_LIST: list[tuple[int, str, float]] = []
for _code, _label in SHUTTER_SPEED_TABLE.items():
    if _code == BULB_CODE:
        continue
    _secs = _parse_shutter_secs(_label)
    if _secs is not None:
        _SHUTTER_LIST.append((_code, _label, _secs))
_SHUTTER_LIST.sort(key=lambda x: x[2])          # fastest first
_SHUTTER_LIST.append((BULB_CODE, "Bulb", float("inf")))  # Bulb at end

# Aperture: ascending by code (lower code = wider aperture = lower F-number)
_APERTURE_LIST: list[tuple[int, str]] = sorted(
    F_NUMBER_TABLE.items(), key=lambda x: x[0]
)

# White balance presets useful for astrophotography
_WB_LIST: list[tuple[int, str]] = [
    (int(WhiteBalance.DAYLIGHT),   "Daylight"),
    (int(WhiteBalance.CLOUDY),     "Cloudy"),
    (int(WhiteBalance.SHADE),      "Shade"),
    (int(WhiteBalance.COLOR_TEMP), "ColorTemp"),
    (int(WhiteBalance.AWB),        "AWB"),
]


def _find_idx(lst: list, code: int, key_fn=lambda x: x[0]) -> int:
    for i, item in enumerate(lst):
        if key_fn(item) == code:
            return i
    return 0


# ---------------------------------------------------------------------------
# Helpers shared between all modes
# ---------------------------------------------------------------------------

def _iso_code_from_decimal(iso_decimal: int) -> int:
    for code, label in ISO_TABLE.items():
        if label == str(iso_decimal):
            return code
    log.warning("ISO %d not in ISO_TABLE; sending decimal value directly", iso_decimal)
    return iso_decimal


def _nearest_shutter_code(seconds: float) -> int:
    fixed = [(secs, code) for code, label, secs in _SHUTTER_LIST
             if secs != float("inf")]
    if not fixed:
        raise RuntimeError("No fixed shutter speeds found in table")
    best_secs, best_code = min(fixed, key=lambda x: abs(x[0] - seconds))
    if abs(best_secs - seconds) > 2:
        log.warning("Requested %.1fs; nearest available speed is %s",
                    seconds, SHUTTER_SPEED_TABLE.get(best_code, "?"))
    return best_code


def _setup_camera(camera: SonyCamera, iso: int, aperture: int) -> None:
    """Apply common Manual/MF astrophotography settings."""
    camera.set_mode("still")
    camera.set_save_media(SaveMedia.HOST)
    camera.set_exposure_mode(ExposureMode.MANUAL)
    camera.set_property(DeviceProperty.FOCUS_MODE, int(FocusMode.MANUAL), size=2)
    camera.set_iso(iso)
    camera.set_aperture(aperture)
    log.info("Camera ready — ISO %s  aperture %s",
             ISO_TABLE.get(iso, str(iso)),
             F_NUMBER_TABLE.get(aperture, f"0x{aperture:04X}"))


def _download_after_bulb(
    camera: SonyCamera,
    output_dir: Path,
    frame_num: int,
    exposure_actual: float,
    timeout: float,
    status_fn=None,
) -> bytes:
    """Wait for and download the image produced by a bulb exposure."""
    log.info("Waiting for image (Long-Exposure NR may add ~%.0fs)…", exposure_actual)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if status_fn:
            status_fn()
        try:
            info = camera.get_property(DeviceProperty.SHOOTING_FILE_INFO)
            val = info.current_value if isinstance(info.current_value, int) else 0
            if val & 0x8000:
                break
        except SonyCameraError:
            pass
        time.sleep(0.5)
    else:
        raise SonyCameraError(
            f"Bulb capture timed out after {timeout:.0f}s. "
            "Disable Long-Exposure NR on the camera or increase --timeout."
        )

    camera.get_object_info(SHOT_OBJECT_HANDLE)
    data = camera.get_object(SHOT_OBJECT_HANDLE)
    path = output_dir / f"astro_bulb_{frame_num:04d}.jpg"
    path.write_bytes(data)
    log.info("Saved → %s  (%d bytes)", path, len(data))
    camera._wait_for_shooting_file_info_clear(timeout=15.0)
    return data


# ---------------------------------------------------------------------------
# Fixed and bulb helpers for non-live modes
# ---------------------------------------------------------------------------

def capture_fixed(
    camera: SonyCamera,
    shutter_seconds: float,
    output_dir: Path,
    frame_num: int,
    timeout: float,
) -> bytes:
    code = _nearest_shutter_code(shutter_seconds)
    label = SHUTTER_SPEED_TABLE.get(code, f"0x{code:08X}")
    camera.set_shutter_speed(code)
    log.info("Frame %d — shutter: %s", frame_num, label)
    path = output_dir / f"astro_fixed_{frame_num:04d}.jpg"
    return camera.capture(output_path=path, timeout=timeout)


def capture_bulb(
    camera: SonyCamera,
    bulb_seconds: float,
    output_dir: Path,
    frame_num: int,
    timeout: float,
) -> bytes:
    camera.set_shutter_speed(BULB_CODE)
    camera.set_save_media(SaveMedia.HOST)
    camera._wait_for_property_value(DeviceProperty.SAVE_MEDIA, int(SaveMedia.HOST))
    camera._wait_for_liveview()
    camera._wait_for_shooting_file_info_clear(timeout=15.0)

    camera.control_device(DeviceProperty.S1_BUTTON, 0x0002)
    time.sleep(0.3)
    camera.control_device(DeviceProperty.S2_BUTTON, 0x0002)
    t_open = time.monotonic()
    log.info("  Shutter open — holding for %.1fs…", bulb_seconds)

    elapsed = 0.0
    while elapsed < bulb_seconds:
        remaining = bulb_seconds - elapsed
        time.sleep(min(10.0, remaining))
        elapsed = time.monotonic() - t_open
        if elapsed < bulb_seconds:
            log.info("  %.0fs / %.0fs elapsed…", elapsed, bulb_seconds)

    camera.control_device(DeviceProperty.S2_BUTTON, 0x0001)
    actual = time.monotonic() - t_open
    time.sleep(0.1)
    camera.control_device(DeviceProperty.S1_BUTTON, 0x0001)
    log.info("  Shutter closed after %.2fs", actual)

    return _download_after_bulb(camera, output_dir, frame_num, actual, timeout)


# ---------------------------------------------------------------------------
# Live mode — OpenCV viewfinder
# ---------------------------------------------------------------------------

# HUD layout constants
_PANEL_W  = 215    # left settings panel width (px)
_BAR_H    = 28     # bottom status bar height (px)
_FONT     = None   # assigned after cv2 import check

# BGR colour palette
_WHITE    = (255, 255, 255)
_YELLOW   = (0, 215, 255)
_CYAN     = (200, 200, 0)
_RED      = (50,  50,  240)
_GREEN    = (60,  210, 60)
_DIM      = (110, 110, 110)
_ORANGE   = (30,  165, 230)


class _AstroState:
    """Tracks the current index into each ordered setting list."""

    def __init__(self, iso_code: int, shutter_code: int, aperture_code: int, wb_code: int):
        self.iso_idx      = _find_idx(_ISO_LIST,      iso_code)
        self.shutter_idx  = _find_idx(_SHUTTER_LIST,  shutter_code, key_fn=lambda x: x[0])
        self.aperture_idx = _find_idx(_APERTURE_LIST, aperture_code)
        self.wb_idx       = _find_idx(_WB_LIST,       wb_code)
        self.battery_label: str  = ""
        self.status_msg:    str  = "Ready — SPACE to capture"
        # Bulb timing (managed by the inner live loop)
        self.in_bulb:       bool  = False
        self.bulb_start:    float = 0.0
        self.bulb_target:   float = 0.0

    # ── property: iso ──────────────────────────────────────────────────
    @property
    def iso_code(self)  -> int:  return _ISO_LIST[self.iso_idx][0]
    @property
    def iso_label(self) -> str:  return _ISO_LIST[self.iso_idx][1]

    # ── property: shutter ──────────────────────────────────────────────
    @property
    def shutter_code(self)  -> int:  return _SHUTTER_LIST[self.shutter_idx][0]
    @property
    def shutter_label(self) -> str:  return _SHUTTER_LIST[self.shutter_idx][1]
    @property
    def is_bulb(self)       -> bool: return self.shutter_code == BULB_CODE

    # ── property: aperture ─────────────────────────────────────────────
    @property
    def aperture_code(self)  -> int: return _APERTURE_LIST[self.aperture_idx][0]
    @property
    def aperture_label(self) -> str: return _APERTURE_LIST[self.aperture_idx][1]

    # ── property: white balance ────────────────────────────────────────
    @property
    def wb_code(self)  -> int: return _WB_LIST[self.wb_idx][0]
    @property
    def wb_label(self) -> str: return _WB_LIST[self.wb_idx][1]


def _decode_jpeg(data: bytes) -> "np.ndarray | None":
    arr = np.frombuffer(data, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def _battery_label(camera: SonyCamera) -> str:
    try:
        info = camera.get_property(DeviceProperty.BATTERY_LEVEL)
        lv = info.current_value
        table = {
            int(BatteryLevel.LEVEL_4_4): "Full",  int(BatteryLevel.LEVEL_3_4): "75%",
            int(BatteryLevel.LEVEL_2_4): "50%",   int(BatteryLevel.LEVEL_1_4): "25%",
            int(BatteryLevel.LEVEL_3_3): "Full",  int(BatteryLevel.LEVEL_2_3): "66%",
            int(BatteryLevel.LEVEL_1_3): "33%",   int(BatteryLevel.PRE_END):   "Low!",
            int(BatteryLevel.UNUSABLE):  "Dead",  int(BatteryLevel.USB_POWER): "USB",
        }
        return table.get(lv, f"0x{lv:02X}")
    except Exception:
        return ""


def _apply(camera: SonyCamera, prop: int, code: int, size: int,
           label: str, state: _AstroState) -> None:
    try:
        camera.set_property(prop, code, size=size)
        state.status_msg = f"Set {label}"
    except SonyCameraError as exc:
        state.status_msg = f"Error: {exc}"
        log.warning("Failed to set %s: %s", label, exc)


def _draw_hud(frame: "np.ndarray", state: _AstroState, frame_n: int) -> "np.ndarray":
    """Render the settings overlay onto the LiveView frame."""
    out = frame.copy()
    h, w = out.shape[:2]

    # Semi-transparent left panel
    overlay = out.copy()
    cv2.rectangle(overlay, (0, 0), (_PANEL_W, h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.55, out, 0.45, 0, out)

    # Semi-transparent bottom status bar
    overlay2 = out.copy()
    cv2.rectangle(overlay2, (0, h - _BAR_H), (w, h), (0, 0, 0), -1)
    cv2.addWeighted(overlay2, 0.60, out, 0.40, 0, out)

    FONT = cv2.FONT_HERSHEY_SIMPLEX
    y    = [26]   # mutable so the closure can update it

    def row(text: str, color=_WHITE, scale: float = 0.54,
            thickness: int = 1, dy: int = 22) -> None:
        cv2.putText(out, text, (8, y[0]), FONT, scale, color,
                    thickness, cv2.LINE_AA)
        y[0] += dy

    # ── Header ──────────────────────────────────────────────────────────
    row("─── ASTRO ───", _CYAN, scale=0.55, thickness=2, dy=28)

    # ── ISO ─────────────────────────────────────────────────────────────
    row(f"ISO  {state.iso_label}", _YELLOW, scale=0.58, dy=20)
    row("  i=up  I=down", _DIM, scale=0.40, dy=26)

    # ── Shutter ─────────────────────────────────────────────────────────
    ss_color = _RED if state.is_bulb else _YELLOW
    row(f"Shutter  {state.shutter_label}", ss_color, scale=0.58, dy=20)
    row("  s=slow  S=fast", _DIM, scale=0.40, dy=26)

    # ── Aperture ────────────────────────────────────────────────────────
    row(f"Aperture {state.aperture_label}", _YELLOW, scale=0.58, dy=20)
    row("  a=open  A=close", _DIM, scale=0.40, dy=26)

    # ── White balance ───────────────────────────────────────────────────
    row(f"WB  {state.wb_label}", _YELLOW, scale=0.56, dy=20)
    row("  w=next  W=prev", _DIM, scale=0.40, dy=26)

    # ── Focus ───────────────────────────────────────────────────────────
    row("Focus (Manual)", _YELLOW, scale=0.56, dy=20)
    row("  f=near  F=far", _DIM, scale=0.40, dy=30)

    # ── Battery ─────────────────────────────────────────────────────────
    if state.battery_label:
        warn = state.battery_label in ("Low!", "Dead", "25%")
        row(f"Battery  {state.battery_label}",
            _RED if warn else _GREEN, scale=0.50, dy=26)

    # ── Bulb timer / capture hint ────────────────────────────────────────
    if state.in_bulb:
        elapsed   = time.monotonic() - state.bulb_start
        remaining = max(0.0, state.bulb_target - elapsed)
        row(f"BULB  {elapsed:.0f}s / {state.bulb_target:.0f}s",
            _RED, scale=0.52, thickness=2, dy=22)
        row(f"  {remaining:.0f}s left", _ORANGE, scale=0.48, dy=22)
        row("  SPACE = close early", _DIM, scale=0.40, dy=22)
    else:
        row("SPACE: capture", _WHITE, scale=0.50, dy=20)
        if state.is_bulb:
            row("  (will open bulb)", _ORANGE, scale=0.44, dy=22)
        row("q: quit", _DIM, scale=0.44, dy=22)

    # ── Status bar (bottom) ───────────────────────────────────────────────
    cv2.putText(out, state.status_msg,
                (8, h - 8), FONT, 0.50, _WHITE, 1, cv2.LINE_AA)

    # ── Frame counter (top-right) ──────────────────────────────────────
    cv2.putText(out, f"#{frame_n}",
                (w - 60, 22), FONT, 0.48, _DIM, 1, cv2.LINE_AA)

    return out


def _refresh_display(window: str, camera: SonyCamera,
                     state: _AstroState, frame_n: int,
                     last_frame: "np.ndarray | None") -> "np.ndarray | None":
    """Grab a liveview frame, draw HUD, show in window. Returns the decoded frame."""
    try:
        raw = camera.get_liveview_frame()
        img = _decode_jpeg(raw) if raw else None
    except SonyCameraError:
        img = None
    if img is None:
        img = last_frame
    if img is not None:
        cv2.imshow(window, _draw_hud(img, state, frame_n))
    return img


def _bulb_live_capture(
    camera: SonyCamera,
    state: _AstroState,
    output_dir: Path,
    shot_num: int,
    window: str,
    frame_n_ref: list[int],
    last_frame: "np.ndarray | None",
) -> "np.ndarray | None":
    """Run one bulb exposure in live mode: open → countdown → close → download."""

    state.in_bulb    = True
    state.bulb_start = time.monotonic()
    state.bulb_target = state.bulb_target  # already set by caller

    camera.set_shutter_speed(BULB_CODE)
    camera.set_save_media(SaveMedia.HOST)
    camera._wait_for_property_value(DeviceProperty.SAVE_MEDIA, int(SaveMedia.HOST))
    camera._wait_for_liveview()
    camera._wait_for_shooting_file_info_clear(timeout=15.0)

    # Open shutter
    camera.control_device(DeviceProperty.S1_BUTTON, 0x0002)
    time.sleep(0.3)
    camera.control_device(DeviceProperty.S2_BUTTON, 0x0002)
    state.bulb_start = time.monotonic()     # reset after S2 press
    log.info("Bulb shutter open — target %.1fs", state.bulb_target)

    # Countdown loop — refresh display ~5 fps; SPACE closes early
    while True:
        elapsed = time.monotonic() - state.bulb_start
        state.status_msg = (f"BULB OPEN  {elapsed:.1f}s / {state.bulb_target:.0f}s"
                            f"  ({max(0, state.bulb_target - elapsed):.0f}s left)")
        frame_n_ref[0] += 1
        last_frame = _refresh_display(window, camera, state, frame_n_ref[0], last_frame)
        key = cv2.waitKey(200) & 0xFF
        if key == ord(' ') or elapsed >= state.bulb_target:
            break

    # Close shutter
    camera.control_device(DeviceProperty.S2_BUTTON, 0x0001)
    actual = time.monotonic() - state.bulb_start
    time.sleep(0.1)
    camera.control_device(DeviceProperty.S1_BUTTON, 0x0001)
    log.info("Bulb shutter closed after %.2fs", actual)
    state.in_bulb = False

    # Download — keep refreshing the display while we wait
    dl_timeout = actual * 2 + 60.0

    def _tick() -> None:
        frame_n_ref[0] += 1
        nonlocal last_frame
        last_frame = _refresh_display(window, camera, state, frame_n_ref[0], last_frame)
        cv2.waitKey(500)

    try:
        data = _download_after_bulb(camera, output_dir, shot_num,
                                    actual, dl_timeout, status_fn=_tick)
        state.status_msg = (f"Saved astro_bulb_{shot_num:04d}.jpg"
                            f"  ({len(data):,} bytes)")
    except SonyCameraError as exc:
        state.status_msg = f"Error: {exc}"
        log.error("Bulb download failed: %s", exc)

    return last_frame


def run_live_mode(camera: SonyCamera, args: argparse.Namespace, output_dir: Path) -> None:
    if not _CV2_AVAILABLE:
        print(
            "ERROR: Live mode requires opencv-python and numpy.\n"
            "Install with:  pip install opencv-python numpy\n"
            '           or  pip install -e ".[gui]"'
        )
        raise SystemExit(1)

    # Seed state from current camera values where possible
    try:
        props         = camera.get_all_properties()
        iso_code      = (props[DeviceProperty.ISO].current_value
                         if DeviceProperty.ISO in props
                         else _iso_code_from_decimal(args.iso))
        shutter_code  = (props[DeviceProperty.SHUTTER_SPEED].current_value
                         if DeviceProperty.SHUTTER_SPEED in props
                         else _nearest_shutter_code(args.exposure))
        aperture_code = (props[DeviceProperty.F_NUMBER].current_value
                         if DeviceProperty.F_NUMBER in props
                         else args.aperture)
        wb_code       = (props[DeviceProperty.WHITE_BALANCE].current_value
                         if DeviceProperty.WHITE_BALANCE in props
                         else int(WhiteBalance.DAYLIGHT))
    except Exception:
        iso_code      = _iso_code_from_decimal(args.iso)
        shutter_code  = _nearest_shutter_code(args.exposure)
        aperture_code = args.aperture
        wb_code       = int(WhiteBalance.DAYLIGHT)

    state = _AstroState(iso_code, shutter_code, aperture_code, wb_code)
    state.bulb_target = args.bulb_seconds

    WINDOW = "Astro LiveView"
    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW, 960, 640)

    shot_num   = 0
    frame_n    = [0]       # list so inner functions can mutate it
    last_frame = None      # last successfully decoded frame
    batt_t     = 0.0       # battery poll timer

    print(
        "\n  Keys: i/I=ISO  s/S=shutter  a/A=aperture  "
        "w/W=WB  f/F=focus  SPACE=capture  q=quit\n"
    )

    for raw_frame in camera.liveview_stream(count=0):
        frame_n[0] += 1
        img = _decode_jpeg(raw_frame)
        if img is None:
            continue
        last_frame = img

        # Refresh battery every ~15 s (avoids slowing the loop)
        now = time.monotonic()
        if now - batt_t > 15.0:
            state.battery_label = _battery_label(camera)
            batt_t = now

        cv2.imshow(WINDOW, _draw_hud(img, state, frame_n[0]))
        key = cv2.waitKey(1) & 0xFF

        if key == 0xFF:
            continue

        # ── ISO ────────────────────────────────────────────────────
        elif key == ord('i'):
            state.iso_idx = min(len(_ISO_LIST) - 1, state.iso_idx + 1)
            _apply(camera, DeviceProperty.ISO, state.iso_code, 4,
                   f"ISO {state.iso_label}", state)
        elif key == ord('I'):
            state.iso_idx = max(0, state.iso_idx - 1)
            _apply(camera, DeviceProperty.ISO, state.iso_code, 4,
                   f"ISO {state.iso_label}", state)

        # ── Shutter ────────────────────────────────────────────────
        elif key == ord('s'):   # slower / longer
            state.shutter_idx = min(len(_SHUTTER_LIST) - 1, state.shutter_idx + 1)
            if not state.is_bulb:
                _apply(camera, DeviceProperty.SHUTTER_SPEED, state.shutter_code, 4,
                       f"Shutter {state.shutter_label}", state)
            else:
                camera.set_shutter_speed(BULB_CODE)
                state.status_msg = "Shutter: Bulb — SPACE to open"
        elif key == ord('S'):   # faster / shorter
            state.shutter_idx = max(0, state.shutter_idx - 1)
            _apply(camera, DeviceProperty.SHUTTER_SPEED, state.shutter_code, 4,
                   f"Shutter {state.shutter_label}", state)

        # ── Aperture ───────────────────────────────────────────────
        elif key == ord('a'):   # wider (lower F)
            state.aperture_idx = max(0, state.aperture_idx - 1)
            _apply(camera, DeviceProperty.F_NUMBER, state.aperture_code, 2,
                   f"Aperture {state.aperture_label}", state)
        elif key == ord('A'):   # narrower (higher F)
            state.aperture_idx = min(len(_APERTURE_LIST) - 1, state.aperture_idx + 1)
            _apply(camera, DeviceProperty.F_NUMBER, state.aperture_code, 2,
                   f"Aperture {state.aperture_label}", state)

        # ── White balance ──────────────────────────────────────────
        elif key == ord('w'):
            state.wb_idx = (state.wb_idx + 1) % len(_WB_LIST)
            _apply(camera, DeviceProperty.WHITE_BALANCE, state.wb_code, 2,
                   f"WB {state.wb_label}", state)
        elif key == ord('W'):
            state.wb_idx = (state.wb_idx - 1) % len(_WB_LIST)
            _apply(camera, DeviceProperty.WHITE_BALANCE, state.wb_code, 2,
                   f"WB {state.wb_label}", state)

        # ── Focus ──────────────────────────────────────────────────
        elif key == ord('f'):
            camera.focus_near(step=1)
            state.status_msg = "Focus: stepped near"
        elif key == ord('F'):
            camera.focus_far(step=1)
            state.status_msg = "Focus: stepped far"

        # ── Capture ────────────────────────────────────────────────
        elif key == ord(' '):
            shot_num += 1
            if state.is_bulb:
                last_frame = _bulb_live_capture(
                    camera, state, output_dir, shot_num,
                    WINDOW, frame_n, last_frame,
                )
            else:
                state.status_msg = f"Capturing ({state.shutter_label})…"
                cv2.imshow(WINDOW, _draw_hud(img, state, frame_n[0]))
                cv2.waitKey(1)
                try:
                    path = output_dir / f"astro_fixed_{shot_num:04d}.jpg"
                    data = camera.capture(output_path=path,
                                          timeout=args.exposure + 90.0)
                    state.status_msg = (f"Saved astro_fixed_{shot_num:04d}.jpg"
                                        f"  ({len(data):,} bytes)")
                    log.info("Saved → %s  (%d bytes)", path, len(data))
                except SonyCameraError as exc:
                    state.status_msg = f"Capture failed: {exc}"
                    log.error("Capture error: %s", exc)

        # ── Quit ───────────────────────────────────────────────────
        elif key == ord('q'):
            log.info("Quit.")
            break

    cv2.destroyAllWindows()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Astrophotography: long-exposure, bulb, and live viewfinder",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--mode", choices=["fixed", "bulb", "live"], default="fixed",
                   help="Capture mode (default: fixed)")
    p.add_argument("--exposure", type=float, default=25.0,
                   help="Shutter speed in seconds for fixed mode (default: 25)")
    p.add_argument("--bulb-seconds", type=float, default=60.0,
                   help="Default bulb exposure duration in seconds (default: 60)")
    p.add_argument("--iso", type=int, default=6400,
                   help="ISO as decimal integer (default: 6400)")
    p.add_argument("--aperture", type=lambda x: int(x, 0), default=0x0118,
                   help="F-number code in hex (default: 0x0118 = F2.8)")
    p.add_argument("--frames", type=int, default=1,
                   help="Number of frames for fixed/bulb modes (default: 1)")
    p.add_argument("--interval", type=float, default=5.0,
                   help="Seconds between frames in a sequence (default: 5)")
    p.add_argument("--output", type=Path, default=Path("astro_output"),
                   help="Output directory (default: astro_output/)")
    p.add_argument("--timeout", type=float, default=0.0,
                   help="Override download timeout in seconds (0 = auto)")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    output_dir: Path = args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    iso_code = _iso_code_from_decimal(args.iso)

    if args.timeout > 0:
        timeout = args.timeout
    elif args.mode == "bulb":
        timeout = args.bulb_seconds * 2 + 60.0
    else:
        timeout = args.exposure + 90.0

    print(f"\n  Astrophotography — {args.mode.upper()} mode")
    print(f"  ISO: {ISO_TABLE.get(iso_code, str(args.iso))}"
          f"   Aperture: {F_NUMBER_TABLE.get(args.aperture, f'0x{args.aperture:04X}')}")
    print(f"  Output: {output_dir}/\n")
    print("  TIP: Pre-focus manually on a bright star before starting.")
    print("  TIP: Disable Long-Exposure NR on the camera to halve wait time.\n")

    with SonyCamera() as camera:
        camera.authenticate()
        log.info("Authenticated.")
        _setup_camera(camera, iso=iso_code, aperture=args.aperture)

        if args.mode == "live":
            run_live_mode(camera, args, output_dir)
        else:
            if args.mode == "fixed":
                camera.set_shutter_speed(_nearest_shutter_code(args.exposure))

            for frame_num in range(1, args.frames + 1):
                if frame_num > 1 and args.interval > 0:
                    log.info("Waiting %.1fs before next frame…", args.interval)
                    time.sleep(args.interval)
                if args.mode == "bulb":
                    capture_bulb(camera, args.bulb_seconds, output_dir, frame_num, timeout)
                else:
                    capture_fixed(camera, args.exposure, output_dir, frame_num, timeout)

            print(f"\n  Done — {args.frames} frame(s) saved to {output_dir}/")


if __name__ == "__main__":
    main()



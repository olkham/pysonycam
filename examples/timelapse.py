"""
Timelapse capture: shoot N frames at a fixed interval, with optional live
preview and automatic video assembly.

Two modes
---------
  headless  — shoot and save frames silently (default); ideal for long
              unattended sessions; no dependencies beyond the camera library.
  live      — OpenCV window shows the last captured frame, a countdown to
              the next shot, remaining frames, and a settings HUD.
              Press SPACE to trigger immediately, q to quit.

After all frames are captured the script can assemble them into an MP4 using
OpenCV's VideoWriter (no ffmpeg required).

Usage
-----
    python examples/timelapse.py [options]

    --frames      Total number of frames to capture (default: 60)
    --interval    Seconds between shots, measured shutter-to-shutter (default: 10)
    --exposure    Shutter speed in seconds; 0 = leave as-is on camera (default: 0)
    --iso         ISO as a decimal integer; 0 = leave as-is (default: 0)
    --aperture    F-number code in hex; 0 = leave as-is (default: 0)
    --output      Directory to save frames (default: timelapse_output/)
    --video       Assemble frames into a video file after capture (e.g. out.mp4)
    --fps         Playback fps for the assembled video (default: 24)
    --mode        'headless' (default) or 'live'
    --no-lv       Disable LiveView preview in 'live' mode (saves USB bandwidth)

Examples
--------
    # 100 frames every 30 s, leave exposure to the camera
    python examples/timelapse.py --frames 100 --interval 30

    # 200 frames every 5 s, ISO 400, assemble to video at 30 fps
    python examples/timelapse.py --frames 200 --interval 5 --iso 400 --video timelapse.mp4 --fps 30

    # Interactive live preview
    python examples/timelapse.py --frames 60 --interval 10 --mode live
"""

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

try:
    import cv2
    import numpy as np
    _CV2_AVAILABLE = True
except ImportError:
    _CV2_AVAILABLE = False

from pysonycam import SonyCamera, ExposureMode
from pysonycam.constants import (
    DeviceProperty,
    SaveMedia,
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
# Shutter speed: seconds → nearest code
# ---------------------------------------------------------------------------

def _parse_label_secs(label: str) -> float | None:
    try:
        if label.endswith('"'):
            return float(label[:-1])
        if label.startswith("1/"):
            return 1.0 / float(label[2:])
    except (ValueError, ZeroDivisionError):
        pass
    return None


_SHUTTER_BY_SECS: list[tuple[float, int, str]] = sorted(
    [
        (s, code, label)
        for code, label in SHUTTER_SPEED_TABLE.items()
        if code != 0 and (s := _parse_label_secs(label)) is not None
    ],
    key=lambda x: x[0],
)


def _nearest_shutter_code(seconds: float) -> tuple[int, str]:
    if not _SHUTTER_BY_SECS:
        raise RuntimeError("SHUTTER_SPEED_TABLE is empty")
    secs, code, label = min(_SHUTTER_BY_SECS, key=lambda x: abs(x[0] - seconds))
    if abs(secs - seconds) > 1:
        log.warning("Requested %.2fs shutter; nearest is %s", seconds, label)
    return code, label


def _iso_code(decimal: int) -> int:
    for code, label in ISO_TABLE.items():
        if label == str(decimal):
            return code
    log.warning("ISO %d not in table; sending raw decimal", decimal)
    return decimal


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

def _apply_settings(camera: SonyCamera, args: argparse.Namespace) -> dict[str, str]:
    """Apply whatever settings were requested; return a summary dict."""
    applied: dict[str, str] = {}

    if args.exposure > 0:
        code, label = _nearest_shutter_code(args.exposure)
        camera.set_shutter_speed(code)
        applied["Shutter"] = label

    if args.iso > 0:
        iso_code = _iso_code(args.iso)
        camera.set_iso(iso_code)
        applied["ISO"] = ISO_TABLE.get(iso_code, str(args.iso))

    if args.aperture > 0:
        camera.set_aperture(args.aperture)
        applied["Aperture"] = F_NUMBER_TABLE.get(args.aperture, f"0x{args.aperture:04X}")

    return applied


# ---------------------------------------------------------------------------
# Video assembly
# ---------------------------------------------------------------------------

def assemble_video(frame_paths: list[Path], output_path: Path, fps: float) -> None:
    """Write *frame_paths* as an MP4 video using OpenCV."""
    if not _CV2_AVAILABLE:
        log.warning("opencv-python not installed — skipping video assembly.")
        log.warning("Install with:  pip install opencv-python numpy")
        return
    if not frame_paths:
        log.warning("No frames to assemble.")
        return

    # Read the first frame to get dimensions
    first = cv2.imread(str(frame_paths[0]))
    if first is None:
        log.error("Could not read first frame: %s", frame_paths[0])
        return
    h, w = first.shape[:2]

    fourcc = cv2.VideoWriter.fourcc(*"mp4v")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(output_path), fourcc, fps, (w, h))
    if not writer.isOpened():
        log.error("Could not open VideoWriter for %s", output_path)
        return

    log.info("Assembling %d frames → %s at %.1f fps…", len(frame_paths), output_path, fps)
    for i, path in enumerate(frame_paths):
        img = cv2.imread(str(path))
        if img is None:
            log.warning("Skipping unreadable frame: %s", path)
            continue
        if img.shape[:2] != (h, w):
            img = cv2.resize(img, (w, h))
        writer.write(img)
        if (i + 1) % 50 == 0:
            log.info("  …wrote %d / %d frames", i + 1, len(frame_paths))

    writer.release()
    size_mb = output_path.stat().st_size / 1_048_576
    log.info("Video saved → %s  (%.1f MB)", output_path, size_mb)


# ---------------------------------------------------------------------------
# Headless capture
# ---------------------------------------------------------------------------

def run_headless(
    camera: SonyCamera,
    args: argparse.Namespace,
    output_dir: Path,
) -> list[Path]:
    """Capture frames silently, returning a list of saved file paths."""
    saved: list[Path] = []
    total = args.frames
    interval = args.interval

    for i in range(total):
        t_shot = time.monotonic()
        frame_path = output_dir / f"frame_{i:05d}.jpg"

        try:
            camera.capture(output_path=frame_path, timeout=max(30.0, args.exposure + 30))
            saved.append(frame_path)
            elapsed = time.monotonic() - t_shot
            log.info("[%d/%d] %s  (%.1fs)", i + 1, total, frame_path.name, elapsed)
        except SonyCameraError as exc:
            log.error("[%d/%d] Capture failed: %s", i + 1, total, exc)

        if i < total - 1:
            # Wait the remainder of the interval, accounting for capture time
            elapsed = time.monotonic() - t_shot
            wait = max(0.0, interval - elapsed)
            if wait > 0:
                log.info("  Next shot in %.1fs…", wait)
                time.sleep(wait)

    return saved


# ---------------------------------------------------------------------------
# Live mode
# ---------------------------------------------------------------------------

_FONT  = None   # assigned after CV2 check
_WHITE = (255, 255, 255)
_CYAN  = (200, 200, 0)
_GREEN = (60, 210, 60)
_RED   = (50,  50, 240)
_DIM   = (110, 110, 110)
_AMBER = (30, 165, 230)


def _decode_jpeg(data: bytes) -> "np.ndarray | None":
    arr = np.frombuffer(data, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def _draw_hud(
    base: "np.ndarray",
    settings: dict[str, str],
    frame_num: int,
    total: int,
    next_in: float,
    interval: float,
    status: str,
) -> "np.ndarray":
    """Overlay timelapse HUD on *base* frame."""
    out = base.copy()
    h, w = out.shape[:2]
    FONT = cv2.FONT_HERSHEY_SIMPLEX

    # Left panel background
    panel_w = 210
    overlay = out.copy()
    cv2.rectangle(overlay, (0, 0), (panel_w, h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.55, out, 0.45, 0, out)

    # Bottom status bar
    bar_h = 28
    overlay2 = out.copy()
    cv2.rectangle(overlay2, (0, h - bar_h), (w, h), (0, 0, 0), -1)
    cv2.addWeighted(overlay2, 0.60, out, 0.40, 0, out)

    y = [24]

    def row(text: str, color=_WHITE, scale: float = 0.54,
            thickness: int = 1, dy: int = 22) -> None:
        cv2.putText(out, text, (8, y[0]), FONT, scale, color,
                    thickness, cv2.LINE_AA)
        y[0] += dy

    row("─ TIMELAPSE ─", _CYAN, scale=0.55, thickness=2, dy=28)

    # Frame progress
    pct = int(100 * frame_num / total) if total else 0
    row(f"Frame  {frame_num} / {total}  ({pct}%)", _WHITE, scale=0.54, dy=22)

    # Countdown bar
    ratio   = 1.0 - min(1.0, next_in / interval) if interval > 0 else 1.0
    bar_len = panel_w - 16
    filled  = int(bar_len * ratio)
    bar_y   = y[0]
    cv2.rectangle(out, (8, bar_y), (8 + bar_len, bar_y + 10), (60, 60, 60), -1)
    cv2.rectangle(out, (8, bar_y), (8 + filled, bar_y + 10), _GREEN, -1)
    y[0] += 18

    bar_color = _RED if next_in < 3.0 else (_AMBER if next_in < 10.0 else _GREEN)
    row(f"Next in  {next_in:.1f}s", bar_color, scale=0.54, dy=26)
    row(f"Interval  {interval:.0f}s", _DIM, scale=0.44, dy=22)

    y[0] += 6
    row("Settings", _CYAN, scale=0.48, dy=20)
    for key, val in settings.items():
        row(f"  {key}: {val}", _DIM, scale=0.44, dy=18)

    y[0] += 8
    row("SPACE=shoot now", _WHITE, scale=0.48, dy=18)
    row("q=quit", _DIM, scale=0.44, dy=18)

    # Status bar
    cv2.putText(out, status,
                (8, h - 8), FONT, 0.48, _WHITE, 1, cv2.LINE_AA)

    return out


def run_live(
    camera: SonyCamera,
    args: argparse.Namespace,
    output_dir: Path,
    settings: dict[str, str],
) -> list[Path]:
    """Live timelapse mode: preview + countdown HUD, SPACE to shoot early."""
    if not _CV2_AVAILABLE:
        print(
            "ERROR: Live mode requires opencv-python and numpy.\n"
            "Install with:  pip install opencv-python numpy\n"
            '           or  pip install -e ".[gui]"'
        )
        raise SystemExit(1)

    WINDOW  = "Timelapse"
    total   = args.frames
    interval = args.interval
    saved:  list[Path] = []
    status  = "Waiting for first shot…"

    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW, 960, 640)

    last_img:   "np.ndarray | None" = None   # last decoded liveview frame
    last_shot:  "np.ndarray | None" = None   # last captured photo
    frame_num   = 0
    next_shot_t = time.monotonic()            # fire immediately on first iteration

    print(f"\n  SPACE = shoot now   q = quit\n")

    while frame_num < total:
        now     = time.monotonic()
        next_in = max(0.0, next_shot_t - now)

        # ── Grab a LiveView frame ──────────────────────────────────────
        if not args.no_lv:
            try:
                raw = camera.get_liveview_frame()
                img = _decode_jpeg(raw) if raw else None
                if img is not None:
                    last_img = img
            except SonyCameraError:
                pass

        display_base = last_img if last_img is not None else (
            last_shot if last_shot is not None else
            np.zeros((480, 720, 3), dtype=np.uint8)  # blank until first frame
        )

        hud = _draw_hud(display_base, settings, frame_num, total,
                        next_in, interval, status)
        cv2.imshow(WINDOW, hud)
        key = cv2.waitKey(50) & 0xFF   # 20 fps UI refresh

        force_shoot = key == ord(' ')

        if key == ord('q'):
            log.info("Quit by user after %d frame(s).", frame_num)
            break

        # ── Time to shoot? ──────────────────────────────────────────────
        if now >= next_shot_t or force_shoot:
            frame_num += 1
            frame_path = output_dir / f"frame_{frame_num:05d}.jpg"
            status = f"Capturing frame {frame_num}/{total}…"

            # Show updated HUD immediately before blocking on capture
            hud = _draw_hud(display_base, settings, frame_num, total,
                            0.0, interval, status)
            cv2.imshow(WINDOW, hud)
            cv2.waitKey(1)

            t_shot = time.monotonic()
            try:
                camera.capture(output_path=frame_path,
                               timeout=max(30.0, args.exposure + 30))
                saved.append(frame_path)
                elapsed = time.monotonic() - t_shot
                status = (f"Frame {frame_num}/{total} saved"
                          f"  ({elapsed:.1f}s) — {frame_path.name}")
                log.info("[%d/%d] %s  (%.1fs)", frame_num, total,
                         frame_path.name, elapsed)

                # Show the captured photo briefly as a thumbnail overlay
                captured_img = cv2.imread(str(frame_path))
                if captured_img is not None:
                    last_shot = captured_img
            except SonyCameraError as exc:
                status = f"Capture failed: {exc}"
                log.error("[%d/%d] %s", frame_num, total, exc)

            # Schedule next shot from the *intended* fire time (not wall clock)
            # to avoid drift accumulating across many frames.
            next_shot_t = t_shot + interval

    cv2.destroyAllWindows()
    return saved


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Timelapse: capture frames at a fixed interval",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--frames",    type=int,   default=60,
                   help="Total frames to capture (default: 60)")
    p.add_argument("--interval",  type=float, default=10.0,
                   help="Seconds between shots (default: 10)")
    p.add_argument("--exposure",  type=float, default=0.0,
                   help="Shutter speed in seconds; 0=leave camera setting (default: 0)")
    p.add_argument("--iso",       type=int,   default=0,
                   help="ISO decimal; 0=leave camera setting (default: 0)")
    p.add_argument("--aperture",  type=lambda x: int(x, 0), default=0,
                   help="F-number code hex; 0=leave camera setting (default: 0)")
    p.add_argument("--output",    type=Path,  default=Path("timelapse_output"),
                   help="Frame output directory (default: timelapse_output/)")
    p.add_argument("--video",     type=Path,  default=None,
                   help="Assemble frames into this video file after capture")
    p.add_argument("--fps",       type=float, default=24.0,
                   help="Playback fps for assembled video (default: 24)")
    p.add_argument("--mode",      choices=["headless", "live"], default="headless",
                   help="'headless' (default) or 'live' (OpenCV preview)")
    p.add_argument("--no-lv",     action="store_true",
                   help="Disable LiveView polling in live mode (saves USB bandwidth)")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    output_dir: Path = args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    total_duration = args.frames * args.interval
    h, m, s = int(total_duration // 3600), int((total_duration % 3600) // 60), int(total_duration % 60)

    print(f"\n  Timelapse — {args.mode.upper()} mode")
    print(f"  Frames:    {args.frames}")
    print(f"  Interval:  {args.interval}s")
    print(f"  Duration:  ~{h:02d}h {m:02d}m {s:02d}s")
    if args.exposure > 0:
        _, label = _nearest_shutter_code(args.exposure)
        print(f"  Shutter:   {label}")
    if args.iso > 0:
        print(f"  ISO:       {ISO_TABLE.get(_iso_code(args.iso), str(args.iso))}")
    if args.aperture > 0:
        print(f"  Aperture:  {F_NUMBER_TABLE.get(args.aperture, f'0x{args.aperture:04X}')}")
    if args.video:
        print(f"  Video:     {args.video}  @ {args.fps} fps")
    print(f"  Output:    {output_dir}/\n")

    with SonyCamera() as camera:
        camera.authenticate()
        log.info("Authenticated.")

        camera.set_mode("still")
        camera.set_save_media(SaveMedia.HOST)

        settings = _apply_settings(camera, args)

        if not settings:
            settings["Exposure"] = "camera default"

        if args.mode == "live":
            saved = run_live(camera, args, output_dir, settings)
        else:
            saved = run_headless(camera, args, output_dir)

    print(f"\n  Captured {len(saved)} / {args.frames} frames → {output_dir}/")

    if args.video and saved:
        assemble_video(saved, args.video, args.fps)
    elif args.video and not saved:
        print("  No frames captured — skipping video assembly.")

    if saved and not args.video:
        print(
            f"\n  Tip: assemble into a video with:\n"
            f"    python examples/timelapse.py --output {output_dir}"
            f" --video out.mp4 --fps {int(args.fps)}\n"
            f"  (re-run with same --output; it will skip capture if you add 0 frames,\n"
            f"   or use ffmpeg:  ffmpeg -framerate {int(args.fps)}"
            f" -i {output_dir}/frame_%05d.jpg -c:v libx264 out.mp4)"
        )


if __name__ == "__main__":
    main()

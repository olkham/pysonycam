"""
HFR (High Frame Rate) slow-motion recording — fully unattended loop.

Controls the camera's HFR mode via PTP/USB:

    1. Set HFR exposure mode (camera must be on Movie/HFR dial position)
    2. Enter STBY (standby / high-fps buffering) via PTP ``HFR_STANDBY``
    3. Wait for an external trigger **or** auto-trigger after a delay
    4. Record the HFR clip (camera processes ~70-90 s at 960 fps)
    5. Return to Movie Rec mode → re-enter STBY
    6. Repeat forever (Ctrl-C to stop)

Note: Clips are saved to the camera's SD card. Downloading via USB is not
supported in PC Remote mode — retrieve files by removing the SD card or
switching the camera to MTP/Mass Storage mode.

HFR camera settings (must be configured on camera body before starting):
    - Frame rate:       240 / 480 / 960 / 1000 fps
    - Trigger timing:   Start / End / End Half
    - Recording quality / format

Usage
-----
    python examples/hfr_slow_motion.py [options]

    Options:
        --mode P|A|S|M      HFR sub-mode (default: P)
        --auto-trigger SEC  Auto-trigger after SEC seconds in STBY (0 = manual)
        --loop N            Number of clips to record (0 = infinite, default 0)
        --interactive       Run in interactive mode with keyboard commands

Controls (interactive mode)
---------------------------
    SPACE   Enter / re-enter HFR STBY (high-fps buffering)
    R       Trigger recording (camera must be in STBY)
    S       Show current camera status
    Q       Quit
"""

import argparse
import time
import logging

try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

from pysonycam import SonyCamera, DeviceProperty, ExposureMode
from pysonycam.constants import OperatingMode
from pysonycam.format import format_value

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

HFR_MODES = {
    "P": ExposureMode.HFR_P,
    "A": ExposureMode.HFR_A,
    "S": ExposureMode.HFR_S,
    "M": ExposureMode.HFR_M,
}

# Movie recording status values
MOVIE_STOPPED = 0x00
MOVIE_RECORDING = 0x01
MOVIE_UNABLE = 0x02

WINDOW_LIVE = "HFR LiveView"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def decode_jpeg(data: bytes):
    """Decode JPEG bytes to an OpenCV BGR image. Returns None on failure."""
    if not HAS_CV2 or not data:
        return None
    arr = np.frombuffer(data, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def show_liveview(camera: SonyCamera, duration: float = 0, poll_key: bool = True) -> int:
    """Show the LiveView feed in an OpenCV window.

    Parameters
    ----------
    camera : SonyCamera
        Connected and authenticated camera.
    duration : float
        How long to show the feed in seconds. 0 = show one frame and return.
    poll_key : bool
        Whether to poll for key presses and return them.

    Returns
    -------
    int
        The key code pressed (0 if none / no OpenCV).
    """
    if not HAS_CV2:
        return 0

    deadline = time.monotonic() + duration if duration > 0 else 0
    key = 0

    while True:
        try:
            frame = camera.get_liveview_frame()
            img = decode_jpeg(frame)
            if img is not None:
                cv2.imshow(WINDOW_LIVE, img)
        except Exception:
            pass

        if poll_key:
            k = cv2.waitKey(30) & 0xFF
            if k != 0xFF:
                key = k
                break
        else:
            cv2.waitKey(1)

        if deadline and time.monotonic() >= deadline:
            break

    return key


def liveview_wait(camera: SonyCamera, seconds: float, log_interval: int = 10) -> int:
    """Wait for *seconds* while showing the LiveView feed.

    Returns the key code if a key was pressed, else 0.
    """
    if not HAS_CV2:
        # Fall back to plain sleep with countdown
        for remaining in range(int(seconds), 0, -1):
            time.sleep(1.0)
            if remaining % log_interval == 0 and remaining != int(seconds):
                print(f"       {remaining}s remaining...")
        return 0

    deadline = time.monotonic() + seconds
    last_log = time.monotonic()
    while time.monotonic() < deadline:
        try:
            frame = camera.get_liveview_frame()
            img = decode_jpeg(frame)
            if img is not None:
                remaining = max(0, int(deadline - time.monotonic()))
                cv2.setWindowTitle(WINDOW_LIVE, f"HFR LiveView  [{remaining}s]")
                cv2.imshow(WINDOW_LIVE, img)
        except Exception:
            pass

        k = cv2.waitKey(30) & 0xFF
        if k != 0xFF:
            return k

        now = time.monotonic()
        if now - last_log >= log_interval:
            remaining = max(0, int(deadline - now))
            print(f"       {remaining}s remaining...")
            last_log = now

    return 0


def get_movie_status(camera: SonyCamera) -> int:
    try:
        return camera.get_property(DeviceProperty.MOVIE_REC).current_value
    except Exception:
        return -1


def print_status(camera: SonyCamera) -> None:
    try:
        exp = camera.get_property(DeviceProperty.EXPOSURE_MODE)
        print(f"  Exposure mode : {format_value(DeviceProperty.EXPOSURE_MODE, exp.current_value)}")
    except Exception:
        pass

    movie = get_movie_status(camera)
    names = {0x00: "Stopped", 0x01: "Recording", 0x02: "Unable to Record"}
    print(f"  Movie status  : {names.get(movie, f'Unknown (0x{movie:02X})')}")

    for prop, label in [
        (DeviceProperty.ISO, "ISO"),
        (DeviceProperty.SHUTTER_SPEED, "Shutter speed"),
        (DeviceProperty.F_NUMBER, "Aperture"),
    ]:
        try:
            info = camera.get_property(prop)
            print(f"  {label:14s}: {format_value(prop, info.current_value)}")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# HFR STBY control  (0xD2D5 — the PTP equivalent of the center button)
# ---------------------------------------------------------------------------

def enter_hfr_standby(camera: SonyCamera) -> bool:
    """Send HFR Standby Down+Up to enter (or re-enter) STBY buffering.

    Returns True on success, False on error.
    """
    try:
        camera.control_device(DeviceProperty.HFR_STANDBY, 0x0002)  # Down
        time.sleep(0.3)
        camera.control_device(DeviceProperty.HFR_STANDBY, 0x0001)  # Up
        log.info("HFR_STANDBY command sent")
        return True
    except Exception as e:
        log.error("HFR Standby failed: %s", e)
        return False


def cancel_hfr_recording(camera: SonyCamera) -> bool:
    """Send HFR Recording Cancel (0xD2D6) Down+Up."""
    try:
        camera.control_device(DeviceProperty.HFR_RECORDING_CANCEL, 0x0002)
        time.sleep(0.3)
        camera.control_device(DeviceProperty.HFR_RECORDING_CANCEL, 0x0001)
        log.info("HFR_RECORDING_CANCEL sent")
        return True
    except Exception as e:
        log.error("HFR Recording Cancel failed: %s", e)
        return False


# ---------------------------------------------------------------------------
# Trigger recording
# ---------------------------------------------------------------------------

def trigger_recording(camera: SonyCamera) -> bool:
    """Trigger HFR recording via MOVIE_REC button press+release."""
    try:
        camera.control_device(DeviceProperty.MOVIE_REC, 0x0002)
        time.sleep(0.3)
        camera.control_device(DeviceProperty.MOVIE_REC, 0x0001)
        log.info("MOVIE_REC trigger sent")
        return True
    except Exception as e:
        log.error("REC trigger failed: %s", e)
        return False


def _draw_processing_overlay(img, elapsed: int, status_text: str) -> None:
    """Draw a semi-transparent status banner at the top of *img* in-place."""
    h, w = img.shape[:2]
    banner_h = max(50, h // 12)
    overlay = img.copy()
    cv2.rectangle(overlay, (0, 0), (w, banner_h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.55, img, 0.45, 0, img)
    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(img, f"Processing... {elapsed}s  [{status_text}]  C=Cancel",
                (10, banner_h - 12), font, 0.6, (0, 220, 255), 1, cv2.LINE_AA)


def wait_for_processing(camera: SonyCamera, timeout: int = 120) -> str:
    """Wait for HFR processing to complete.

    HFR processing typically takes 70-90 seconds at 960 fps.  The camera
    encodes the high-speed buffer into an MP4 on the SD card.

    Returns one of:
        ``"complete"``   – processing finished (or assumed done after timeout)
        ``"cancelled"``  – user pressed C / cancel succeeded
        ``"timeout"``    – timeout elapsed without a clear done signal

    When OpenCV is available the LiveView window stays responsive; the last
    good frame is frozen with a status overlay so the user can see progress
    and press C to cancel.
    """
    log.info("Waiting for HFR processing (up to %ds)...", timeout)

    prev_status = get_movie_status(camera)
    status_names = {0x00: "Stopped", 0x01: "Recording", 0x02: "Unable", -1: "Error"}
    log.info("  Initial movie status: 0x%02X (%s)",
             prev_status & 0xFF, status_names.get(prev_status, "?"))

    if not HAS_CV2:
        # ---- text-only fallback (no OpenCV) --------------------------------
        for elapsed in range(timeout):
            time.sleep(1.0)
            status = get_movie_status(camera)
            if status != prev_status and prev_status >= 0 and status >= 0:
                log.info("  Movie status changed: 0x%02X → 0x%02X at %ds",
                         prev_status, status, elapsed + 1)
            if elapsed >= 10 and status in (MOVIE_STOPPED, MOVIE_UNABLE):
                if status != prev_status or elapsed >= 60:
                    log.info("Processing complete (%ds)", elapsed + 1)
                    return "complete"
            prev_status = status
            if elapsed % 15 == 14:
                log.info("  Still processing... %ds, status=0x%02X (%s)",
                         elapsed + 1, status & 0xFF, status_names.get(status, "?"))
        if timeout >= 90:
            log.info("Timeout reached (%ds) — assuming processing complete", timeout)
            return "complete"
        log.warning("Processing timeout (%ds). Last status: 0x%02X", timeout, prev_status)
        return "timeout"

    # ---- OpenCV-aware loop (keeps the window responsive) -------------------
    last_frame = None          # last successfully decoded liveview frame
    start = time.monotonic()
    last_status_poll = start   # when we last called get_movie_status

    while True:
        now = time.monotonic()
        elapsed = int(now - start)

        if elapsed >= timeout:
            break

        # Poll movie status at most once per second
        if now - last_status_poll >= 1.0:
            status = get_movie_status(camera)
            last_status_poll = now
            if status != prev_status and prev_status >= 0 and status >= 0:
                log.info("  Movie status changed: 0x%02X → 0x%02X at %ds",
                         prev_status, status, elapsed)
            if elapsed >= 10 and status in (MOVIE_STOPPED, MOVIE_UNABLE):
                if status != prev_status or elapsed >= 60:
                    log.info("Processing complete (%ds)", elapsed)
                    cv2.setWindowTitle(WINDOW_LIVE, "HFR LiveView")
                    return "complete"
            prev_status = status
            if elapsed % 15 == 0 and elapsed > 0:
                log.info("  Still processing... %ds, status=0x%02X (%s)",
                         elapsed, status & 0xFF, status_names.get(status, "?"))
        else:
            status = prev_status

        # Try to grab a fresh liveview frame; fall back to the frozen one
        try:
            raw = camera.get_liveview_frame()
            img = decode_jpeg(raw)
            if img is not None:
                last_frame = img.copy()
        except Exception:
            pass

        # Display last good frame with overlay (or a black placeholder)
        if last_frame is not None:
            display = last_frame.copy()
        else:
            display = np.zeros((480, 640, 3), dtype=np.uint8)

        status_text = status_names.get(status, "?")
        _draw_processing_overlay(display, elapsed, status_text)
        cv2.setWindowTitle(WINDOW_LIVE, f"HFR Processing...  {elapsed}s")
        cv2.imshow(WINDOW_LIVE, display)

        k = cv2.waitKey(30) & 0xFF
        if k == ord('c'):
            print("\nCancelling recording...")
            cancel_hfr_recording(camera)
            cv2.setWindowTitle(WINDOW_LIVE, "HFR LiveView")
            return "cancelled"

    # Timeout path
    if timeout >= 90:
        log.info("Timeout reached (%ds) — assuming processing complete", timeout)
        cv2.setWindowTitle(WINDOW_LIVE, "HFR LiveView")
        return "complete"

    log.warning("Processing timeout (%ds). Last status: 0x%02X", timeout, prev_status)
    cv2.setWindowTitle(WINDOW_LIVE, "HFR LiveView")
    return "timeout"


# ---------------------------------------------------------------------------
# Setup: connect, authenticate, prepare HFR mode
# ---------------------------------------------------------------------------

def setup_camera(camera: SonyCamera, hfr_mode: int) -> None:
    """Connect, authenticate, and prepare the camera for HFR recording."""
    camera.authenticate()
    print("[OK] Authenticated")

    # Check operating mode — if already Movie Rec, don't force set_mode
    try:
        op = camera.get_property(DeviceProperty.OPERATING_MODE)
        current = op.current_value
        log.info("Operating mode: 0x%02X", current)
        if current == OperatingMode.MOVIE_REC:
            print("[OK] Already in Movie Rec mode")
        else:
            print("     Switching to Movie Rec mode...")
            camera.set_mode("movie")
            print("[OK] Movie Rec mode set")
    except Exception:
        try:
            camera.set_mode("movie")
            print("[OK] Movie Rec mode set")
        except Exception as e:
            print(f"[WARN] Could not set Movie mode: {e}")
            print("       Ensure camera dial is on HFR/Movie.")

    # Set HFR exposure mode
    try:
        camera.set_exposure_mode(hfr_mode)
        time.sleep(0.5)
        mode_name = {v: k for k, v in HFR_MODES.items()}.get(hfr_mode, "?")
        print(f"[OK] Exposure mode: HFR ({mode_name})")
    except Exception as e:
        print(f"[WARN] Could not set HFR exposure: {e}")
        print("       Camera may already be in HFR mode via dial.")

    print()
    print("Status:")
    print_status(camera)
    print()


# ---------------------------------------------------------------------------
# Main loops
# ---------------------------------------------------------------------------

def unattended_loop(
    camera: SonyCamera,
    auto_trigger_delay: int,
    max_clips: int,
    hfr_mode: int = ExposureMode.HFR_P,
) -> None:
    """Fully unattended HFR capture loop.

    1. Enter STBY
    2. Wait auto_trigger_delay seconds, then trigger
    3. Wait for processing
    4. Restore HFR mode and re-enter STBY
    5. Repeat
    """
    clip_num = 0

    while max_clips == 0 or clip_num < max_clips:
        clip_num += 1
        print(f"\n{'='*50}")
        print(f"  Clip {clip_num}" + (f" / {max_clips}" if max_clips else ""))
        print(f"{'='*50}")

        # Step 1: Enter HFR STBY
        print("\n[1/4] Entering HFR STBY (buffering)...")
        if not enter_hfr_standby(camera):
            print("[ERROR] Could not enter STBY. Retrying in 5s...")
            time.sleep(5.0)
            continue

        # Give camera time to start buffering
        time.sleep(2.0)
        print("[OK] Camera should now be in STBY (buffering at high fps)")

        # Step 2: Wait before trigger (with LiveView)
        if auto_trigger_delay > 0:
            print(f"\n[2/4] Waiting {auto_trigger_delay}s before trigger (LiveView active)...")
            key = liveview_wait(camera, auto_trigger_delay)
            if key == ord('q'):
                print("\nUser quit during wait.")
                break
        else:
            print("\n[2/4] Triggering immediately...")

        # Step 3: Trigger recording
        print("\n[3/4] Triggering HFR recording...")
        if not trigger_recording(camera):
            print("[ERROR] Trigger failed. Canceling and retrying...")
            cancel_hfr_recording(camera)
            time.sleep(3.0)
            continue

        # Step 4: Wait for processing then restore mode for next cycle
        print("\n[4/4] Waiting for HFR processing...  (C=Cancel)")
        result = wait_for_processing(camera, timeout=120)
        if result == "cancelled":
            print("[INFO] Recording cancelled.")
        else:
            time.sleep(5.0)
            print("      Clip saved to camera SD card.")
        print("      Restoring HFR mode for next recording...")
        try:
            camera.set_mode("movie")
        except Exception as e:
            log.warning("Could not restore Movie mode: %s", e)
        time.sleep(0.5)
        try:
            camera.set_exposure_mode(hfr_mode)
        except Exception as e:
            log.warning("Could not restore HFR exposure: %s", e)
        time.sleep(2.0)

    print(f"\nCompleted {clip_num} clip(s).")


def interactive_loop(
    camera: SonyCamera, hfr_mode: int = ExposureMode.HFR_P
) -> None:
    """Interactive keyboard-driven HFR control with LiveView."""
    if HAS_CV2:
        print("Controls (LiveView window must be focused for key presses):")
        print("  SPACE   Enter / re-enter HFR STBY")
        print("  R       Trigger recording (must be in STBY)")
        print("  S       Show camera status")
        print("  Q       Quit")
        print()
        cv2.namedWindow(WINDOW_LIVE, cv2.WINDOW_NORMAL)

        while True:
            key = show_liveview(camera, duration=0, poll_key=True)

            if key == ord('q'):
                print("\nQuitting...")
                break

            elif key == ord(' '):
                print("Entering HFR STBY...")
                if enter_hfr_standby(camera):
                    time.sleep(2.0)
                    print("[OK] STBY active — buffering at high fps. Press R to trigger.")
                else:
                    print("[ERROR] Could not enter STBY.")

            elif key == ord('r'):
                print("Triggering recording...")
                if not trigger_recording(camera):
                    print("[ERROR] Trigger failed. Is camera in STBY?")
                    continue
                print("[OK] Triggered — processing...  (C=Cancel)")
                result = wait_for_processing(camera, timeout=120)
                if result == "cancelled":
                    print("[INFO] Recording cancelled.")
                else:
                    time.sleep(5.0)
                    print("      Clip saved to camera SD card.")
                try:
                    camera.set_mode("movie")
                    camera.set_exposure_mode(hfr_mode)
                except Exception:
                    pass
                print("[OK] HFR mode restored. Press SPACE to re-enter STBY.")

            elif key == ord('s'):
                print("Status:")
                print_status(camera)

            elif key == ord('c'):
                cancel_hfr_recording(camera)
                print("[OK] Recording canceled.")

        cv2.destroyAllWindows()

    else:
        # Fallback: text-only interactive mode (no OpenCV)
        print("Controls:")
        print("  ENTER   Enter / re-enter HFR STBY")
        print("  R       Trigger recording (must be in STBY)")
        print("  S       Show camera status")
        print("  Q       Quit")
        print("  (Install opencv-python for LiveView: pip install opencv-python numpy)")
        print()

        while True:
            try:
                cmd = input("> ").strip().upper()
            except (EOFError, KeyboardInterrupt):
                print("\nExiting...")
                break

            if cmd == "Q":
                break

            elif cmd == "":
                print("Entering HFR STBY...")
                if enter_hfr_standby(camera):
                    time.sleep(2.0)
                    print("[OK] STBY active — buffering at high fps. Press R to trigger.")
                else:
                    print("[ERROR] Could not enter STBY.")

            elif cmd == "R":
                print("Triggering recording...")
                if not trigger_recording(camera):
                    print("[ERROR] Trigger failed. Is camera in STBY?")
                    continue
                print("[OK] Triggered — processing...")
                result = wait_for_processing(camera, timeout=120)
                if result == "cancelled":
                    print("[INFO] Recording cancelled.")
                else:
                    time.sleep(5.0)
                    print("      Clip saved to camera SD card.")
                try:
                    camera.set_mode("movie")
                    camera.set_exposure_mode(hfr_mode)
                except Exception:
                    pass
                print("[OK] HFR mode restored. Press ENTER to re-enter STBY.")

            elif cmd == "S":
                print("Status:")
                print_status(camera)

            elif cmd == "C":
                cancel_hfr_recording(camera)
                print("[OK] Recording canceled.")

            else:
                print(f"Unknown: {cmd}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="HFR slow-motion capture — unattended or interactive",
    )
    p.add_argument("--mode", default="P", choices=["P", "A", "S", "M"],
                    help="HFR exposure sub-mode (default: P)")
    p.add_argument("--auto-trigger", type=int, default=5, metavar="SEC",
                    help="Seconds to wait in STBY before auto-triggering (default: 5)")
    p.add_argument("--loop", type=int, default=0, metavar="N",
                    help="Number of clips (0 = infinite, default: 0)")
    p.add_argument("--interactive", action="store_true",
                    help="Interactive keyboard mode instead of auto-loop")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    hfr_mode = HFR_MODES[args.mode]

    print(f"HFR Slow Motion — mode: HFR ({args.mode})")
    print("=" * 50)
    if HAS_CV2:
        print("LiveView: enabled (opencv-python detected)")
    else:
        print("LiveView: disabled (install opencv-python numpy for live preview)")
    print()
    print("Camera requirements:")
    print("  - Dial set to HFR / Movie position")
    print("  - Frame rate configured (240/480/960/1000 fps)")
    print("  - Trigger timing set (Start/End/End Half)")
    print()

    with SonyCamera() as camera:
        setup_camera(camera, hfr_mode)

        if args.interactive:
            interactive_loop(camera, hfr_mode)
        else:
            print(f"Auto-trigger delay: {args.auto_trigger}s")
            print(f"Max clips: {'unlimited' if args.loop == 0 else args.loop}")
            print("Clips saved to camera SD card.")
            print()
            print("Starting unattended loop (Ctrl-C to stop)...")
            try:
                unattended_loop(
                    camera, args.auto_trigger, args.loop, hfr_mode
                )
            except KeyboardInterrupt:
                print("\n\nStopped by user.")

    print("Done.")


if __name__ == "__main__":
    main()

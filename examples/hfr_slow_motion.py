"""
HFR (High Frame Rate) slow-motion recording — fully unattended loop.

Turns a Sony camera into an unlimited-storage high-speed camera by looping:

    1. Set HFR exposure mode (camera must be on Movie/HFR dial position)
    2. Enter STBY (standby / high-fps buffering) via PTP ``HFR_STANDBY``
    3. Wait for an external trigger **or** auto-trigger after a delay
    4. Record the HFR clip (camera processes ~70-90 s at 960 fps)
    5. Switch to Contents Transfer mode and download the MP4
    6. Return to Movie Rec mode → re-enter STBY
    7. Repeat forever (Ctrl-C to stop)

All clips are saved to disk on the host machine, giving effectively
unlimited recording storage.

HFR camera settings (must be configured on camera body before starting):
    - Frame rate:       240 / 480 / 960 / 1000 fps
    - Trigger timing:   Start / End / End Half
    - Recording quality / format

Usage
-----
    python examples/hfr_slow_motion.py [options]

    Options:
        --mode P|A|S|M      HFR sub-mode (default: P)
        --output DIR        Output directory (default: hfr_output/)
        --auto-trigger SEC  Auto-trigger after SEC seconds in STBY (0 = manual)
        --loop N            Number of clips to record (0 = infinite, default 0)
        --interactive       Run in interactive mode with keyboard commands

Controls (interactive mode)
---------------------------
    ENTER   Enter / re-enter HFR STBY (high-fps buffering)
    R       Trigger recording (camera must be in STBY)
    D       Download the latest HFR clip from the camera
    S       Show current camera status
    Q       Quit
"""

import argparse
import struct
import sys
import time
import logging
from pathlib import Path

from pysonycam import SonyCamera, DeviceProperty, ExposureMode
from pysonycam.constants import SDIOOpCode, OperatingMode
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

# PTP object format codes
FORMAT_FOLDER = 0x3001
FORMAT_MP4 = 0xB982
STORAGE_ID = 0x00010001

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def parse_object_info(data: bytes) -> dict:
    if len(data) < 53:
        return {}
    storage_id, obj_format, protect, obj_size = struct.unpack_from("<IHHI", data, 0)
    offset = 52
    filename = ""
    if offset < len(data):
        name_len = data[offset]
        offset += 1
        if name_len > 0 and offset + name_len * 2 <= len(data):
            filename = data[offset:offset + (name_len - 1) * 2].decode("utf-16-le", errors="replace")
    return {"storage_id": storage_id, "format": obj_format, "size": obj_size, "filename": filename}


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


def wait_for_processing(camera: SonyCamera, timeout: int = 120) -> bool:
    """Wait for HFR processing to complete.

    HFR processing typically takes 70-90 seconds at 960 fps.  The camera
    encodes the high-speed buffer into an MP4 on the SD card.

    Detection strategy:
    - Log the actual movie status every 15 seconds for diagnostics.
    - Detect status *changes* (e.g. RECORDING→STOPPED means done).
    - After >= 10 seconds, accept STOPPED or UNABLE as completion.
    - For timeouts >= 90 s, assume processing is done (it almost
      certainly finished within 90 s for HFR).
    """
    log.info("Waiting for HFR processing (up to %ds)...", timeout)

    prev_status = get_movie_status(camera)
    status_names = {0x00: "Stopped", 0x01: "Recording", 0x02: "Unable", -1: "Error"}
    log.info("  Initial movie status: 0x%02X (%s)",
             prev_status & 0xFF, status_names.get(prev_status, "?"))

    for elapsed in range(timeout):
        time.sleep(1.0)
        status = get_movie_status(camera)

        # Detect status changes
        if status != prev_status and prev_status >= 0 and status >= 0:
            log.info("  Movie status changed: 0x%02X → 0x%02X at %ds",
                     prev_status, status, elapsed + 1)

        # After at least 10 seconds, check for completion indicators
        if elapsed >= 10 and status in (MOVIE_STOPPED, MOVIE_UNABLE):
            # If status changed to a terminal state, we're done
            if status != prev_status or elapsed >= 60:
                log.info("Processing complete (%ds)", elapsed + 1)
                return True

        prev_status = status

        if elapsed % 15 == 14:
            log.info("  Still processing... %ds, status=0x%02X (%s)",
                     elapsed + 1, status & 0xFF, status_names.get(status, "?"))

    # For long timeouts, the processing has almost certainly finished
    if timeout >= 90:
        log.info("Timeout reached (%ds) — assuming processing complete", timeout)
        return True

    log.warning("Processing timeout (%ds). Last status: 0x%02X", timeout, prev_status)
    return False


# ---------------------------------------------------------------------------
# Contents Transfer Mode — download MP4
# ---------------------------------------------------------------------------
# The v3 protocol requires SDIO_OpenSession (0x9210) with FunctionMode=1
# ("Content Transfer Mode") to enable access to the camera's SD card.
#
# Standard PTP OpenSession (0x1002) connects in Remote Control Mode, which
# does NOT support SDIOSetContentsTransferMode (0x9212) — the camera will
# stall the endpoint with LIBUSB_ERROR_PIPE (-9).
#
# The v3 spec (page 0055) states: "Switching between 'Remote Control Mode'
# and 'Content Transfer Mode' cannot be performed while connected."
#
# Therefore, we must:
#   1. Close the current session
#   2. Re-open with SDIO_OpenSession(FunctionMode=1)
#   3. Authenticate
#   4. SDIOSetContentsTransferMode(On) — with send() (spec: Data=None)
#   5. Browse and download via standard PTP GetObjectHandles + GetObject
#   6. SDIOSetContentsTransferMode(Off)
#   7. Close session, re-open with standard OpenSession
#   8. Re-authenticate to return to Remote Control Mode
# ---------------------------------------------------------------------------

def reconnect_for_transfer(camera: SonyCamera) -> bool:
    """Close the Remote Control session and reconnect in Content Transfer Mode.

    Returns True on success, False on failure.
    """
    # Close current session
    try:
        camera._close_session()
    except Exception:
        pass
    time.sleep(0.5)

    # Open SDIO session in Content Transfer Mode
    try:
        camera.sdio_open_session(session_id=1, function_mode=1)
    except Exception as e:
        log.warning("SDIO_OpenSession(CT) failed: %s — trying USB reconnect", e)
        try:
            camera._transport.clear_halt()
            camera._transport.reset_device()
            time.sleep(2.0)
            camera._transport.disconnect()
            time.sleep(1.0)
            camera._transport.connect()
            camera.sdio_open_session(session_id=1, function_mode=1)
        except Exception as e2:
            log.error("SDIO_OpenSession failed after reset: %s", e2)
            # Fallback: reconnect in control mode so the session isn't broken
            try:
                camera._open_session()
                camera.authenticate()
            except Exception:
                pass
            return False

    # Authenticate in Content Transfer Mode
    try:
        camera.authenticate()
    except Exception as e:
        log.error("Authentication in Content Transfer Mode failed: %s", e)
        return False

    # Enable content transfer (spec: Data=None, use send not receive)
    try:
        resp = camera._transport.send(
            SDIOOpCode.SET_CONTENTS_TRANSFER_MODE,
            [0x00000002, 0x00000001, 0x00000000],
        )
        log.info("SetContentsTransferMode(On) resp=0x%04X", resp.code)
    except Exception as e:
        log.error("SetContentsTransferMode failed: %s", e)
        return False

    # Wait for camera to expose storage (camera fires StoreAdded event)
    time.sleep(2.0)
    return True


def reconnect_for_control(camera: SonyCamera) -> bool:
    """Close the Content Transfer session and reconnect in Remote Control Mode.

    Returns True on success, False on failure.
    """
    # Turn off content transfer
    try:
        camera._transport.send(
            SDIOOpCode.SET_CONTENTS_TRANSFER_MODE,
            [0x00000002, 0x00000000, 0x00000000],
        )
    except Exception:
        pass
    time.sleep(1.0)

    # Close SDIO session
    try:
        camera._close_session()
    except Exception:
        pass
    time.sleep(0.5)

    # Reopen with standard PTP OpenSession (Remote Control Mode)
    try:
        camera._open_session()
    except Exception as e:
        log.warning("Standard OpenSession failed: %s — trying USB reconnect", e)
        try:
            camera._transport.clear_halt()
            camera._transport.reset_device()
            time.sleep(2.0)
            camera._transport.disconnect()
            time.sleep(1.0)
            camera._transport.connect()
            camera._open_session()
        except Exception as e2:
            log.error("OpenSession failed after reset: %s", e2)
            return False

    # Re-authenticate
    try:
        camera.authenticate()
    except Exception as e:
        log.error("Re-authentication failed: %s", e)
        return False

    log.info("Reconnected in Remote Control Mode")
    return True


def download_latest_mp4(camera: SonyCamera, output_dir: Path) -> str | None:
    """Download the most recent MP4 from the camera's SD card.

    Handles the full lifecycle:
      reconnect(transfer) → browse → download → reconnect(control)

    Returns the saved file path, or None on failure.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    original_timeout = camera._transport._timeout_ms
    camera._transport._timeout_ms = 60_000  # 60s for large video

    try:
        if not reconnect_for_transfer(camera):
            log.error("Could not enter Content Transfer Mode")
            return None

        # Get storage IDs
        storage_ids = camera._get_storage_ids()
        if not storage_ids:
            log.warning("No storage IDs found — trying default 0x00010001")
            storage_ids = [STORAGE_ID]

        log.info("Storage IDs: %s", [f"0x{s:08X}" for s in storage_ids])

        saved_path = None
        for sid in storage_ids:
            # Get folder handles
            folders = camera._get_object_handles(sid, FORMAT_FOLDER, 0xFFFFFFFF)
            if not folders:
                log.debug("No folders on storage 0x%08X", sid)
                continue

            # Find MP4 files across all folders
            all_mp4s: list[int] = []
            for fh in folders:
                time.sleep(0.2)
                handles = camera._get_object_handles(sid, FORMAT_MP4, fh)
                all_mp4s.extend(handles)

            if not all_mp4s:
                # Also try without format filter
                handles = camera._get_object_handles(sid, 0, 0xFFFFFFFF)
                for h in handles:
                    try:
                        info_data = camera.get_object_info(h)
                        info = parse_object_info(info_data)
                        if info.get("filename", "").lower().endswith(".mp4"):
                            all_mp4s.append(h)
                    except Exception:
                        continue

            if not all_mp4s:
                log.debug("No MP4 files on storage 0x%08X", sid)
                continue

            log.info("Found %d MP4 file(s) on storage 0x%08X", len(all_mp4s), sid)

            # Get info on newest file (last handle)
            latest = all_mp4s[-1]
            info_data = camera.get_object_info(latest)
            info = parse_object_info(info_data)
            filename = info.get("filename") or f"HFR_{latest:08X}.mp4"
            file_size = info.get("size", 0)

            if file_size == 0:
                log.warning("File %s reports 0 bytes", filename)
                continue

            log.info("Downloading %s (%.1f MB)...", filename, file_size / (1024 * 1024))

            data = camera.get_object(latest)
            out_path = output_dir / filename
            out_path.write_bytes(data)
            log.info("Saved %s (%d bytes)", out_path, len(data))
            saved_path = str(out_path)
            break

        return saved_path

    finally:
        camera._transport._timeout_ms = original_timeout
        # Always reconnect back to Remote Control Mode
        reconnect_for_control(camera)


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


def restore_hfr_mode(camera: SonyCamera, hfr_mode: int) -> None:
    """Restore Movie Rec mode and HFR exposure after a transfer cycle."""
    try:
        camera.set_mode("movie")
    except Exception as e:
        log.warning("Could not restore Movie mode: %s", e)
    time.sleep(0.5)
    try:
        camera.set_exposure_mode(hfr_mode)
    except Exception as e:
        log.warning("Could not restore HFR exposure: %s", e)
    time.sleep(0.5)


# ---------------------------------------------------------------------------
# Main loops
# ---------------------------------------------------------------------------

def unattended_loop(
    camera: SonyCamera,
    output_dir: Path,
    auto_trigger_delay: int,
    max_clips: int,
    hfr_mode: int = ExposureMode.HFR_P,
) -> None:
    """Fully unattended HFR capture loop.

    1. Enter STBY
    2. Wait auto_trigger_delay seconds, then trigger
    3. Wait for processing
    4. Download clip (reconnects session for transfer, then back to control)
    5. Restore HFR mode and re-enter STBY
    6. Repeat
    """
    clip_num = 0

    while max_clips == 0 or clip_num < max_clips:
        clip_num += 1
        print(f"\n{'='*50}")
        print(f"  Clip {clip_num}" + (f" / {max_clips}" if max_clips else ""))
        print(f"{'='*50}")

        # Step 1: Enter HFR STBY
        print("\n[1/6] Entering HFR STBY (buffering)...")
        if not enter_hfr_standby(camera):
            print("[ERROR] Could not enter STBY. Retrying in 5s...")
            time.sleep(5.0)
            continue

        # Give camera time to start buffering
        time.sleep(2.0)
        print("[OK] Camera should now be in STBY (buffering at high fps)")

        # Step 2: Wait before trigger
        if auto_trigger_delay > 0:
            print(f"\n[2/6] Waiting {auto_trigger_delay}s before trigger...")
            for remaining in range(auto_trigger_delay, 0, -1):
                time.sleep(1.0)
                if remaining % 10 == 0 and remaining != auto_trigger_delay:
                    print(f"       {remaining}s remaining...")
        else:
            print("\n[2/6] Triggering immediately...")

        # Step 3: Trigger recording
        print("\n[3/6] Triggering HFR recording...")
        if not trigger_recording(camera):
            print("[ERROR] Trigger failed. Canceling and retrying...")
            cancel_hfr_recording(camera)
            time.sleep(3.0)
            continue

        # Step 4: Wait for processing
        print("\n[4/6] Waiting for HFR processing...")
        wait_for_processing(camera, timeout=120)

        # Allow camera to fully settle after processing
        time.sleep(5.0)

        # Step 5: Download the clip (reconnects session)
        print("\n[5/6] Downloading clip...")
        saved = download_latest_mp4(camera, output_dir)
        if saved:
            print(f"[OK] Saved: {saved}")
        else:
            print("[WARN] Download failed or no file found.")
            print("       Clip may still be on camera SD card.")

        # Step 6: Restore HFR mode and prepare for next cycle
        print("\n[6/6] Restoring HFR mode for next recording...")
        restore_hfr_mode(camera, hfr_mode)
        time.sleep(2.0)

    print(f"\nCompleted {clip_num} clip(s).")


def interactive_loop(
    camera: SonyCamera, output_dir: Path, hfr_mode: int = ExposureMode.HFR_P
) -> None:
    """Interactive keyboard-driven HFR control."""
    print("Controls:")
    print("  ENTER   Enter / re-enter HFR STBY")
    print("  R       Trigger recording (must be in STBY)")
    print("  D       Download latest clip")
    print("  S       Show camera status")
    print("  Q       Quit")
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
            # ENTER = enter STBY
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
            wait_for_processing(camera, timeout=120)
            time.sleep(5.0)
            print("Downloading...")
            saved = download_latest_mp4(camera, output_dir)
            if saved:
                print(f"[OK] Saved: {saved}")
                restore_hfr_mode(camera, hfr_mode)
                print("[OK] HFR mode restored. Press ENTER to re-enter STBY.")
            else:
                print("[WARN] Download failed. Use D to retry.")
                restore_hfr_mode(camera, hfr_mode)

        elif cmd == "D":
            print("Downloading latest MP4...")
            try:
                saved = download_latest_mp4(camera, output_dir)
                if saved:
                    print(f"[OK] Saved: {saved}")
                else:
                    print("[WARN] No MP4 found.")
            except Exception as e:
                print(f"[ERROR] Download failed: {e}")
            restore_hfr_mode(camera, hfr_mode)

        elif cmd == "S":
            print("Status:")
            print_status(camera)

        elif cmd == "C":
            # Hidden: cancel current recording
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
    p.add_argument("--output", default="hfr_output",
                    help="Output directory (default: hfr_output/)")
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
    output_dir = Path(args.output)

    print(f"HFR Slow Motion — mode: HFR ({args.mode})")
    print("=" * 50)
    print()
    print("Camera requirements:")
    print("  - Dial set to HFR / Movie position")
    print("  - Frame rate configured (240/480/960/1000 fps)")
    print("  - Trigger timing set (Start/End/End Half)")
    print()

    with SonyCamera() as camera:
        setup_camera(camera, hfr_mode)

        if args.interactive:
            interactive_loop(camera, output_dir, hfr_mode)
        else:
            print(f"Auto-trigger delay: {args.auto_trigger}s")
            print(f"Max clips: {'unlimited' if args.loop == 0 else args.loop}")
            print(f"Output: {output_dir}/")
            print()
            print("Starting unattended loop (Ctrl-C to stop)...")
            try:
                unattended_loop(
                    camera, output_dir, args.auto_trigger, args.loop, hfr_mode
                )
            except KeyboardInterrupt:
                print("\n\nStopped by user.")

    print("Done.")


if __name__ == "__main__":
    main()

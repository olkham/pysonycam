"""
S&Q (Slow & Quick) motion capture with event confirmation.

Configures the camera for Slow & Quick movie mode, starts and stops recording
via :meth:`~pysonycam.SonyCamera.toggle_movie`, waits for the
``MOVIE_REC_OPERATION_RESULTS`` event confirming the clip was written to card,
then verifies the new clip appears in the content list.

Demonstrates:
  - :meth:`~pysonycam.SonyCamera.set_sq_mode`
  - :meth:`~pysonycam.SonyCamera.set_sq_frame_rate`
  - :meth:`~pysonycam.SonyCamera.set_sq_record_setting`
  - :meth:`~pysonycam.SonyCamera.toggle_movie`
  - :meth:`~pysonycam.SonyCamera.on_event` / :meth:`start_event_listener` / :meth:`stop_event_listener`
  - :meth:`~pysonycam.SonyCamera.get_content_info_list`

Usage
-----
    python examples/sq_mode_capture.py [options]

    Options:
        --duration SEC     Duration of the S&Q clip in seconds (default: 5)
        --frame-rate CODE  S&Q frame rate code in hex (default: 0x0001)
                           Common codes: 0x0001 = 1 fps (max slow-mo),
                           0x0800 = 120 fps, 0x1E00 = 30 fps (real-time)
        --record-setting N S&Q record setting code (default: 0)
                           0 = leave as currently configured on camera
        --sq-mode N        S&Q mode enable value (default: 0x0001 = enabled)
        --timeout SEC      Max seconds to wait for the rec-result event (default: 30)
        --verify           List the camera card after capture to confirm the new clip
"""

from __future__ import annotations

import argparse
import threading
import time
import logging

from pysonycam import SonyCamera
from pysonycam.constants import SDIOEventCode
from pysonycam.exceptions import SonyCameraError
from pysonycam.ptp import PTPEvent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# S&Q mode enable value
SQ_MODE_ENABLED  = 0x0001
SQ_MODE_DISABLED = 0x0000


def _rec_result_handler(
    event: PTPEvent,
    result_holder: list,
    done_event: threading.Event,
) -> None:
    """Callback for MOVIE_REC_OPERATION_RESULTS."""
    code = event.params[0] if event.params else 0
    result_holder.append(code)
    log.info(
        "MOVIE_REC_OPERATION_RESULTS received  (code=0x%04X — %s)",
        code,
        "OK (clip saved)" if code == 0 else "non-zero result",
    )
    done_event.set()


def record_sq_clip(
    camera: SonyCamera,
    *,
    duration_sec: float,
    frame_rate_code: int,
    record_setting: int,
    sq_mode: int,
    timeout_sec: float,
) -> bool:
    """Configure S&Q mode, record a clip, and wait for confirmation."""

    # ------------------------------------------------------------------
    # Step 1 — Configure S&Q parameters
    # ------------------------------------------------------------------
    log.info("Enabling S&Q mode (value=0x%04X)…", sq_mode)
    camera.set_sq_mode(sq_mode)
    time.sleep(0.3)

    log.info("Setting S&Q frame rate code: 0x%04X", frame_rate_code)
    camera.set_sq_frame_rate(frame_rate_code)
    time.sleep(0.3)

    if record_setting != 0:
        log.info("Setting S&Q record setting: 0x%08X", record_setting)
        camera.set_sq_record_setting(record_setting)
        time.sleep(0.3)

    # ------------------------------------------------------------------
    # Step 2 — Register result event callback
    # ------------------------------------------------------------------
    result_holder: list[int] = []
    done_event = threading.Event()

    camera.on_event(
        SDIOEventCode.MOVIE_REC_OPERATION_RESULTS,
        lambda ev: _rec_result_handler(ev, result_holder, done_event),
    )
    camera.start_event_listener()

    try:
        # ------------------------------------------------------------------
        # Step 3 — Start recording
        # ------------------------------------------------------------------
        log.info("Starting S&Q recording (toggle_movie)…")
        camera.toggle_movie()

        # ------------------------------------------------------------------
        # Step 4 — Record for the requested duration
        # ------------------------------------------------------------------
        log.info("Recording for %.1f second(s)…", duration_sec)
        time.sleep(duration_sec)

        # ------------------------------------------------------------------
        # Step 5 — Stop recording
        # ------------------------------------------------------------------
        log.info("Stopping recording (toggle_movie)…")
        camera.toggle_movie()

        # ------------------------------------------------------------------
        # Step 6 — Wait for the camera to confirm the clip was written
        # ------------------------------------------------------------------
        log.info("Waiting up to %.0f s for MOVIE_REC_OPERATION_RESULTS…", timeout_sec)
        if not done_event.wait(timeout=timeout_sec):
            log.warning("Timed out waiting for recording result event.")
            return False

        result_code = result_holder[0]
        if result_code != 0:
            log.error("Recording result indicates failure (code=0x%04X).", result_code)
            return False

        log.info("Clip successfully written to camera card.")
        return True

    except (SonyCameraError, KeyboardInterrupt) as exc:
        log.warning("Recording interrupted: %s", exc)
        try:
            camera.toggle_movie()   # attempt to stop a in-progress recording
        except SonyCameraError:
            pass
        return False
    finally:
        camera.stop_event_listener()


def verify_new_clip(camera: SonyCamera, before_count: int) -> None:
    """Fetch the content list and report any new items since before_count."""
    log.info("Fetching content list to verify new clip…")
    try:
        items = camera.get_content_info_list()
    except SonyCameraError as exc:
        log.error("Could not fetch content list: %s", exc)
        return

    if len(items) > before_count:
        new_items = items[before_count:]
        print(f"\n{len(new_items)} new item(s) on card:")
        for item in new_items:
            size_mb = item.get("size", 0) / 1_048_576
            print(
                f"  {item.get('file_name', '?'):30s}  "
                f"{size_mb:7.2f} MB  "
                f"{item.get('date_time', '')}"
            )
    else:
        print("\nNo new items detected on card (content list unchanged).")


def main() -> None:
    parser = argparse.ArgumentParser(description="S&Q mode capture with event confirmation")
    parser.add_argument("--duration", type=float, default=5.0, metavar="SEC",
                        help="Clip duration in seconds (default: 5)")
    parser.add_argument("--frame-rate", type=lambda x: int(x, 0), default=0x0001,
                        metavar="CODE", help="S&Q frame rate code (default: 0x0001 = 1 fps)")
    parser.add_argument("--record-setting", type=lambda x: int(x, 0), default=0,
                        metavar="N", help="S&Q record setting code (0 = leave as-is)")
    parser.add_argument("--sq-mode", type=lambda x: int(x, 0), default=SQ_MODE_ENABLED,
                        metavar="N", help="S&Q mode enable code (default: 0x0001)")
    parser.add_argument("--timeout", type=float, default=30.0, metavar="SEC",
                        help="Seconds to wait for the recording result event")
    parser.add_argument("--verify", action="store_true",
                        help="List card content after capture to confirm new clip")
    args = parser.parse_args()

    with SonyCamera() as camera:
        camera.authenticate()
        print("Connected and authenticated.")

        # Snapshot content count before recording for the verification step
        before_count = 0
        if args.verify:
            try:
                before_count = len(camera.get_content_info_list())
                log.info("Content count before recording: %d", before_count)
            except SonyCameraError:
                pass

        success = record_sq_clip(
            camera,
            duration_sec=args.duration,
            frame_rate_code=args.frame_rate,
            record_setting=args.record_setting,
            sq_mode=args.sq_mode,
            timeout_sec=args.timeout,
        )

        if success:
            print("\nS&Q clip recorded successfully.")
            if args.verify:
                verify_new_clip(camera, before_count)
        else:
            print("\nS&Q recording was not completed successfully (see log for details).")

        # Restore normal movie mode
        try:
            log.info("Restoring S&Q mode to disabled…")
            camera.set_sq_mode(SQ_MODE_DISABLED)
        except SonyCameraError as exc:
            log.warning("Could not restore S&Q mode: %s", exc)


if __name__ == "__main__":
    main()

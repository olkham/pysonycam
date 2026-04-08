"""
Custom white balance capture sequence with event confirmation.

Walks through the full Sony custom WB workflow:
  1. Optionally configure a preset colour temperature baseline
  2. Enter custom WB standby mode
  3. Shoot the target (white card) and execute the measurement
  4. Wait for the CWB_CAPTURED_RESULT event confirming the result
  5. Optionally fine-tune R-gain and B-gain offsets
  6. Cancel gracefully if interrupted

Demonstrates:
  - :meth:`~pysonycam.SonyCamera.custom_wb_standby`
  - :meth:`~pysonycam.SonyCamera.custom_wb_execute`
  - :meth:`~pysonycam.SonyCamera.custom_wb_cancel`
  - :meth:`~pysonycam.SonyCamera.set_wb_preset_color_temp`
  - :meth:`~pysonycam.SonyCamera.set_wb_r_gain`
  - :meth:`~pysonycam.SonyCamera.set_wb_b_gain`
  - :meth:`~pysonycam.SonyCamera.on_event` / :meth:`start_event_listener` / :meth:`stop_event_listener`

Usage
-----
    python examples/custom_white_balance.py [options]

    Options:
        --temp K           Preset colour temperature in Kelvin (e.g. 5500)
                           Set to 0 to skip the preset step (default: 0)
        --r-gain N         R-gain offset to apply after capture (default: 0)
        --b-gain N         B-gain offset to apply after capture (default: 0)
        --timeout SEC      Seconds to wait for the CWB result event (default: 15)
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


def _cwb_result_handler(
    event: PTPEvent,
    result_holder: list,
    done_event: threading.Event,
) -> None:
    """Callback invoked when the camera sends CWB_CAPTURED_RESULT."""
    result_code = event.params[0] if event.params else 0
    result_holder.append(result_code)
    log.info(
        "CWB_CAPTURED_RESULT received  (code=0x%04X — %s)",
        result_code,
        "success" if result_code == 0 else "failure/cancelled",
    )
    done_event.set()


def run_custom_wb(
    camera: SonyCamera,
    *,
    preset_temp: int = 0,
    r_gain: int = 0,
    b_gain: int = 0,
    timeout_sec: float = 15.0,
) -> bool:
    """Execute the custom WB sequence.  Returns True on success."""

    # ------------------------------------------------------------------
    # Step 1 — Optionally set a preset colour temperature as a starting point
    # ------------------------------------------------------------------
    if preset_temp > 0:
        log.info("Setting WB preset colour temperature to %d K…", preset_temp)
        camera.set_wb_preset_color_temp(preset_temp)
        time.sleep(0.3)

    # ------------------------------------------------------------------
    # Step 2 — Register the result event callback (before entering standby)
    # ------------------------------------------------------------------
    result_holder: list[int] = []
    done_event = threading.Event()

    camera.on_event(
        SDIOEventCode.CWB_CAPTURED_RESULT,
        lambda ev: _cwb_result_handler(ev, result_holder, done_event),
    )
    camera.start_event_listener()

    try:
        # ------------------------------------------------------------------
        # Step 3 — Enter custom WB standby (camera awaits the measurement shot)
        # ------------------------------------------------------------------
        log.info("Entering custom WB standby mode…")
        log.info("Point the camera at a neutral white/grey target and press the shutter.")
        camera.custom_wb_standby()

        # ------------------------------------------------------------------
        # Step 4 — Execute the measurement shot
        # ------------------------------------------------------------------
        # In a real workflow the user presses the physical shutter.
        # Here we trigger the execute command immediately; on the camera body
        # the operator should have the white card framed before this runs.
        log.info("Executing custom WB measurement…")
        camera.custom_wb_execute()

        # ------------------------------------------------------------------
        # Step 5 — Wait for CWB_CAPTURED_RESULT event from the camera
        # ------------------------------------------------------------------
        log.info("Waiting up to %.0f s for CWB result event…", timeout_sec)
        if not done_event.wait(timeout=timeout_sec):
            log.warning("Timed out waiting for CWB_CAPTURED_RESULT. Cancelling.")
            camera.custom_wb_cancel()
            return False

        result_code = result_holder[0]
        if result_code != 0:
            log.error("Custom WB measurement failed (result code 0x%04X).", result_code)
            return False

        log.info("Custom WB measurement accepted by camera.")

        # ------------------------------------------------------------------
        # Step 6 — Apply optional gain offsets
        # ------------------------------------------------------------------
        if r_gain != 0:
            log.info("Applying R-gain offset: %d", r_gain)
            camera.set_wb_r_gain(r_gain)
            time.sleep(0.2)
        if b_gain != 0:
            log.info("Applying B-gain offset: %d", b_gain)
            camera.set_wb_b_gain(b_gain)
            time.sleep(0.2)

        return True

    except (SonyCameraError, KeyboardInterrupt) as exc:
        log.warning("Custom WB aborted: %s. Sending cancel…", exc)
        try:
            camera.custom_wb_cancel()
        except SonyCameraError:
            pass
        return False
    finally:
        camera.stop_event_listener()


def main() -> None:
    parser = argparse.ArgumentParser(description="Custom white balance capture")
    parser.add_argument("--temp", type=int, default=0, metavar="K",
                        help="Preset colour temperature in Kelvin (0 = skip)")
    parser.add_argument("--r-gain", type=int, default=0, metavar="N",
                        help="R-gain offset after capture")
    parser.add_argument("--b-gain", type=int, default=0, metavar="N",
                        help="B-gain offset after capture")
    parser.add_argument("--timeout", type=float, default=15.0, metavar="SEC",
                        help="Seconds to wait for the CWB result event")
    args = parser.parse_args()

    with SonyCamera() as camera:
        camera.authenticate()
        print("Connected and authenticated.")

        success = run_custom_wb(
            camera,
            preset_temp=args.temp,
            r_gain=args.r_gain,
            b_gain=args.b_gain,
            timeout_sec=args.timeout,
        )

        if success:
            print("\nCustom white balance applied successfully.")
        else:
            print("\nCustom white balance was not applied (see log for details).")


if __name__ == "__main__":
    main()

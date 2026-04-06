"""
Interactive shutter: hold S1 for AF+AE, press SPACE to fire each shot.

The camera half-presses (S1) once when the script starts, locking autofocus
and auto-exposure.  It then waits in a loop for you to press SPACE to take
a shot.  After each shot the image is downloaded automatically.

Press 'q' or Ctrl-C to release S1 and exit.

Usage
-----
    python examples/interactive_shutter.py [output_dir]

    output_dir  Directory to save images (default: interactive_output/)
"""

import sys
import time
import logging
import msvcrt
from pathlib import Path

from sony_camera_control import SonyCamera
from sony_camera_control.constants import (
    DeviceProperty,
    SaveMedia,
    SHOT_OBJECT_HANDLE,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)


def wait_for_key() -> str:
    """Block until a key is pressed and return it (Windows)."""
    while True:
        if msvcrt.kbhit():
            ch = msvcrt.getwch()
            return ch
        time.sleep(0.01)


def main() -> None:
    output_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("interactive_output")
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Interactive shutter — images will be saved to", output_dir)
    print()

    with SonyCamera() as camera:
        camera.authenticate()
        print("Authenticated.")

        camera.set_mode("still")
        camera.set_save_media(SaveMedia.HOST)
        print("Camera ready.\n")

        # Wait for LiveView so the camera is fully active.
        camera._wait_for_liveview()
        camera._wait_for_shooting_file_info_clear(timeout=10.0)

        # Hold S1 — half-press locks AF + AE.
        camera.control_device(DeviceProperty.S1_BUTTON, 0x0002)
        print("S1 held (AF + AE locking)…")

        # Wait for AF to lock (up to 3 s), then proceed either way.
        deadline = time.monotonic() + 3.0
        af_locked = False
        while time.monotonic() < deadline:
            try:
                af = camera.get_property(DeviceProperty.AF_LOCK_INDICATION)
                if af.current_value:
                    af_locked = True
                    break
            except Exception:
                pass
            time.sleep(0.05)

        if af_locked:
            print("AF locked ✓")
        else:
            print("AF did not confirm lock — proceeding anyway (may be in MF mode)")

        print()
        print("Press SPACE to take a shot, 'q' to quit.")
        print("-" * 45)

        shot_num = 0
        try:
            while True:
                key = wait_for_key()

                if key in ("q", "Q"):
                    print("\nQuitting…")
                    break

                if key != " ":
                    continue

                shot_num += 1
                print(f"\n  Firing shot {shot_num}…", end="", flush=True)

                # Pulse S2 (shutter) — S1 is already held.
                camera.control_device(DeviceProperty.S2_BUTTON, 0x0002)
                time.sleep(0.2)
                camera.control_device(DeviceProperty.S2_BUTTON, 0x0001)

                # Wait for image to be ready.
                t0 = time.monotonic()
                timeout = 30.0
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    info = camera.get_property(DeviceProperty.SHOOTING_FILE_INFO)
                    val = info.current_value if isinstance(info.current_value, int) else 0
                    if val & 0x8000:
                        break
                    time.sleep(0.05)
                else:
                    print(" TIMEOUT — no image received")
                    continue

                # Download.
                camera.get_object_info(SHOT_OBJECT_HANDLE)
                data = camera.get_object(SHOT_OBJECT_HANDLE)
                elapsed = time.monotonic() - t0

                fname = output_dir / f"shot_{shot_num:04d}.jpg"
                fname.write_bytes(data)
                print(f" done  {len(data):,} bytes  ({elapsed:.1f}s)  → {fname}")

                # Wait for the camera to clear the flag before next shot.
                camera._wait_for_shooting_file_info_clear(timeout=10.0)

        except KeyboardInterrupt:
            print("\nInterrupted.")
        finally:
            # Always release S1.
            camera.control_device(DeviceProperty.S1_BUTTON, 0x0001)
            print("S1 released.")

    print(f"Done — {shot_num} image(s) saved to {output_dir}/")


if __name__ == "__main__":
    main()

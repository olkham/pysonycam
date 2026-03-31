"""
Continuous burst: shoot at the camera's native burst fps, then download.

This example sets the camera to a continuous-shooting drive mode, holds the
shutter (S2) for a specified duration, and lets the camera fire at its full
hardware burst rate.  After releasing the shutter, all queued images are
downloaded from the camera's internal transfer buffer.

This is fundamentally different from the other capture examples:
  - burst_capture / rapid_fire: pulse S2 per shot, download between shots
  - continuous_burst (this): hold S2, camera fires at native fps, download
    everything at the end

Typical results:  hold_seconds=2.0 on a camera that does 10 fps → ~20 shots,
all downloaded after the burst completes.

Prerequisites
-------------
Set the camera's Drive Mode dial to a continuous shooting mode BEFORE running,
or let the script set it via set_drive_mode().  Not all cameras allow remote
drive-mode changes — if yours doesn't, set it on the camera body first.

Usage
-----
    python examples/continuous_burst.py [hold_seconds] [output_dir]

    hold_seconds  How long to hold the shutter (default: 2.0)
    output_dir    Directory to save images (default: continuous_output/)
"""

import sys
import time
import logging
from pathlib import Path

from sony_camera_control import SonyCamera, DriveMode

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)


def main() -> None:
    hold = float(sys.argv[1]) if len(sys.argv) > 1 else 2.0
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("continuous_output")

    print(f"Continuous burst: hold shutter for {hold}s → {output_dir}/\n")

    with SonyCamera() as camera:
        camera.authenticate()
        print("Authenticated.")

        camera.set_mode("still")
        print("Camera in still mode.")

        # Set drive mode to continuous shooting.
        # If this fails on your camera, set it manually on the body.
        try:
            camera.set_drive_mode(DriveMode.CONTINUOUS_HI)
            print("Drive mode → Continuous Hi")
        except Exception as e:
            print(f"Could not set drive mode remotely ({e}).")
            print("Make sure the camera dial is set to continuous shooting.\n")

        print(f"\nHolding shutter for {hold}s — camera will burst…\n")

        t0 = time.monotonic()
        images = camera.continuous_burst(
            hold_seconds=hold,
            output_dir=output_dir,
        )
        elapsed = time.monotonic() - t0

    n = len(images)
    print(f"\nDone — {n} image(s) in {elapsed:.1f}s")
    if n:
        burst_time = hold
        print(f"  Burst rate:     ~{n / burst_time:.1f} fps (during {burst_time}s hold)")
        print(f"  Total inc. DL:  {elapsed:.1f}s  ({elapsed / n:.1f}s avg per image)")
    for i, data in enumerate(images):
        path = output_dir / f"cont_{i:04d}.jpg"
        print(f"  {path}  ({len(data):,} bytes)")


if __name__ == "__main__":
    main()

"""
Rapid-fire capture: shoot N frames with a full shutter cycle per shot.

Unlike burst_capture (which holds S1 half-pressed for the whole run and only
pulses S2), this example performs a complete S1→S2→release cycle for every
frame.  This prevents a common issue where the camera "hangs" after the first
image because it never saw S1 released.

Delays are kept to the minimum that the Sony SDIO protocol reliably handles
(200 ms S2 hold, 300 ms AF settle, matching the C++ SDK reference app).

Usage
-----
    python examples/rapid_fire.py [count] [output_dir]

    count       Number of shots (default: 5)
    output_dir  Directory to save images (default: rapid_output/)
"""

import sys
import time
import logging
from pathlib import Path

from sony_camera_control import SonyCamera

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)


def main() -> None:
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("rapid_output")

    print(f"Rapid-fire: {count} shots → {output_dir}/\n")

    with SonyCamera() as camera:
        camera.authenticate()
        print("Authenticated.")

        camera.set_mode("still")
        print("Camera ready.\n")

        t0 = time.monotonic()
        images = camera.rapid_fire(count=count, output_dir=output_dir)
        elapsed = time.monotonic() - t0

    print(f"\nDone — {len(images)} image(s) in {elapsed:.1f}s "
          f"({elapsed / len(images):.1f}s per shot)")
    for i, data in enumerate(images):
        path = output_dir / f"rapid_{i:04d}.jpg"
        print(f"  {path}  ({len(data):,} bytes)")


if __name__ == "__main__":
    main()

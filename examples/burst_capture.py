"""
Burst capture demo: shoot N frames as fast as possible, then download.

Sony's SDIO host-control protocol delivers one image at a time via a fixed
handle, so this script fires each shot, waits for the camera to signal the
image is ready, downloads it immediately, then fires the next shot.  LiveView
is checked only once and all shutter delays are kept to 100 ms.

Typical cycle time: ~2–4 s per shot (AF + shutter + USB transfer of ~8 MB).

Usage
-----
    python examples/burst_capture.py [count] [output_dir]

    count       Number of shots (default: 5)
    output_dir  Directory to save images (default: burst_output/)
"""

import sys
import logging
from pathlib import Path

from pysonycam import SonyCamera

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)


def main() -> None:
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("burst_output")

    print(f"Burst capture: {count} shots → {output_dir}/")

    with SonyCamera() as camera:
        camera.authenticate()
        print("Authenticated.")

        camera.set_mode("still")
        print("Camera ready.\n")

        images = camera.burst_capture(count=count, output_dir=output_dir)

    print(f"\nDone — {len(images)} image(s) saved to {output_dir}/")
    for i, data in enumerate(images):
        path = output_dir / f"burst_{i:04d}.jpg"
        print(f"  {path}  ({len(data):,} bytes)")


if __name__ == "__main__":
    main()

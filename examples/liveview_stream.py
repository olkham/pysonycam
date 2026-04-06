"""
LiveView streaming example: capture JPEG frames from the camera's
live preview and save them to disk.

This can be used for:
  - Real-time monitoring
  - Time-lapse frame capture
  - Building a viewfinder application
"""

import sys
import logging
from pathlib import Path

from pysonycam import SonyCamera

logging.basicConfig(level=logging.INFO)


def main():
    num_frames = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("liveview_frames")
    output_dir.mkdir(parents=True, exist_ok=True)

    with SonyCamera() as camera:
        camera.authenticate()
        print("Authenticated.")

        # Switch to Still Rec mode (LiveView starts automatically)
        camera.set_mode("still")
        print("Camera in Still Rec mode. Streaming LiveView...\n")

        # Stream frames from the camera's live preview
        for i, frame in enumerate(camera.liveview_stream(count=num_frames)):
            path = output_dir / f"frame_{i:04d}.jpg"
            path.write_bytes(frame)
            print(f"  Frame {i + 1}/{num_frames}: {path.name} ({len(frame):,} bytes)")

        print(f"\nDone! {num_frames} frames saved to {output_dir}/")


if __name__ == "__main__":
    main()

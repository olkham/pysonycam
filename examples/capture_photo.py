"""
Capture a still photo and save it to disk.

This example demonstrates the full capture workflow:
  1. Connect and authenticate
  2. Switch to Still Rec mode
  3. Configure save destination
  4. Take a photo
  5. Download and save the image
"""

import sys
import logging
from pathlib import Path

from sony_camera_control import SonyCamera, ExposureMode
from sony_camera_control.constants import SaveMedia

logging.basicConfig(level=logging.INFO)


def main():
    output = sys.argv[1] if len(sys.argv) > 1 else "captured_photo.jpg"

    with SonyCamera() as camera:
        camera.authenticate()
        print("Authenticated.")

        # Switch to Still Rec mode
        camera.set_mode("still")
        print("Camera set to Still Rec mode.")

        # Set save media to host (image will be transferred over USB)
        camera.set_save_media(SaveMedia.HOST)
        print("Save media set to Host.")

        # Optionally change exposure settings
        # camera.set_exposure_mode(ExposureMode.APERTURE_PRIORITY)
        # camera.set_iso(400)
        # camera.set_aperture(0x0118)  # F2.8

        # Capture the image (waits for LiveView, presses shutter, downloads)
        print("Capturing photo...")
        for n in range(0, 5):
            output = Path(f"captured_photo_fast_{n:02d}.jpg")
            image_data = camera.capture(output, fast_mode=True)
            print(f"Photo saved to {output} ({len(image_data):,} bytes)")


if __name__ == "__main__":
    main()

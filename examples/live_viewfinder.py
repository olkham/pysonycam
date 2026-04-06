"""
Live viewfinder with capture controls.

Displays the camera's LiveView feed in an OpenCV window.
Keyboard controls:
    1  — take a single photo (displayed in a pop-up window)
    2  — 9-shot burst (Continuous Mid), displayed as a 3×3 grid
    q  — quit

Usage
-----
    python examples/live_viewfinder.py [output_dir]

    output_dir  Directory to save captured images (default: viewfinder_output/)
"""

import sys
import time
import logging
from pathlib import Path

try:
    import cv2
    import numpy as np
except ImportError:
    print(
        "ERROR: This example requires opencv-python and numpy.\n"
        "Install them with:\n\n"
        "    pip install opencv-python numpy\n\n"
        "Or, if you used the project's optional extras:\n\n"
        '    pip install -e ".[gui]"\n'
    )
    raise SystemExit(1)

from pysonycam import SonyCamera, DriveMode
from pysonycam.constants import (
    DeviceProperty,
    SaveMedia,
    SHOT_OBJECT_HANDLE,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)

WINDOW_LIVE = "LiveView"
WINDOW_PHOTO = "Captured Photo"
WINDOW_BURST = "Burst 3x3"


def decode_jpeg(data: bytes) -> np.ndarray:
    """Decode JPEG bytes to an OpenCV BGR image."""
    arr = np.frombuffer(data, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def make_grid_3x3(images: list[np.ndarray]) -> np.ndarray:
    """Arrange up to 9 images into a 3×3 grid, resizing to a common size."""
    # Use the first image's dimensions as the cell size
    cell_h, cell_w = images[0].shape[:2]

    # Pad list to exactly 9 with black frames if needed
    while len(images) < 9:
        images.append(np.zeros((cell_h, cell_w, 3), dtype=np.uint8))

    # Resize all to the same cell size
    cells = [cv2.resize(img, (cell_w, cell_h)) for img in images[:9]]

    rows = [np.hstack(cells[i * 3 : i * 3 + 3]) for i in range(3)]
    return np.vstack(rows)


def capture_single(camera: SonyCamera, output_dir: Path, shot_num: int) -> None:
    """Take a single photo, download it, save and display."""
    camera.set_save_media(SaveMedia.HOST)
    camera._wait_for_property_value(DeviceProperty.SAVE_MEDIA, int(SaveMedia.HOST))
    camera._wait_for_liveview()
    camera._wait_for_shooting_file_info_clear(timeout=10.0)

    # S1 press (AF)
    camera.control_device(DeviceProperty.S1_BUTTON, 0x0002)
    af_deadline = time.monotonic() + 3.0
    while time.monotonic() < af_deadline:
        try:
            fi = camera.get_property(DeviceProperty.AF_STATUS)
            fv = fi.current_value if isinstance(fi.current_value, int) else 0
            if fv in (0x02, 0x05, 0x06):
                break
        except Exception:
            pass
        time.sleep(0.05)

    # S2 press + release (fire)
    camera.control_device(DeviceProperty.S2_BUTTON, 0x0002)
    time.sleep(0.2)
    camera.control_device(DeviceProperty.S2_BUTTON, 0x0001)
    time.sleep(0.1)
    camera.control_device(DeviceProperty.S1_BUTTON, 0x0001)

    # Wait for image
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        info = camera.get_property(DeviceProperty.SHOOTING_FILE_INFO)
        val = info.current_value if isinstance(info.current_value, int) else 0
        if val & 0x8000:
            break
        time.sleep(0.05)
    else:
        logging.warning("Timeout waiting for image")
        return

    camera.get_object_info(SHOT_OBJECT_HANDLE)
    data = camera.get_object(SHOT_OBJECT_HANDLE)

    fname = output_dir / f"photo_{shot_num:04d}.jpg"
    fname.write_bytes(data)
    logging.info("Saved single photo → %s  (%d bytes)", fname, len(data))

    img = decode_jpeg(data)
    if img is not None:
        cv2.imshow(WINDOW_PHOTO, img)

    camera._wait_for_shooting_file_info_clear(timeout=10.0)


def capture_burst_9(camera: SonyCamera, output_dir: Path, burst_num: int) -> None:
    """Take a 9-shot burst using Continuous Mid, display as 3×3 grid."""
    # continuous_burst handles save media, drive mode, AF, shutter, download
    # We need enough hold time for 9 shots at ~10 fps → ~1s should suffice,
    # but give a bit of margin.
    images = camera.continuous_burst(
        hold_seconds=1.5,
        drive_mode=DriveMode.CONTINUOUS_MID,
        output_dir=output_dir,
    )

    if not images:
        logging.warning("Burst produced no images")
        return

    # Take exactly 9 (or fewer if the camera didn't fire enough)
    images = images[:9]
    logging.info("Burst captured %d image(s)", len(images))

    decoded = []
    for i, data in enumerate(images):
        fname = output_dir / f"burst{burst_num:02d}_{i:04d}.jpg"
        fname.write_bytes(data)
        img = decode_jpeg(data)
        if img is not None:
            decoded.append(img)

    if decoded:
        grid = make_grid_3x3(decoded)
        cv2.imshow(WINDOW_BURST, grid)


def main() -> None:
    output_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("viewfinder_output")
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Live Viewfinder")
    print("  1 = single photo   2 = 9-shot burst   q = quit\n")

    with SonyCamera() as camera:
        camera.authenticate()
        print("Authenticated.")

        camera.set_mode("still")
        print("Camera in still mode.\n")

        cv2.namedWindow(WINDOW_LIVE, 0)
        cv2.namedWindow(WINDOW_PHOTO, 0)
        cv2.namedWindow(WINDOW_BURST, 0)

        shot_num = 0
        burst_num = 0

        for frame in camera.liveview_stream(count=0):
            # Decode and show LiveView frame
            img = decode_jpeg(frame)
            if img is not None:
                cv2.imshow(WINDOW_LIVE, img)

            key = cv2.waitKey(1) & 0xFF

            if key == ord("q"):
                print("\nQuitting…")
                break

            elif key == ord("1"):
                shot_num += 1
                print(f"\n  Taking single photo #{shot_num}…")
                capture_single(camera, output_dir, shot_num)
                print("  Done. Resuming LiveView…")

            elif key == ord("2"):
                burst_num += 1
                print(f"\n  Taking 9-shot burst #{burst_num}…")
                capture_burst_9(camera, output_dir, burst_num)
                print("  Done. Resuming LiveView…")

        cv2.destroyAllWindows()

    print(f"Finished — images saved to {output_dir}/")


if __name__ == "__main__":
    main()

"""
Zoom control example: demonstrate optical/digital zoom in and out.
"""

import time
import logging

from pysonycam import SonyCamera
from pysonycam.constants import DeviceProperty, ZoomSetting

logging.basicConfig(level=logging.INFO)


def main():
    with SonyCamera() as camera:
        camera.authenticate()
        print("Connected and authenticated!")

        camera.set_mode("still")
        print("Camera in Still Rec mode.\n")

        # Read current zoom scale
        props = camera.get_all_properties()
        zoom = props.get(DeviceProperty.ZOOM_SCALE)
        if zoom:
            print(f"Current zoom scale: 0x{zoom.current_value:08X}")

        # Zoom in slowly for 2 seconds
        print("Zooming in...")
        camera.zoom_in(speed=1)
        time.sleep(2)
        camera.zoom_stop()
        print("Zoom in complete.")

        time.sleep(0.5)

        # Read new zoom level
        props = camera.get_all_properties()
        zoom = props.get(DeviceProperty.ZOOM_SCALE)
        if zoom:
            print(f"Zoom scale after zoom in: 0x{zoom.current_value:08X}")

        # Zoom back out
        print("Zooming out...")
        camera.zoom_out(speed=1)
        time.sleep(2)
        camera.zoom_stop()
        print("Zoom out complete.")

        props = camera.get_all_properties()
        zoom = props.get(DeviceProperty.ZOOM_SCALE)
        if zoom:
            print(f"Final zoom scale: 0x{zoom.current_value:08X}")


if __name__ == "__main__":
    main()

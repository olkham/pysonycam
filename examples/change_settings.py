"""
Change camera settings example: read current settings and modify them.

Demonstrates reading and writing exposure mode, ISO, aperture,
shutter speed, white balance, and other properties.
"""

import logging

from pysonycam import SonyCamera, ExposureMode, WhiteBalance, FocusArea
from pysonycam.constants import (
    DeviceProperty,
    SHUTTER_SPEED_TABLE,
    F_NUMBER_TABLE,
    ISO_TABLE,
)

logging.basicConfig(level=logging.INFO)


def display_current_settings(camera: SonyCamera) -> None:
    """Read and display common camera settings."""
    props = camera.get_all_properties()

    print("\n--- Current Camera Settings ---\n")

    # Exposure mode
    exp = props.get(DeviceProperty.EXPOSURE_MODE)
    if exp:
        try:
            mode_name = ExposureMode(exp.current_value).name
        except ValueError:
            mode_name = f"0x{exp.current_value:08X}"
        print(f"  Exposure Mode:  {mode_name}")

    # Shutter speed
    ss = props.get(DeviceProperty.SHUTTER_SPEED)
    if ss:
        ss_name = SHUTTER_SPEED_TABLE.get(ss.current_value, f"0x{ss.current_value:08X}")
        print(f"  Shutter Speed:  {ss_name}")

    # Aperture
    fn = props.get(DeviceProperty.F_NUMBER)
    if fn:
        fn_name = F_NUMBER_TABLE.get(fn.current_value, f"0x{fn.current_value:04X}")
        print(f"  Aperture:       {fn_name}")

    # ISO
    iso = props.get(DeviceProperty.ISO)
    if iso:
        iso_name = ISO_TABLE.get(iso.current_value, f"0x{iso.current_value:08X}")
        print(f"  ISO:            {iso_name}")

    # White balance
    wb = props.get(DeviceProperty.WHITE_BALANCE)
    if wb:
        try:
            wb_name = WhiteBalance(wb.current_value).name
        except ValueError:
            wb_name = f"0x{wb.current_value:04X}"
        print(f"  White Balance:  {wb_name}")

    # Battery
    batt = props.get(DeviceProperty.BATTERY_LEVEL)
    if batt:
        print(f"  Battery:        0x{batt.current_value:02X}")

    print()


def main():
    with SonyCamera() as camera:
        camera.authenticate()
        print("Connected and authenticated!")

        # Switch to Still Rec mode
        camera.set_mode("still")

        # Display current settings
        display_current_settings(camera)

        # --- Change settings (uncomment as needed) ---

        # Set to Aperture Priority mode
        # camera.set_exposure_mode(ExposureMode.APERTURE_PRIORITY)
        # print("Set to Aperture Priority (A) mode")

        # Set ISO to 800
        # camera.set_iso(0x00000320)  # 800
        # print("Set ISO to 800")

        # Set aperture to F5.6
        # camera.set_aperture(0x0230)  # F5.6
        # print("Set aperture to F5.6")

        # Set white balance to Daylight
        # camera.set_white_balance(WhiteBalance.DAYLIGHT)
        # print("Set white balance to Daylight")

        # Display settings after changes
        display_current_settings(camera)


if __name__ == "__main__":
    main()

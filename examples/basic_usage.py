"""
Basic usage example: Connect to a Sony camera, authenticate, and read
all device properties with human-readable names and values.

Prerequisites:
  - Camera connected via USB and set to PC Remote mode
  - On Linux: libusb-1.0 installed; run as root or set udev rule
  - On Windows: WinUSB driver installed via Zadig
"""

import logging
from sony_camera_control import SonyCamera, property_name, format_value
from sony_camera_control.constants import DataType

logging.basicConfig(level=logging.WARNING)  # set to INFO/DEBUG for protocol details


def describe_form(info) -> str:
    """Return a compact summary of the property's valid range or enum."""
    if info.form_flag == 1:
        lo = format_value(info.property_code, info.minimum_value)
        hi = format_value(info.property_code, info.maximum_value)
        return f"  range [{lo} … {hi}]"
    if info.form_flag == 2 and info.supported_values:
        vals = [format_value(info.property_code, v) for v in info.supported_values]
        if len(vals) <= 8:
            return "  options: " + ", ".join(vals)
        return f"  options: {', '.join(vals[:6])}, … ({len(vals)} total)"
    return ""


def main():
    with SonyCamera() as camera:
        camera.authenticate()

        properties = camera.get_all_properties()
        print(f"Connected — {len(properties)} properties\n")
        print(f"  {'Code':<8} {'Name':<28} {'A':<2} {'E':<2}  {'Value':<20}  Human-readable")
        print("  " + "-" * 90)

        for code, info in sorted(properties.items()):
            rw  = "RW" if info.is_writable else "RO"
            en  = "✓" if info.is_valid else "–"
            v   = info.current_value
            raw = f"0x{v:X}" if isinstance(v, int) else repr(v)
            human = format_value(code, v) if isinstance(v, int) else ""
            name  = property_name(code)

            # Only show human-readable if it differs from the raw hex
            readable = f"→ {human}" if human != raw else ""

            print(f"  0x{code:04X}  {name:<28} {rw:<2}  {en:<2}  {raw:<20}  {readable}")

            # Print supported values on the next line if interesting
            form_str = describe_form(info)
            if form_str:
                print(f"  {'':<8} {form_str}")

        battery = camera.battery_level
        batt_str = format_value(0xD20E, battery.current_value) if battery else "N/A"
        print(f"\nBattery: {batt_str}")


if __name__ == "__main__":
    main()

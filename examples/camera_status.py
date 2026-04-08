"""
Full camera status report: firmware, lens, battery, media slots, file count,
vendor code version, and all readable device properties.

Demonstrates:
  - :meth:`~pysonycam.SonyCamera.get_software_version`
  - :meth:`~pysonycam.SonyCamera.get_vendor_code_version`
  - :meth:`~pysonycam.SonyCamera.get_lens_info`
  - :meth:`~pysonycam.SonyCamera.get_battery_info`
  - :meth:`~pysonycam.SonyCamera.get_media_slot1_status`
  - :meth:`~pysonycam.SonyCamera.get_media_slot2_status`
  - :meth:`~pysonycam.SonyCamera.get_num_objects`
  - :meth:`~pysonycam.SonyCamera.get_device_info`
  - :meth:`~pysonycam.SonyCamera.operation_results_supported`

Usage
-----
    python examples/camera_status.py [--verbose]
"""

from __future__ import annotations

import argparse
import logging

from pysonycam import SonyCamera
from pysonycam.constants import DeviceProperty
from pysonycam.exceptions import SonyCameraError
from pysonycam.format import format_value, property_name

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)

# Expected vendor code version for SDIO v3
_SDIO_V3 = 0x012C


def _section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def _row(label: str, value: object) -> None:
    print(f"  {label:<35} {value}")


def report_system(camera: SonyCamera) -> None:
    _section("System")
    try:
        fw = camera.get_software_version()
        _row("Firmware version", fw or "(not available)")
    except SonyCameraError as exc:
        _row("Firmware version", f"ERROR: {exc}")

    try:
        ver = camera.get_vendor_code_version()
        ver_str = f"0x{ver:04X}"
        if ver == _SDIO_V3:
            ver_str += "  (SDIO v3)"
        elif ver > 0:
            ver_str += f"  (v{ver >> 8}.{ver & 0xFF:02d})"
        _row("SDIO vendor code version", ver_str)
    except SonyCameraError as exc:
        _row("SDIO vendor code version", f"ERROR: {exc}")

    try:
        supported = camera.operation_results_supported()
        _row("Async operation results", "supported" if supported else "not supported")
    except SonyCameraError as exc:
        _row("Async operation results", f"ERROR: {exc}")


def report_lens(camera: SonyCamera) -> None:
    _section("Lens")
    try:
        info = camera.get_lens_info()
        _row("Model name", info.get("model_name") or "(not available)")
        _row("Serial number", info.get("serial_number") or "(not available)")
        _row("Version number", info.get("version_number") or "(not available)")
    except SonyCameraError as exc:
        _row("Lens info", f"ERROR: {exc}")

    # Raw SDIO lens information blob size
    try:
        raw = camera.get_lens_information()
        _row("Raw lens information bytes", len(raw))
    except SonyCameraError:
        pass


def report_battery(camera: SonyCamera) -> None:
    _section("Battery")
    try:
        info = camera.get_battery_info()
        mins = info.get("remaining_minutes")
        volts = info.get("remaining_voltage")
        total = info.get("total_remaining")
        source = info.get("power_source")

        _row("Remaining (minutes)", mins if mins is not None else "(N/A)")
        _row("Voltage (raw)", f"0x{volts:04X}" if isinstance(volts, int) else "(N/A)")
        _row("Total remaining (raw)", f"0x{total:04X}" if isinstance(total, int) else "(N/A)")
        _row("Power source (raw)", f"0x{source:04X}" if isinstance(source, int) else "(N/A)")
    except SonyCameraError as exc:
        _row("Battery info", f"ERROR: {exc}")

    # Classic battery level property
    try:
        props = camera.get_all_properties()
        batt = props.get(DeviceProperty.BATTERY_LEVEL)
        if batt:
            label = format_value(DeviceProperty.BATTERY_LEVEL, batt.current_value)
            _row("Battery level", label)
    except SonyCameraError:
        pass


def _slot_report(label: str, info: dict) -> None:
    status = info.get("status")
    shots = info.get("remaining_shots")
    secs = info.get("remaining_time_s")
    _row(f"{label} status (raw)", f"0x{status:04X}" if isinstance(status, int) else "(N/A)")
    _row(f"{label} remaining shots", shots if shots is not None else "(N/A)")
    _row(f"{label} remaining time (s)", secs if secs is not None else "(N/A)")


def report_media(camera: SonyCamera) -> None:
    _section("Media Slots")
    try:
        _slot_report("Slot 1", camera.get_media_slot1_status())
    except SonyCameraError as exc:
        _row("Slot 1", f"ERROR: {exc}")
    try:
        _slot_report("Slot 2", camera.get_media_slot2_status())
    except SonyCameraError as exc:
        _row("Slot 2", f"ERROR: {exc}")

    # Total object count on card
    try:
        n = camera.get_num_objects()
        _row("Total objects on card", n)
    except SonyCameraError as exc:
        _row("Total objects on card", f"ERROR: {exc}")


def report_properties(camera: SonyCamera) -> None:
    _section("Device Properties (current values)")
    try:
        props = camera.get_all_properties()
    except SonyCameraError as exc:
        print(f"  Could not read properties: {exc}")
        return

    for code, info in sorted(props.items(), key=lambda kv: kv[0]):
        name = property_name(code)
        raw = info.current_value
        try:
            human = format_value(code, raw) if isinstance(raw, int) else str(raw)
        except Exception:
            human = str(raw)
        _row(f"0x{code:04X}  {name}", human)


def main() -> None:
    parser = argparse.ArgumentParser(description="Print a full camera status report")
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Also dump all device properties"
    )
    args = parser.parse_args()

    with SonyCamera() as camera:
        camera.authenticate()
        print("\n=== Sony Camera Status Report ===")

        report_system(camera)
        report_lens(camera)
        report_battery(camera)
        report_media(camera)

        if args.verbose:
            report_properties(camera)
        else:
            print("\n(Run with --verbose to dump all device properties)")

        print(f"\n{'─' * 60}\n")


if __name__ == "__main__":
    main()

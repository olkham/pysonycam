"""
Advanced focus control: focus point placement, magnifier, continuous focus
drive, AF settings, and zoom/focus position presets.

Demonstrates:
  - :meth:`~pysonycam.SonyCamera.set_focus_point`
  - :meth:`~pysonycam.SonyCamera.enable_focus_magnifier` / :meth:`disable_focus_magnifier`
  - :meth:`~pysonycam.SonyCamera.focus_mag_increase` / :meth:`focus_mag_decrease`
  - :meth:`~pysonycam.SonyCamera.focus_continuous`
  - :meth:`~pysonycam.SonyCamera.save_zoom_focus_position` / :meth:`load_zoom_focus_position`
  - :meth:`~pysonycam.SonyCamera.set_focus_mode_setting`
  - :meth:`~pysonycam.SonyCamera.set_af_transition_speed`
  - :meth:`~pysonycam.SonyCamera.set_af_subject_shift_sensitivity`
  - :meth:`~pysonycam.SonyCamera.get_focal_position`

Usage
-----
    python examples/advanced_focus.py [options]

    Options:
        --demo magnifier        Run the focus magnifier workflow
        --demo focus-point      Move the focus point to several positions
        --demo continuous       Drive focus near/far with continuous speed
        --demo preset           Save and restore a zoom/focus position preset
        --demo af-settings      Apply AF speed and sensitivity settings
        --all                   Run all demos in sequence (default)
"""

from __future__ import annotations

import argparse
import time
import logging

from pysonycam import SonyCamera
from pysonycam.constants import DeviceProperty
from pysonycam.exceptions import SonyCameraError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# Focus mode codes (camera-dependent; adjust if needed)
FOCUS_MODE_AFS = 0x0001   # AF-S  (single-shot autofocus)
FOCUS_MODE_AFC = 0x0002   # AF-C  (continuous autofocus)
FOCUS_MODE_MF  = 0x0004   # Manual focus

# Focus point positions (signed 16-bit, relative to live-view centre)
FOCUS_POINTS = [
    (0,    0,   "Centre"),
    (-800, -600, "Top-left"),
    (800,  -600, "Top-right"),
    (0,    600,  "Bottom-centre"),
]


def demo_magnifier(camera: SonyCamera) -> None:
    print("\n[Magnifier demo]")
    log.info("Enabling focus magnifier…")
    camera.enable_focus_magnifier()
    time.sleep(1)

    log.info("Increasing magnification level…")
    camera.focus_mag_increase()
    time.sleep(0.5)
    camera.focus_mag_increase()
    time.sleep(1)

    log.info("Decreasing magnification level…")
    camera.focus_mag_decrease()
    time.sleep(0.5)

    log.info("Disabling focus magnifier…")
    camera.disable_focus_magnifier()
    time.sleep(0.5)
    print("[Magnifier demo] done.")


def demo_focus_point(camera: SonyCamera) -> None:
    print("\n[Focus-point demo]")
    for x, y, label in FOCUS_POINTS:
        log.info("Moving focus point → %s (%d, %d)", label, x, y)
        camera.set_focus_point(x, y)
        time.sleep(0.8)
    print("[Focus-point demo] done.")


def demo_continuous_focus(camera: SonyCamera) -> None:
    print("\n[Continuous focus demo]")
    pos_before = camera.get_focal_position()
    log.info("Focal position before: %d", pos_before)

    log.info("Driving focus far (speed=+8000) for 1 s…")
    camera.focus_continuous(8000)
    time.sleep(1)
    camera.focus_continuous(0)   # stop

    pos_mid = camera.get_focal_position()
    log.info("Focal position after far push: %d  (delta: %+d)", pos_mid, pos_mid - pos_before)
    time.sleep(0.3)

    log.info("Driving focus near (speed=-8000) for 1 s…")
    camera.focus_continuous(-8000)
    time.sleep(1)
    camera.focus_continuous(0)   # stop

    pos_after = camera.get_focal_position()
    log.info("Focal position after near pull: %d  (delta: %+d)", pos_after, pos_after - pos_mid)
    print("[Continuous focus demo] done.")


def demo_preset(camera: SonyCamera) -> None:
    print("\n[Zoom/focus preset demo]")
    log.info("Saving current zoom and focus position to preset…")
    camera.save_zoom_focus_position()
    time.sleep(0.5)

    # Simulate moving focus away from the saved position
    log.info("Nudging focus to a different position…")
    camera.focus_continuous(5000)
    time.sleep(0.5)
    camera.focus_continuous(0)

    log.info("Recalling saved zoom/focus preset…")
    camera.load_zoom_focus_position()
    time.sleep(0.5)
    log.info("Preset recalled.")
    print("[Zoom/focus preset demo] done.")


def demo_af_settings(camera: SonyCamera) -> None:
    print("\n[AF settings demo]")
    log.info("Setting focus mode → AF-S (0x%04X)", FOCUS_MODE_AFS)
    camera.set_focus_mode_setting(FOCUS_MODE_AFS)
    time.sleep(0.3)

    log.info("Setting AF transition speed → 4 (mid-range)")
    camera.set_af_transition_speed(4)
    time.sleep(0.3)

    log.info("Setting AF subject shift sensitivity → 3")
    camera.set_af_subject_shift_sensitivity(3)
    time.sleep(0.3)

    log.info("Switching to AF-C for continuous autofocus…")
    camera.set_focus_mode_setting(FOCUS_MODE_AFC)
    time.sleep(0.3)

    log.info("Restoring AF-S…")
    camera.set_focus_mode_setting(FOCUS_MODE_AFS)
    print("[AF settings demo] done.")


_DEMO_REGISTRY: dict[str, tuple[str, callable]] = {
    "magnifier":   ("Focus magnifier on/off + zoom levels", demo_magnifier),
    "focus-point": ("Move focus point to several positions", demo_focus_point),
    "continuous":  ("Drive focus near/far at a continuous speed", demo_continuous_focus),
    "preset":      ("Save and recall a zoom/focus position preset", demo_preset),
    "af-settings": ("AF transition speed and subject shift sensitivity", demo_af_settings),
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Advanced focus control demo")
    parser.add_argument(
        "--demo",
        choices=list(_DEMO_REGISTRY),
        metavar="NAME",
        help=f"One of: {', '.join(_DEMO_REGISTRY)}",
    )
    parser.add_argument("--all", action="store_true", default=True,
                        help="Run all demos (default)")
    args = parser.parse_args()

    selected = [args.demo] if args.demo else list(_DEMO_REGISTRY)

    with SonyCamera() as camera:
        camera.authenticate()
        print("Connected and authenticated.")
        camera.set_mode("still")
        time.sleep(0.5)

        for key in selected:
            description, fn = _DEMO_REGISTRY[key]
            print(f"\n{'─' * 55}")
            print(f"  Demo: {description}")
            print(f"{'─' * 55}")
            try:
                fn(camera)
            except SonyCameraError as exc:
                log.error("Demo '%s' failed: %s", key, exc)

        print("\nAll selected demos complete.")


if __name__ == "__main__":
    main()

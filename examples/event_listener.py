"""
Event Listener — Phase 7 example.

Demonstrates how to use the camera's event system:
  - Register callbacks for PROPERTY_CHANGED and CAPTURED_EVENT
  - Start the background event listener
  - Print incoming events to the console for 30 seconds
  - Stop the listener cleanly

Usage::

    python examples/event_listener.py

The camera must be in PC Remote mode and connected before running this script.
"""

import time
import logging
from pysonycam import SonyCamera
from pysonycam.constants import DeviceProperty, SDIOEventCode
from pysonycam.format import property_name, format_value
from pysonycam.ptp import PTPEvent

logging.basicConfig(level=logging.WARNING)

LISTEN_SECONDS = 30


def on_property_changed(event: PTPEvent) -> None:
    prop_code = event.params[0] if event.params else 0
    name = property_name(prop_code)
    print(f"[PROPERTY_CHANGED] 0x{prop_code:04X} ({name})")


def on_captured(event: PTPEvent) -> None:
    print(f"[CAPTURED_EVENT] params={event.params}")


def main() -> None:
    with SonyCamera() as camera:
        camera.authenticate()
        print("Authenticated. Registering event callbacks…")

        camera.on_event(SDIOEventCode.PROPERTY_CHANGED, on_property_changed)
        camera.on_event(SDIOEventCode.CAPTURED_EVENT, on_captured)

        camera.start_event_listener()
        print(f"Listening for events for {LISTEN_SECONDS} s. "
              "Change settings on the camera to see PROPERTY_CHANGED events.")

        try:
            time.sleep(LISTEN_SECONDS)
        except KeyboardInterrupt:
            print("\nInterrupted by user.")
        finally:
            camera.stop_event_listener()
            print("Event listener stopped.")


if __name__ == "__main__":
    main()

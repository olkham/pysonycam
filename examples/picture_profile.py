"""
Edit Sony Picture Profile (PP) settings via the SDK.

Picture Profiles are available on most Sony Alpha and cinema cameras (A9 II,
A7R IV, A7C, A7 IV, A7S III, FX3, FX30, ZV-E1, etc.).  There are up to 11
PP slots (PP1–PP11) plus some cameras expose LUT slots (LUT1–LUT4).

When a Picture Profile is active the Creative Style property is DISABLED.
Switch to PP OFF first if you want to use Creative Style instead.

Key concepts
------------
  Gamma   — tone curve (S-Log3, HLG, Cine1–4, Movie, etc.)
  Color   — colour gamut + colour science (S-Gamut3.Cine, BT.2020, Movie, etc.)
  Detail  — edge enhancement / sharpness
  Knee    — highlight roll-off (auto / manual point + slope)
  Black   — black level and black-gamma (shadow toe)

Usage examples
--------------
  # List built-in presets
  python examples/picture_profile.py --list

  # Apply S-Log3/S-Gamut3.Cine to PP7
  python examples/picture_profile.py --preset slog3 --slot 7

  # Set individual parameters on the currently active slot
  python examples/picture_profile.py --gamma S_LOG3 --color-mode S_GAMUT3_CINE

  # Activate PP3 without changing any other parameters
  python examples/picture_profile.py --slot 3

  # Turn Picture Profile OFF (re-enables Creative Style)
  python examples/picture_profile.py --slot 0

  # Copy the current PP to another slot
  python examples/picture_profile.py --slot 7 --copy-to 8

  # Show what a preset would apply (without connecting to a camera)
  python examples/picture_profile.py --list --preset slog3
"""

import argparse
import sys
import time

# ---------------------------------------------------------------------------
# Built-in PP presets
# ---------------------------------------------------------------------------
# Each preset is a dict whose keys exactly match the ``apply_picture_profile_settings``
# parameter names (without the ``set_pp_`` prefix).
# Numeric values for gamma / color_mode / etc. correspond to the enums in
# pysonycam.constants.  Using string names makes the dicts self-documenting;
# they are resolved to int at apply-time via the enum by name.
# ---------------------------------------------------------------------------

PRESETS = {
    "slog3": {
        "_description": "S-Log3 / S-Gamut3.Cine — standard log acquisition for post",
        "gamma":             "S_LOG3",
        "color_mode":        "S_GAMUT3_CINE",
        "black_level":       0,
        "knee_mode":         "AUTO",
        "knee_autoset_sensitivity": "MID",
        "saturation":        0,
        "color_phase":       0,
        "detail_level":      -7,
        "detail_adjust_mode": "MANUAL",
        "detail_vh_balance":  0,
        "detail_bw_balance": "TYPE3",
        "detail_limit":      0,
        "detail_crispening": 0,
        "detail_highlight_detail": 0,
    },
    "slog3_sgamut3": {
        "_description": "S-Log3 / S-Gamut3 — broader gamut for VFX / chroma work",
        "gamma":             "S_LOG3",
        "color_mode":        "S_GAMUT3",
        "black_level":       0,
        "knee_mode":         "AUTO",
        "saturation":        0,
        "color_phase":       0,
        "detail_level":      -7,
        "detail_adjust_mode": "MANUAL",
    },
    "slog2": {
        "_description": "S-Log2 / S-Gamut — legacy log for S-Gamut colour space",
        "gamma":             "S_LOG2",
        "color_mode":        "S_GAMUT",
        "black_level":       0,
        "knee_mode":         "AUTO",
        "saturation":        0,
        "detail_level":      -7,
        "detail_adjust_mode": "MANUAL",
    },
    "hlg": {
        "_description": "HLG / S-Gamut3.Cine — Hybrid Log-Gamma for HDR delivery",
        "gamma":             "HLG",
        "color_mode":        "S_GAMUT3_CINE",
        "black_level":       0,
        "knee_mode":         "AUTO",
        "saturation":        0,
        "color_phase":       0,
        "detail_level":      -3,
        "detail_adjust_mode": "MANUAL",
    },
    "hlg_bt2020": {
        "_description": "HLG / BT.2020 — HDR broadcast-standard colour",
        "gamma":             "HLG",
        "color_mode":        "BT2020",
        "black_level":       0,
        "knee_mode":         "AUTO",
        "saturation":        0,
        "detail_level":      -3,
        "detail_adjust_mode": "MANUAL",
    },
    "cine_ei": {
        "_description": "Cine EI look — Cine1 gamma + S-Cinetone colour science",
        "gamma":             "CINE1",
        "color_mode":        "S_CINETONE",
        "black_level":       0,
        "knee_mode":         "AUTO",
        "saturation":        0,
        "color_phase":       0,
        "detail_level":      0,
        "detail_adjust_mode": "AUTO",
    },
    "still": {
        "_description": "Natural still — Still gamma + Still colour, neutral adjustments",
        "gamma":             "STILL",
        "color_mode":        "STILL",
        "black_level":       0,
        "knee_mode":         "AUTO",
        "saturation":        0,
        "color_phase":       0,
        "detail_level":      0,
        "detail_adjust_mode": "AUTO",
    },
    "neutral_flat": {
        "_description": "Neutral flat — Movie gamma, low detail, for grading",
        "gamma":             "MOVIE",
        "color_mode":        "MOVIE",
        "black_level":       -3,
        "knee_mode":         "MANUAL",
        "knee_manualset_point": 10500,   # 105 %
        "knee_manualset_slope": -5,
        "saturation":        -8,
        "color_phase":       0,
        "detail_level":      -7,
        "detail_adjust_mode": "MANUAL",
        "detail_crispening": 1,
    },
    "s_cinetone": {
        "_description": "S-Cinetone — Sony's in-camera cinematic look (memory-colour enhanced)",
        "gamma":             "S_CINETONE",
        "color_mode":        "S_CINETONE",
        "black_level":       0,
        "knee_mode":         "AUTO",
        "saturation":        0,
        "color_phase":       0,
        "detail_level":      0,
        "detail_adjust_mode": "AUTO",
    },
}


def _resolve_settings(settings: dict, pp_classes: dict) -> dict:
    """
    Resolve string enum names to integer values using the provided enum classes.

    ``pp_classes`` maps param key → enum class, e.g.::

        {"gamma": PPGamma, "color_mode": PPColorMode, ...}
    """
    resolved = {}
    for k, v in settings.items():
        if k.startswith("_"):
            continue
        if isinstance(v, str) and k in pp_classes:
            resolved[k] = pp_classes[k][v]
        else:
            resolved[k] = v
    return resolved


def _print_preset(name: str, settings: dict) -> None:
    desc = settings.get("_description", "")
    print(f"\n  {name}")
    if desc:
        print(f"    {desc}")
    for k, v in settings.items():
        if not k.startswith("_"):
            print(f"    {k:30s} = {v}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Edit Sony Picture Profile settings via the SDK.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--slot", "-s", type=int, default=None,
        metavar="N",
        help="Activate PP slot N (1-11) or 0 to turn Picture Profile OFF.",
    )
    parser.add_argument(
        "--preset", "-p", default=None,
        metavar="NAME",
        help="Apply a built-in preset (see --list for names).",
    )
    parser.add_argument(
        "--gamma", "-g", default=None,
        metavar="NAME",
        help="Set gamma curve by PPGamma enum name (e.g. S_LOG3, HLG, CINE1).",
    )
    parser.add_argument(
        "--color-mode", "-c", default=None,
        dest="color_mode",
        metavar="NAME",
        help="Set colour mode by PPColorMode enum name (e.g. S_GAMUT3_CINE).",
    )
    parser.add_argument(
        "--copy-to", type=int, default=None,
        dest="copy_to",
        metavar="N",
        help="Copy the currently active PP slot to slot N (1-11).",
    )
    parser.add_argument(
        "--list", "-l", action="store_true",
        help="List available built-in presets and exit.",
    )
    parser.add_argument(
        "--read", "-r", action="store_true",
        help="Read back PP slot and all bulk-readable properties after writing (diagnostic).",
    )
    parser.add_argument(
        "--dump", action="store_true",
        help="Dump all property codes returned by GetAllExtDevicePropInfo (diagnostic).",
    )
    args = parser.parse_args()

    # --list — no camera needed -----------------------------------------------
    if args.list:
        print("Built-in Picture Profile presets:")
        for name, settings in PRESETS.items():
            _print_preset(name, settings)
        if args.preset and args.preset in PRESETS:
            print(f"\nPreset '{args.preset}' selected above.")
        return

    # Nothing requested --------------------------------------------------------
    if args.slot is None and args.preset is None and args.gamma is None \
            and args.color_mode is None and args.copy_to is None \
            and not args.read and not args.dump:
        parser.print_help()
        return

    # Camera operations --------------------------------------------------------
    try:
        from pysonycam import (
            SonyCamera,
            DeviceProperty,
            PictureProfileSlot,
            PPGamma,
            PPBlackGammaRange,
            PPKneeMode,
            PPKneeAutoSensitivity,
            PPColorMode,
            PPDetailAdjustMode,
            PPDetailBWBalance,
        )
    except ImportError as exc:
        print(f"Error: could not import pysonycam — {exc}", file=sys.stderr)
        sys.exit(1)

    # Map of settings key → enum class for string-to-int resolution
    PP_ENUM_CLASSES = {
        "gamma":                   PPGamma,
        "black_gamma_range":       PPBlackGammaRange,
        "knee_mode":               PPKneeMode,
        "knee_autoset_sensitivity": PPKneeAutoSensitivity,
        "color_mode":              PPColorMode,
        "detail_adjust_mode":      PPDetailAdjustMode,
        "detail_bw_balance":       PPDetailBWBalance,
    }

    with SonyCamera() as camera:
        camera.authenticate()

        # 1. Activate the requested slot first so subsequent parameter writes
        #    target the correct PP slot.
        if args.slot is not None:
            slot_val = PictureProfileSlot(args.slot) if args.slot != 0 else PictureProfileSlot.OFF
            camera.set_picture_profile(slot_val)
            label = "OFF" if args.slot == 0 else f"PP{args.slot}"
            print(f"Picture Profile slot set to {label}.")
            # Give the camera a moment to commit the slot change before
            # writing sub-parameters.
            time.sleep(0.3)

        writing_params = (
            args.preset is not None
            or args.gamma is not None
            or args.color_mode is not None
        )
        if writing_params:
            # Fetch bulk property list to (a) check which slot is active and
            # (b) verify this camera supports PP sub-parameter editing.
            props = camera.get_all_properties()

            # Capability check: PP sub-parameters (0xD0E0-0xD0F8) only appear
            # in the bulk response on supported cameras (ILCE-1, ILCE-7M4,
            # FX3, etc.).  The RX100M7 and several other models only support
            # PP slot selection (0xD23F) — sub-parameter writes are silently
            # discarded by the camera.
            if DeviceProperty.PP_GAMMA not in props:
                print(
                    "Error: this camera does not support remote PP sub-parameter\n"
                    "editing via the SDK (PP Gamma / Color Mode / Detail etc. are\n"
                    "not exposed in the device property list).\n"
                    "\n"
                    "PP slot selection (--slot N) is still supported.\n"
                    "\n"
                    "Cameras with full PP sub-parameter editing support include:\n"
                    "  ILCE-1/1M2, ILCE-9M3, ILCE-7M4/7M5, ILCE-7SM3,\n"
                    "  ILCE-7CM2/7CR, ILCE-6700, ILME-FX3/FX30/FX2, ZV-E1.",
                    file=sys.stderr,
                )
                sys.exit(1)

            slot_info = props.get(DeviceProperty.PICTURE_PROFILE)
            current_slot = slot_info.current_value if slot_info else None

            if current_slot == 0 or current_slot is None:
                print(
                    "Error: Picture Profile is currently OFF.  Parameter writes "
                    "would be stored but not applied visually.\n"
                    "  Use --slot N (e.g. --slot 1) to activate a PP slot first, "
                    "then the parameters will take effect.",
                    file=sys.stderr,
                )
                sys.exit(1)

            if args.slot is None:
                print(f"Writing to currently active slot PP{current_slot}.")

        # 2. Apply a named preset (after activating the slot, so both happen).
        if args.preset is not None:
            preset_name = args.preset.lower()
            if preset_name not in PRESETS:
                available = ", ".join(PRESETS.keys())
                print(
                    f"Error: unknown preset '{preset_name}'. "
                    f"Available: {available}",
                    file=sys.stderr,
                )
                sys.exit(1)
            raw = PRESETS[preset_name]
            settings = _resolve_settings(raw, PP_ENUM_CLASSES)
            # Don't re-send slot — we already did it above (or the user
            # wants to apply to the currently active slot).
            settings.pop("slot", None)
            camera.apply_picture_profile_settings(settings)
            desc = raw.get("_description", preset_name)
            print(f"Preset '{preset_name}' applied: {desc}")

        # 3. Apply ad-hoc gamma / colour mode overrides.
        if args.gamma is not None:
            try:
                gamma_val = PPGamma[args.gamma.upper()]
            except KeyError:
                names = [e.name for e in PPGamma]
                print(
                    f"Error: unknown gamma '{args.gamma}'. "
                    f"Valid names: {', '.join(names)}",
                    file=sys.stderr,
                )
                sys.exit(1)
            camera.set_pp_gamma(gamma_val)
            print(f"Gamma set to {gamma_val.name}.")

        if args.color_mode is not None:
            try:
                cm_val = PPColorMode[args.color_mode.upper()]
            except KeyError:
                names = [e.name for e in PPColorMode]
                print(
                    f"Error: unknown colour mode '{args.color_mode}'. "
                    f"Valid names: {', '.join(names)}",
                    file=sys.stderr,
                )
                sys.exit(1)
            camera.set_pp_color_mode(cm_val)
            print(f"Colour mode set to {cm_val.name}.")

        # 4. Copy the active slot to another slot.
        if args.copy_to is not None:
            if not 1 <= args.copy_to <= 11:
                print("Error: --copy-to must be between 1 and 11.", file=sys.stderr)
                sys.exit(1)
            camera.copy_picture_profile(dest_slot=args.copy_to)
            print(f"Picture Profile copied to PP{args.copy_to}.")

        # 5. Diagnostic read-back via GetAllExtDevicePropInfo (0x9209).
        # NOTE: PP sub-parameters (0xD0E0-0xD0F8) are NOT included in the
        # bulk property response on the RX100M7.  Individual SDIOGetExtDevicePropInfo
        # (0x9208) calls cause a USB pipe stall on this camera.
        # To verify writes took effect: disconnect USB then check the camera menu.
        if args.read or args.dump:
            time.sleep(0.2)
            props = camera.get_all_properties()

            if args.read:
                _PP_DIAG = [
                    (DeviceProperty.PICTURE_PROFILE, "Slot       (0xD23F)"),
                    (DeviceProperty.PP_GAMMA,        "Gamma      (0xD0E1)"),
                    (DeviceProperty.PP_COLOR_MODE,   "Color Mode (0xD0E9)"),
                    (DeviceProperty.PP_BLACK_LEVEL,  "Blk Level  (0xD0E0)"),
                    (DeviceProperty.PP_SATURATION,   "Saturation (0xD0EA)"),
                    (DeviceProperty.PP_DETAIL_LEVEL, "Detail     (0xD0F2)"),
                ]
                print("\nCamera read-back (GetAllExtDevicePropInfo):")
                for code, label in _PP_DIAG:
                    info = props.get(code)
                    if info is None:
                        print(f"  {label}: not in bulk response")
                    else:
                        print(
                            f"  {label}: value=0x{info.current_value:04X}  "
                            f"is_enable={info.is_enable}"
                        )
                print(
                    "\n  NOTE: PP sub-parameters are write-only from the SDK's perspective\n"
                    "  on this camera — they do not appear in the property dump.\n"
                    "  Disconnect USB and check the camera menu to confirm writes."
                )

            if args.dump:
                print(f"\nAll {len(props)} property codes in bulk response:")
                for code in sorted(props):
                    info = props[code]
                    val = info.current_value
                    val_str = f"0x{val:08X}" if isinstance(val, int) else repr(val)
                    print(
                        f"  0x{code:04X}  value={val_str}"
                        f"  enabled={info.is_enable}  rw={'RW' if info.is_writable else 'RO'}"
                    )

        print("Done.")


if __name__ == "__main__":
    main()

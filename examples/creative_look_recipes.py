"""
Apply Sony film-simulation settings to the camera programmatically.

Sony cameras use one of two image-processing systems depending on model:

  Creative Look  (newer cameras: A7 IV/V, A7R V, A1, A9 III, ZV-E1, FX3, …)
  ~~~~~~~~~~~~~~
  Property 0xD0FA.  Styles are named by two/three-letter codes: ST, PT, NT,
  VV, VV2, FL, IN, SH, BW, SE, FL2, FL3.  All eight tune parameters
  (Contrast, Highlights, Shadows, Fade, Saturation, Sharpness,
  SharpnessRange, Clarity) are settable remotely via SDK.

  Creative Style  (older cameras: A9 II, A7R IV/IVA, A7C, ZV-E10, …)
  ~~~~~~~~~~~~~~
  Property 0xD240.  Styles are named Standard, Vivid, Portrait, …
  ONLY the base-style selection is remotely settable.  The per-style
  contrast/saturation/sharpness sliders cannot be set via SDK —
  those must be adjusted on-camera.
  Creative Style is also DISABLED when a Picture Profile is active;
  use --disable-pp to switch Picture Profile OFF first.

This script auto-detects which system the connected camera uses and
behaves accordingly.

Usage
-----
  # List all built-in recipes
  python examples/creative_look_recipes.py --list

  # Apply a Creative Look recipe (newer cameras)
  python examples/creative_look_recipes.py --recipe "Kodak Portra 400"
  python examples/creative_look_recipes.py --recipe 4         # by index

  # Apply a bare Creative Look style (no tune adjustments)
  python examples/creative_look_recipes.py --look FL

  # Apply a Creative Style (older cameras)
  python examples/creative_look_recipes.py --style VIVID

  # Disable Picture Profile then apply a style (older cameras)
  python examples/creative_look_recipes.py --style VIVID --disable-pp

  # Use a custom recipes file
  python examples/creative_look_recipes.py --recipe 0 --json path/to/file.json

  # Run the per-setter demo (Creative Look cameras only)
  python examples/creative_look_recipes.py --demo

Built-in recipes (from docs/creative_recipes.json):
    0  50s Kodachrome       (IN)
    1  Fujifilm Fortia      (VV2)
    2  Kodak Vision 200T    (PT)
    3  Phoenix Harman       (FL)
    4  Kodak Portra 400     (NT)
    5  Cinestill 800        (IN)
    6  Cuba                 (FL)
    7  Provia               (ST)
    8  Velvia               (VV)
    9  Astia                (PT)
   10  Classic Chrome       (NT)
   11  Pro Neg Std.         (PT)
   12  Classic Negative     (FL)
   13  Eterna               (ST)
   14  Nostalgic Neg        (IN)
   15  Kodak Gold V2        (NL)
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from pysonycam import SonyCamera, CreativeLookName, CreativeStyleName
from pysonycam.constants import DeviceProperty
from pysonycam.exceptions import SonyCameraError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# Default bundled recipes file
_DEFAULT_RECIPES = (
    Path(__file__).resolve().parent.parent
    / "docs"
    / "creative_recipes.json"
)

# Best-effort mapping from Creative Look abbreviations to the nearest
# Creative Style equivalent, used when the camera only supports Creative Style.
_CL_TO_CS: dict[str, CreativeStyleName] = {
    "ST":  CreativeStyleName.STANDARD,
    "PT":  CreativeStyleName.PORTRAIT,
    "NT":  CreativeStyleName.NEUTRAL,
    "VV":  CreativeStyleName.VIVID,
    "VV2": CreativeStyleName.VIVID,        # no Vivid 2 equiv; closest is Vivid
    "FL":  CreativeStyleName.LIGHT,        # Film ≈ Light
    "FL2": CreativeStyleName.LIGHT,
    "FL3": CreativeStyleName.LIGHT,
    "IN":  CreativeStyleName.CLEAR,        # Instant ≈ Clear
    "SH":  CreativeStyleName.LIGHT,        # Soft Highkey ≈ Light
    "BW":  CreativeStyleName.BW,
    "SE":  CreativeStyleName.SEPIA,
    "NL":  CreativeStyleName.NEUTRAL,
}


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def _load_recipes(json_path: Path) -> list[dict]:
    if not json_path.exists():
        raise FileNotFoundError(
            f"Recipes JSON not found: {json_path}\n"
            "Run scripts/extract_recipes.py to generate it."
        )
    return json.loads(json_path.read_text(encoding="utf-8"))


def _print_recipe_list(recipes: list[dict]) -> None:
    print(f"\n{'#':<4} {'Name':<28} {'Look':<6} {'Contrast':>8} {'Saturation':>10}")
    print("─" * 62)
    for i, r in enumerate(recipes):
        print(
            f"{i:<4} {r.get('name', '?'):<28} "
            f"{r.get('creative_look', '?'):<6} "
            f"{str(r.get('contrast', '')):>8} "
            f"{str(r.get('saturation', '')):>10}"
        )
    print(f"\n{len(recipes)} recipe(s) available.")
    print("Note: recipes require a Creative Look camera (A7 IV+, A1, ZV-E1, FX3, …)")


def _print_recipe_detail(recipe: dict) -> None:
    fields = [
        ("Creative Look",   recipe.get("creative_look")),
        ("Contrast",        recipe.get("contrast")),
        ("Highlights",      recipe.get("highlights")),
        ("Shadows",         recipe.get("shadows")),
        ("Fade",            recipe.get("fade")),
        ("Saturation",      recipe.get("saturation")),
        ("Sharpness",       recipe.get("sharpness")),
        ("Sharpness Range", recipe.get("sharpness_range")),
        ("Clarity",         recipe.get("clarity")),
        ("AWB",             recipe.get("awb")),
        ("DRO",             recipe.get("dro")),
    ]
    print(f"\n  Recipe : {recipe.get('name', 'Unknown')}")
    print("  " + "─" * 40)
    for label, val in fields:
        if val is not None:
            print(f"  {label:<20} {val}")


def _find_recipe(recipes: list[dict], query: str) -> dict:
    """Find a recipe by name (case-insensitive substring) or integer index."""
    if query.lstrip("-").isdigit():
        idx = int(query)
        if 0 <= idx < len(recipes):
            return recipes[idx]
        raise ValueError(f"Index {idx} out of range (0–{len(recipes) - 1})")
    lower = query.lower()
    matches = [r for r in recipes if lower in r.get("name", "").lower()]
    if not matches:
        raise ValueError(f"No recipe matching {query!r}")
    if len(matches) > 1:
        names = [r["name"] for r in matches]
        raise ValueError(f"Ambiguous query {query!r} matches: {names}")
    return matches[0]


# ---------------------------------------------------------------------------
# Creative Look helpers (newer cameras)
# ---------------------------------------------------------------------------

def apply_cl_recipe(camera: SonyCamera, recipe: dict) -> None:
    """Apply a full Creative Look recipe to a Creative Look camera."""
    _print_recipe_detail(recipe)
    log.info("Applying Creative Look recipe: %s", recipe.get("name", "?"))
    camera.apply_creative_look_recipe(recipe)
    log.info("Recipe applied.")

    awb = recipe.get("awb")
    dro = recipe.get("dro")
    if awb or dro:
        print("\n  NOTE: manual settings still required on the camera body:")
        if awb:
            print(f"     AWB : {awb}")
        if dro:
            print(f"     DRO : {dro}")
        print()


def demo_individual_cl_setters(camera: SonyCamera) -> None:
    """Demonstrate each Creative Look setter individually."""
    print("\n[Individual setter demo] Applying 'Cinestill 800' equivalent…")
    camera.set_creative_look(CreativeLookName.IN)
    camera.set_creative_look_contrast(3)
    camera.set_creative_look_highlights(4)
    camera.set_creative_look_shadows(-9)
    camera.set_creative_look_fade(1)
    camera.set_creative_look_saturation(7)
    camera.set_creative_look_sharpness(0)
    camera.set_creative_look_sharpness_range(1)
    camera.set_creative_look_clarity(0)
    log.info("Individual setters complete.")

    try:
        props = camera.get_all_properties()
        info = props.get(DeviceProperty.CREATIVE_LOOK)
        if info:
            code = info.current_value
            try:
                name = CreativeLookName(code).name
            except ValueError:
                name = f"0x{code:04X}"
            print(f"  Camera reports Creative Look: {name}")
    except SonyCameraError:
        pass


# ---------------------------------------------------------------------------
# Creative Style helpers (older cameras)
# ---------------------------------------------------------------------------

def _list_creative_styles() -> None:
    print("\nAvailable Creative Style names (--style argument):")
    for m in CreativeStyleName:
        print(f"  {m.name}")
    print()
    print("Note: per-style Contrast/Saturation/Sharpness CANNOT be set")
    print("remotely — adjust those on-camera after selecting a style.")
    print("Picture Profile must be OFF for Creative Style to be active.")
    print("Use --disable-pp to turn Picture Profile off automatically.")


def apply_cs_style(camera: SonyCamera, style_name: str, disable_pp: bool) -> None:
    """Apply a Creative Style selection to an older camera."""
    sname = style_name.upper()
    try:
        code = CreativeStyleName[sname]
    except KeyError:
        valid = [m.name for m in CreativeStyleName]
        print(f"Unknown Creative Style name: {sname!r}")
        print(f"Valid styles: {valid}")
        return

    if disable_pp:
        log.info("Turning Picture Profile OFF (0x00)…")
        camera.set_property(DeviceProperty.PICTURE_PROFILE, 0x00, size=1)
        log.info("Picture Profile OFF.")

    log.info("Setting Creative Style → %s (0x%02X)", sname, int(code))
    camera.set_creative_style(code)
    log.info("Creative Style set to %s.", sname)
    print(f"  Creative Style: {sname}")
    print("  NOTE: Contrast/Saturation/Sharpness must be adjusted on-camera.")


def apply_cs_from_recipe(
    camera: SonyCamera,
    recipe: dict,
    disable_pp: bool,
) -> None:
    """Apply the nearest Creative Style for a Creative Look recipe."""
    cl_abbr = recipe.get("creative_look", "ST").upper()
    cs = _CL_TO_CS.get(cl_abbr, CreativeStyleName.STANDARD)
    _print_recipe_detail(recipe)
    print(f"  (Creative Style camera: CL '{cl_abbr}' ≈ CS '{cs.name}')")
    print("  NOTE: Contrast/Saturation/Sharpness CANNOT be set remotely.")
    print("        Suggested (manual) Contrast:   ", recipe.get("contrast", "n/a"))
    print("        Suggested (manual) Saturation: ", recipe.get("saturation", "n/a"))
    print("        Suggested (manual) Sharpness:  ", recipe.get("sharpness", "n/a"))
    if disable_pp:
        log.info("Turning Picture Profile OFF…")
        camera.set_property(DeviceProperty.PICTURE_PROFILE, 0x00, size=1)
    camera.set_creative_style(cs)
    log.info("Creative Style set to %s.", cs.name)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply Sony Creative Look or Creative Style settings"
    )
    parser.add_argument(
        "--json", type=Path, default=_DEFAULT_RECIPES, metavar="FILE",
        help="Path to the recipes JSON file (default: bundled docs/ file)"
    )
    parser.add_argument(
        "--list", "-l", action="store_true",
        help="List available recipes / styles and exit"
    )
    parser.add_argument(
        "--recipe", "-r", metavar="NAME_OR_INDEX",
        help="Recipe name (substring) or index — Creative Look cameras only"
    )
    parser.add_argument(
        "--look", metavar="ABBR",
        help="Bare Creative Look style code (e.g. FL, ST, VV2) — CL cameras only"
    )
    parser.add_argument(
        "--style", metavar="NAME",
        help="Creative Style name (e.g. VIVID, NEUTRAL) — CS cameras only"
    )
    parser.add_argument(
        "--disable-pp", action="store_true",
        help="Set Picture Profile to OFF before applying Creative Style"
    )
    parser.add_argument(
        "--demo", action="store_true",
        help="Individual-setter walkthrough (Creative Look cameras only)"
    )
    args = parser.parse_args()

    if args.list and not args.recipe and not args.look and not args.style and not args.demo:
        # Offline listing
        try:
            recipes = _load_recipes(args.json)
            _print_recipe_list(recipes)
        except FileNotFoundError as exc:
            print(exc)
        print()
        _list_creative_styles()
        return

    recipes: list[dict] = []
    if args.recipe:
        recipes = _load_recipes(args.json)

    if not args.recipe and not args.look and not args.style and not args.demo:
        try:
            recipes = _load_recipes(args.json)
            _print_recipe_list(recipes)
        except FileNotFoundError as exc:
            print(exc)
        print()
        _list_creative_styles()
        return

    with SonyCamera() as camera:
        camera.authenticate()
        camera.set_mode("still")

        system = camera.detect_look_system()
        print(f"Connected. Camera image system: {system}")

        if args.demo:
            if system != "creative_look":
                print("ERROR: --demo requires a Creative Look camera.")
                return
            demo_individual_cl_setters(camera)

        elif args.look:
            if system != "creative_look":
                print(
                    f"ERROR: your camera uses {system}, not Creative Look.\n"
                    "Use --style NAME instead (e.g. --style VIVID)."
                )
                return
            abbr = args.look.upper()
            try:
                code = CreativeLookName[abbr]
            except KeyError:
                valid = [m.name for m in CreativeLookName if not m.name.startswith("CUSTOM")]
                print(f"Unknown look abbreviation: {abbr!r}. Valid: {valid}")
                return
            log.info("Setting Creative Look → %s (0x%04X)", abbr, code)
            camera.set_creative_look(code)
            print(f"Creative Look set to {abbr}.")

        elif args.style:
            if system == "creative_look":
                print(
                    "NOTE: your camera supports Creative Look (newer system).\n"
                    "      Use --look ABBR or --recipe NAME for full recipe support.\n"
                    "      Proceeding with Creative Style selection anyway."
                )
            apply_cs_style(camera, args.style, args.disable_pp)

        elif args.recipe:
            try:
                recipe = _find_recipe(recipes, args.recipe)
            except ValueError as exc:
                print(f"Error: {exc}")
                return

            if system == "creative_look":
                apply_cl_recipe(camera, recipe)
            elif system == "creative_style":
                print(
                    "NOTE: this camera uses Creative Style (older system).\n"
                    "      Full recipe tuning is not available remotely.\n"
                    "      Selecting the nearest base style and printing manual adjustments."
                )
                apply_cs_from_recipe(camera, recipe, args.disable_pp)
            else:
                print(f"ERROR: could not detect image system (got: {system!r}).")


if __name__ == "__main__":
    main()

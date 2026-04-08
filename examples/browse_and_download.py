"""
Browse the camera's memory card and download content via the SDIO content API.

Uses :meth:`~pysonycam.SonyCamera.get_content_info_list` to enumerate files,
then optionally downloads selected items with
:meth:`~pysonycam.SonyCamera.get_content_data` (full file) or
:meth:`~pysonycam.SonyCamera.get_content_compressed_data` (proxy/preview), and
can delete files with :meth:`~pysonycam.SonyCamera.delete_content`.

Usage
-----
    python examples/browse_and_download.py [options]

    Options:
        --output DIR        Directory to save downloaded files (default: downloads/)
        --list              List content only; do not download
        --filter EXT        Only show/download files with this extension, e.g. JPG
        --max N             Maximum number of items to list (default: 50)
        --index N           Download only the item at list index N (0-based)
        --all               Download all listed items
        --proxy             Download proxy/compressed preview instead of full file
        --delete            Delete each item from the card after a successful download
        --start N           Start listing from content index N (default: 0)
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from pysonycam import SonyCamera
from pysonycam.exceptions import SonyCameraError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# PTP object format codes for display
_FORMAT_NAMES: dict[int, str] = {
    0x3000: "Undefined",
    0x3001: "Folder",
    0x3800: "Undefined Image",
    0x3801: "EXIF/JPEG",
    0x3802: "TIFF/EP",
    0x380D: "BMP",
    0x380E: "GIF",
    0x380F: "JFIF",
    0xB982: "MP4",
    0xB103: "AVI",
    0xB301: "WMV",
    0xB101: "MP3",
    0xB905: "ARW",  # Sony RAW
}


def _fmt_size(n: int) -> str:
    if n >= 1_073_741_824:
        return f"{n / 1_073_741_824:.1f} GB"
    if n >= 1_048_576:
        return f"{n / 1_048_576:.1f} MB"
    if n >= 1_024:
        return f"{n / 1_024:.1f} KB"
    return f"{n} B"


def _fmt_code(code: int) -> str:
    return _FORMAT_NAMES.get(code, f"0x{code:04X}")


def _safe_stem(file_name: str) -> str:
    """Return a filesystem-safe version of the file name."""
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in file_name)


def print_table(items: list[dict], start_offset: int = 0) -> None:
    print(f"\n{'#':<5} {'File name':<28} {'Format':<12} {'Size':<12} {'Date/Time'}")
    print("-" * 78)
    for i, item in enumerate(items):
        idx = i + start_offset
        name = item.get("file_name", "")
        fmt = _fmt_code(item.get("format_code", 0))
        size = _fmt_size(item.get("size", 0))
        dt = item.get("date_time", "")
        print(f"{idx:<5} {name:<28} {fmt:<12} {size:<12} {dt}")
    print(f"\n{len(items)} item(s) listed.")


def download_item(
    camera: SonyCamera,
    item: dict,
    output_dir: Path,
    proxy: bool = False,
    delete_after: bool = False,
) -> bool:
    content_id = item["content_id"]
    file_name = _safe_stem(item.get("file_name", f"content_{content_id}"))
    if proxy:
        file_name = Path(file_name).stem + "_proxy.jpg"

    dest = output_dir / file_name
    log.info("Downloading %s → %s …", item.get("file_name", content_id), dest)
    try:
        data = (
            camera.get_content_compressed_data(content_id)
            if proxy
            else camera.get_content_data(content_id)
        )
    except SonyCameraError as exc:
        log.error("Download failed: %s", exc)
        return False

    dest.write_bytes(data)
    log.info("Saved %s (%s)", dest.name, _fmt_size(len(data)))

    if delete_after:
        try:
            camera.delete_content(content_id)
            log.info("Deleted content ID 0x%08X from card.", content_id)
        except SonyCameraError as exc:
            log.warning("Delete failed: %s", exc)

    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Browse and download camera content")
    parser.add_argument("--output", default="downloads/", metavar="DIR")
    parser.add_argument("--list", action="store_true", help="List only; no download")
    parser.add_argument("--filter", metavar="EXT", help="File extension filter, e.g. JPG")
    parser.add_argument("--max", type=int, default=50, metavar="N")
    parser.add_argument("--start", type=int, default=0, metavar="N")
    parser.add_argument("--index", type=int, default=None, metavar="N")
    parser.add_argument("--all", action="store_true", help="Download all listed items")
    parser.add_argument("--proxy", action="store_true", help="Download proxy instead of full file")
    parser.add_argument("--delete", action="store_true", help="Delete after download")
    args = parser.parse_args()

    output_dir = Path(args.output)

    with SonyCamera() as camera:
        camera.authenticate()
        log.info("Authenticated. Fetching content list…")

        items: list[dict] = camera.get_content_info_list(
            start_index=args.start,
            max_count=args.max,
        )

        if not items:
            print("No content found on the camera card.")
            return

        # Apply extension filter
        if args.filter:
            ext = args.filter.upper().lstrip(".")
            items = [it for it in items if it.get("file_name", "").upper().endswith(f".{ext}")]
            log.info("Filter .%s → %d item(s)", ext, len(items))

        print_table(items, start_offset=args.start)

        if args.list:
            return

        # Determine which items to download
        if args.index is not None:
            local_idx = args.index - args.start
            if local_idx < 0 or local_idx >= len(items):
                print(f"Index {args.index} not in current range ({args.start}–{args.start + len(items) - 1}).")
                return
            to_download = [items[local_idx]]
        elif args.all:
            to_download = items
        else:
            print("\nUse --all to download all items, --index N to download a specific item,")
            print("or --list to list without downloading.")
            return

        output_dir.mkdir(parents=True, exist_ok=True)
        ok = failed = 0
        for item in to_download:
            if download_item(camera, item, output_dir, proxy=args.proxy, delete_after=args.delete):
                ok += 1
            else:
                failed += 1

        print(f"\nDone. {ok} downloaded, {failed} failed.")


if __name__ == "__main__":
    main()

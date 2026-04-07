"""
List and download MP4 video files from the camera's SD card.

Uses multiple strategies to access camera storage:
  1. Bare PTP session (no Sony auth) — works like the Linux SDK examples
  2. SDIO Content Transfer session (function_mode=1)
  3. Authenticated session with SetContentsTransferMode

Enumerates all .MP4 files, sorts newest-first, and lets the user
choose which ones to download.

Usage
-----
    python examples/download_videos.py [options]

    Options:
        --output DIR     Output directory (default: downloaded_videos/)
        --list           List videos and exit (no download)
        --index N        Download video at index N (0 = newest)
        --all            Download all videos
        --latest         Download the latest (newest) video only
"""

import argparse
import struct
import time
import logging
from pathlib import Path

from pysonycam.constants import (
    PTPOpCode,
    ResponseCode,
    SDIOOpCode,
)
from pysonycam.ptp import PTPTransport

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# PTP object format codes
FORMAT_FOLDER = 0x3001
FORMAT_MP4 = 0xB982


# ---------------------------------------------------------------------------
# PTP helpers (work directly on PTPTransport, no SonyCamera wrapper)
# ---------------------------------------------------------------------------

def ptp_get_storage_ids(transport: PTPTransport) -> list[int]:
    """Return storage IDs from the camera."""
    resp, data = transport.receive(PTPOpCode.GET_STORAGE_ID)
    if resp.code != ResponseCode.OK or len(data) < 4:
        return []
    count = struct.unpack_from("<I", data, 0)[0]
    if count == 0:
        return []
    return list(struct.unpack_from(f"<{count}I", data, 4))


def ptp_get_object_handles(
    transport: PTPTransport,
    storage_id: int = 0xFFFFFFFF,
    format_code: int = 0x00000000,
    parent_handle: int = 0xFFFFFFFF,
) -> list[int]:
    """Return object handles matching the given filter."""
    resp, data = transport.receive(
        PTPOpCode.GET_OBJECT_HANDLES,
        [storage_id, format_code, parent_handle],
    )
    if resp.code != ResponseCode.OK or len(data) < 4:
        return []
    count = struct.unpack_from("<I", data, 0)[0]
    if count == 0:
        return []
    return list(struct.unpack_from(f"<{count}I", data, 4))


def ptp_get_object_info(transport: PTPTransport, handle: int) -> bytes:
    """Get raw ObjectInfo data for a handle."""
    resp, data = transport.receive(PTPOpCode.GET_OBJECT_INFO, [handle])
    return data


def ptp_get_object(transport: PTPTransport, handle: int) -> bytes:
    """Download an object (file) by handle."""
    resp, data = transport.receive(PTPOpCode.GET_OBJECT, [handle])
    if resp.code != ResponseCode.OK:
        raise RuntimeError(f"GetObject failed: 0x{resp.code:04X}")
    return data


def ptp_open_session(transport: PTPTransport, session_id: int = 1) -> bool:
    """Open a standard PTP session."""
    resp = transport.send(PTPOpCode.OPEN_SESSION, [session_id])
    return resp.code == ResponseCode.OK


def ptp_close_session(transport: PTPTransport) -> None:
    """Close the PTP session."""
    try:
        transport.send(PTPOpCode.CLOSE_SESSION)
    except Exception:
        pass


def parse_object_info(data: bytes) -> dict:
    """Parse a PTP ObjectInfo dataset into a dict."""
    if len(data) < 53:
        return {}
    storage_id, obj_format, protect, obj_size = struct.unpack_from("<IHHI", data, 0)

    # Parse filename at offset 52 (PTP String: leading byte = char count incl. null)
    offset = 52
    filename = ""
    if offset < len(data):
        name_len = data[offset]
        offset += 1
        if name_len > 0 and offset + name_len * 2 <= len(data):
            filename = data[offset:offset + (name_len - 1) * 2].decode(
                "utf-16-le", errors="replace"
            )
            offset += name_len * 2

    # Parse capture date (next PTP String after filename)
    capture_date = ""
    if offset < len(data):
        date_len = data[offset]
        offset += 1
        if date_len > 0 and offset + date_len * 2 <= len(data):
            capture_date = data[offset:offset + (date_len - 1) * 2].decode(
                "utf-16-le", errors="replace"
            )
            offset += date_len * 2

    # Parse modification date
    mod_date = ""
    if offset < len(data):
        date_len = data[offset]
        offset += 1
        if date_len > 0 and offset + date_len * 2 <= len(data):
            mod_date = data[offset:offset + (date_len - 1) * 2].decode(
                "utf-16-le", errors="replace"
            )

    return {
        "storage_id": storage_id,
        "format": obj_format,
        "size": obj_size,
        "filename": filename,
        "capture_date": capture_date,
        "modification_date": mod_date,
    }


def format_size(size_bytes: int) -> str:
    """Human-readable file size."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


# ---------------------------------------------------------------------------
# Video enumeration
# ---------------------------------------------------------------------------

def enumerate_mp4_files(transport: PTPTransport) -> list[dict]:
    """Enumerate all MP4 files on the camera.

    Tries hierarchical folder traversal first (like the SDK example),
    then falls back to flat queries.

    Returns a list of dicts sorted newest-first.
    """
    storage_ids = ptp_get_storage_ids(transport)
    if not storage_ids:
        log.warning("No storage IDs found — trying defaults")
        storage_ids = [0x00010001, 0x00010000]

    log.info("Storage IDs: %s", [f"0x{s:08X}" for s in storage_ids])

    all_videos: list[dict] = []

    for sid in storage_ids:
        mp4_handles: list[int] = []

        # Strategy 1: SDK approach — get root folders, then MP4s in each folder
        folders = ptp_get_object_handles(transport, sid, FORMAT_FOLDER, 0xFFFFFFFF)
        log.info("Storage 0x%08X: %d root folder(s)", sid, len(folders))

        for fh in folders:
            # MP4 files in this folder
            handles = ptp_get_object_handles(transport, sid, FORMAT_MP4, fh)
            if handles:
                log.info("  Folder 0x%08X: %d MP4(s)", fh, len(handles))
                mp4_handles.extend(handles)

            # Also recurse into subfolders
            subfolders = ptp_get_object_handles(transport, sid, FORMAT_FOLDER, fh)
            for sf in subfolders:
                sub_handles = ptp_get_object_handles(transport, sid, FORMAT_MP4, sf)
                if sub_handles:
                    log.info("  Subfolder 0x%08X: %d MP4(s)", sf, len(sub_handles))
                    mp4_handles.extend(sub_handles)

        # Strategy 2: flat MP4 query across all parents
        if not mp4_handles:
            log.info("Trying flat MP4 query (parent=0x00000000)...")
            mp4_handles = ptp_get_object_handles(transport, sid, FORMAT_MP4, 0x00000000)

        # Strategy 3: all objects, filter by format/extension
        if not mp4_handles:
            log.info("Trying unfiltered query...")
            all_handles = ptp_get_object_handles(transport, sid, 0, 0xFFFFFFFF)
            log.info("  Total objects: %d", len(all_handles))
            for h in all_handles:
                try:
                    info_data = ptp_get_object_info(transport, h)
                    info = parse_object_info(info_data)
                    if info.get("filename", "").lower().endswith(".mp4") or info.get("format") == FORMAT_MP4:
                        mp4_handles.append(h)
                except Exception:
                    continue

        log.info("Storage 0x%08X: %d MP4 file(s) found", sid, len(mp4_handles))

        # Get detailed info for each MP4
        for h in mp4_handles:
            try:
                info_data = ptp_get_object_info(transport, h)
                info = parse_object_info(info_data)
                info["handle"] = h
                all_videos.append(info)
            except Exception as e:
                log.warning("Could not get info for handle 0x%08X: %s", h, e)

    # Sort newest-first by capture date, then by handle (higher = newer)
    all_videos.sort(
        key=lambda v: (v.get("capture_date", ""), v.get("handle", 0)),
        reverse=True,
    )
    return all_videos


def print_video_list(videos: list[dict]) -> None:
    """Print a formatted table of videos."""
    if not videos:
        print("No MP4 video files found on the camera.")
        return

    print(f"\n{'Idx':>4}  {'Filename':<20}  {'Size':>10}  {'Date':<20}")
    print(f"{'---':>4}  {'--------':<20}  {'----':>10}  {'----':<20}")
    for i, v in enumerate(videos):
        name = v.get("filename", "???")
        size = format_size(v.get("size", 0))
        date = v.get("capture_date", "") or v.get("modification_date", "")
        print(f"{i:>4}  {name:<20}  {size:>10}  {date:<20}")
    print()


def download_video(
    transport: PTPTransport, video: dict, output_dir: Path
) -> Path | None:
    """Download a single video file."""
    handle = video["handle"]
    filename = video.get("filename") or f"video_{handle:08X}.mp4"
    file_size = video.get("size", 0)

    out_path = output_dir / filename
    if out_path.exists():
        stem = out_path.stem
        out_path = output_dir / f"{stem}_{handle:08X}.mp4"

    print(f"  Downloading {filename} ({format_size(file_size)})...")

    try:
        data = ptp_get_object(transport, handle)
        out_path.write_bytes(data)
        print(f"  Saved to {out_path} ({len(data):,} bytes)")
        return out_path
    except Exception as e:
        log.error("Download failed for %s: %s", filename, e)
        return None


def interactive_select(videos: list[dict]) -> list[int]:
    """Prompt the user to select videos to download."""
    print("Enter video indices to download (comma-separated), or:")
    print("  'all'    — download everything")
    print("  'latest' — download index 0 (newest)")
    print("  'q'      — quit without downloading")
    print()

    while True:
        try:
            choice = input("Selection> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return []

        if choice in ("q", "quit", "exit"):
            return []
        if choice == "all":
            return list(range(len(videos)))
        if choice in ("latest", "0"):
            return [0]

        indices = []
        try:
            for part in choice.split(","):
                part = part.strip()
                if "-" in part:
                    lo, hi = part.split("-", 1)
                    lo, hi = int(lo), int(hi)
                    indices.extend(range(lo, hi + 1))
                else:
                    indices.append(int(part))
        except ValueError:
            print("Invalid input. Enter numbers like: 0,1,2 or 0-5 or 'all'")
            continue

        bad = [i for i in indices if i < 0 or i >= len(videos)]
        if bad:
            print(f"Invalid index(es): {bad}. Valid range: 0–{len(videos) - 1}")
            continue

        return indices


# ---------------------------------------------------------------------------
# Connection strategies
# ---------------------------------------------------------------------------

def try_bare_ptp(transport: PTPTransport) -> list[dict]:
    """Strategy 1: Bare PTP session without Sony SDIO authentication.

    The Linux SDK examples access files this way — standard PTP OpenSession
    followed by GetObjectHandles/GetObject, no vendor-specific auth.
    """
    print("Strategy 1: Bare PTP session (no Sony auth)...")
    transport.connect()
    if not ptp_open_session(transport):
        print("  OpenSession failed")
        ptp_close_session(transport)
        transport.disconnect()
        return []

    print("  Session opened, querying storage...")
    storage_ids = ptp_get_storage_ids(transport)
    print(f"  Storage IDs: {[f'0x{s:08X}' for s in storage_ids]}")

    # Quick check: can we see any objects?
    found_objects = False
    for sid in (storage_ids or [0x00010001]):
        handles = ptp_get_object_handles(transport, sid, 0, 0xFFFFFFFF)
        if handles:
            print(f"  Storage 0x{sid:08X}: {len(handles)} object(s) found!")
            found_objects = True
            break
        else:
            print(f"  Storage 0x{sid:08X}: 0 objects")

    if found_objects:
        videos = enumerate_mp4_files(transport)
        return videos

    # No objects found — close and let caller try next strategy
    ptp_close_session(transport)
    transport.disconnect()
    return []


def try_sdio_content_transfer(transport: PTPTransport) -> list[dict]:
    """Strategy 2: SDIO session with function_mode=1 (Content Transfer)."""
    print("\nStrategy 2: SDIO Content Transfer session...")
    transport.connect()

    # SDIO_OpenSession with function_mode=1 (Content Transfer)
    transport._session_id = 0
    transport._transaction_id = 0
    try:
        resp = transport.send(SDIOOpCode.SDIO_OPEN_SESSION, [1, 1])
        if resp.code != ResponseCode.OK:
            print(f"  SDIO_OpenSession(CT) returned 0x{resp.code:04X}")
            transport.disconnect()
            return []
        print("  SDIO session opened in Content Transfer mode")
    except Exception as e:
        print(f"  SDIO_OpenSession(CT) failed: {e}")
        transport.clear_halt()
        transport.disconnect()
        return []

    storage_ids = ptp_get_storage_ids(transport)
    print(f"  Storage IDs: {[f'0x{s:08X}' for s in storage_ids]}")

    found_objects = False
    for sid in (storage_ids or [0x00010001]):
        handles = ptp_get_object_handles(transport, sid, 0, 0xFFFFFFFF)
        if handles:
            print(f"  Storage 0x{sid:08X}: {len(handles)} object(s) found!")
            found_objects = True
            break
        else:
            print(f"  Storage 0x{sid:08X}: 0 objects")

    if found_objects:
        videos = enumerate_mp4_files(transport)
        return videos

    ptp_close_session(transport)
    transport.disconnect()
    return []


def try_authenticated_with_transfer_mode(transport: PTPTransport) -> list[dict]:
    """Strategy 3: Standard auth + SetContentsTransferMode (0x9212)."""
    from pysonycam import SonyCamera
    from pysonycam.constants import DeviceProperty

    print("\nStrategy 3: Authenticated session + SetContentsTransferMode...")

    camera = SonyCamera()
    try:
        camera.connect()
        camera.authenticate()
        print("  Authenticated OK")
    except Exception as e:
        print(f"  Auth failed: {e}")
        try:
            camera.disconnect()
        except Exception:
            pass
        return []

    # Try SetContentsTransferMode with the 3 params from the v3-Windows SDK
    try:
        resp = camera._transport.send(
            SDIOOpCode.SET_CONTENTS_TRANSFER_MODE,
            [0x02, 0x01, 0x00],
        )
        print(f"  SetContentsTransferMode resp=0x{resp.code:04X}")
        time.sleep(2.0)
    except Exception as e:
        print(f"  SetContentsTransferMode failed: {e}")
        camera._transport.clear_halt()

    # Check storage
    storage_ids = camera._get_storage_ids()
    print(f"  Storage IDs: {[f'0x{s:08X}' for s in storage_ids]}")

    found_objects = False
    for sid in (storage_ids or [0x00010001]):
        handles = camera._get_object_handles(sid, 0, 0xFFFFFFFF)
        if handles:
            print(f"  Storage 0x{sid:08X}: {len(handles)} object(s) found!")
            found_objects = True
            break
        else:
            print(f"  Storage 0x{sid:08X}: 0 objects")

    if found_objects:
        videos = enumerate_mp4_files(camera._transport)
        camera.disconnect()
        return videos

    camera.disconnect()
    return []


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="List and download MP4 videos from a Sony camera."
    )
    parser.add_argument(
        "--output", "-o", default="downloaded_videos",
        help="Output directory (default: downloaded_videos/)",
    )
    parser.add_argument(
        "--list", "-l", action="store_true",
        help="List videos and exit without downloading.",
    )
    parser.add_argument(
        "--index", "-i", type=int, default=None,
        help="Download the video at this index (0 = newest).",
    )
    parser.add_argument(
        "--all", "-a", action="store_true",
        help="Download all videos.",
    )
    parser.add_argument(
        "--latest", action="store_true",
        help="Download the latest (newest) video only.",
    )
    args = parser.parse_args()
    output_dir = Path(args.output)

    transport = PTPTransport(timeout_ms=10_000)

    # Try each strategy in order until one finds files
    videos = []
    active_transport = None

    # Strategy 1: Bare PTP (like the Linux SDK)
    videos = try_bare_ptp(transport)
    if videos:
        active_transport = transport
    else:
        # Strategy 2: SDIO Content Transfer session
        transport2 = PTPTransport(timeout_ms=10_000)
        videos = try_sdio_content_transfer(transport2)
        if videos:
            active_transport = transport2
        else:
            # Strategy 3: Authenticated + SetContentsTransferMode
            videos = try_authenticated_with_transfer_mode(transport)
            if videos:
                active_transport = transport

    if not videos:
        print("\n" + "=" * 60)
        print("No video files found with any strategy.")
        print("=" * 60)
        print("\nPossible causes:")
        print("  1. No MP4 files on the camera's SD card")
        print("  2. Camera USB mode may need to be set to 'Mass Storage'")
        print("     or 'MTP' instead of 'PC Remote'")
        print("  3. The USB driver may not support file browsing")
        print("     (try reinstalling with the SDK driver from Driver/)")
        return

    # Show results
    print(f"\nFound {len(videos)} video(s).")
    print_video_list(videos)

    if args.list:
        if active_transport:
            ptp_close_session(active_transport)
            active_transport.disconnect()
        return

    # Select videos to download
    if args.all:
        selected = list(range(len(videos)))
    elif args.latest:
        selected = [0]
    elif args.index is not None:
        if args.index < 0 or args.index >= len(videos):
            print(f"Index {args.index} out of range (0–{len(videos) - 1}).")
            return
        selected = [args.index]
    else:
        selected = interactive_select(videos)

    if not selected:
        print("No videos selected.")
    else:
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"\nDownloading {len(selected)} video(s) to {output_dir}/\n")

        # Use longer timeout for large file downloads
        if active_transport:
            active_transport._timeout_ms = 120_000

        for idx in selected:
            download_video(active_transport or transport, videos[idx], output_dir)
            print()

        print("Done.")

    # Cleanup
    if active_transport:
        ptp_close_session(active_transport)
        active_transport.disconnect()


if __name__ == "__main__":
    main()

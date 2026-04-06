# HFR Video Transfer Investigation

## Status: STBY SOLVED — TRANSFER FIX IMPLEMENTED (needs hardware test)

## Objective
Remotely trigger HFR (High Frame Rate / super slow motion) recording on a Sony camera and automatically download the resulting MP4 clip via USB PTP, returning the camera to HFR-ready state for the next recording cycle.

## What Works
- **Connecting & authenticating** in HFR mode (camera dial set to HFR)
- **Camera is already in MOVIE_REC (0x03)** operating mode when HFR is selected via dial — no need to call `set_mode("movie")`
- **Triggering recording via `MOVIE_REC` control**: `control_device(MOVIE_REC, 0x0002)` then `control_device(MOVIE_REC, 0x0001)` successfully triggers the HFR capture when camera is in STBY
- **Camera processes the HFR clip** after trigger (~70-90 seconds for 960fps)
- **Entering STBY via PTP**: `HFR_STANDBY` (0xD2D5) Down+Up enters STBY buffering

## Transfer Mode — Root Cause & Fix

### Root Cause (PIPE errors)
The PIPE (-9) errors on `SDIOSetContentsTransferMode` (0x9212) were caused by
connecting in the **wrong PTP session mode**. Standard PTP `OpenSession` (0x1002)
connects in "Remote Control Mode" which does NOT support content transfer commands.

The v3 protocol requires `SDIO_OpenSession` (0x9210) with a **Function Mode**
parameter to enable transfer:
- `0x00` = Remote Control Mode (standard, no transfer)
- `0x01` = Content Transfer Mode (transfer only, no remote control)
- `0x02` = Remote Control with Transfer Mode (both, model-dependent)

The C++ SDK examples use WPD (Windows Portable Devices) which handles session
management internally. On raw USB (libusb), we must use `SDIO_OpenSession` explicitly.

### v3 Spec Clarifications (from reference pages 0124-0127)
- `SDIOSetContentsTransferMode` (0x9212): **Data: None, Data Direction: N/A**
  - Must use `send()` (no data phase), NOT `receive()`
  - The C++ SDK's `PTP_NEXTPHASE_READ_DATA` is a WPD escape API artifact
- `SDIO_OpenSession` (0x9210): **Data: None**, takes SessionID and FunctionMode params
- **Cannot switch modes while connected** (v3 spec page 0055): must disconnect and
  reconnect with the desired FunctionMode

### Content Transfer Mode Flow (v3 spec page 0054)
1. PTP Connected (USB layer)
2. `SDIO_OpenSession(SessionID=1, FunctionMode=1)` — replaces standard OpenSession
3. Authentication (SDIOConnect phases 1-3 + GetExtDeviceInfo)
4. `SDIOSetContentsTransferMode(SelectOnRemote=0x02, On=0x01, None=0x00)` — via send()
5. Camera fires StoreAdded event
6. Check Content Transfer Enable Status (property 0xD295 = 0x01)
7. Browse via GetObjectHandles + download via GetObject
8. `SDIOSetContentsTransferMode(Off)` when done
9. Camera fires StoreRemoved event, 0xD295 = 0x00

### Fix Implemented
The HFR example now performs a **session reconnection cycle** for downloads:
1. Close current Remote Control session
2. Open SDIO session with FunctionMode=1 (Content Transfer Mode)
3. Authenticate
4. Enable content transfer (0x9212 via send)
5. Browse SD card and download MP4
6. Disable content transfer
7. Close SDIO session
8. Re-open standard PTP session (Remote Control Mode)
9. Re-authenticate and restore HFR mode

### Processing Detection Fix
The previous `wait_for_processing()` only checked for `MOVIE_STOPPED` (0x00),
but in HFR mode the status may never be exactly 0x00 during the processing
phase. Fixed to:
- Log actual movie status values for diagnostics
- Accept both `MOVIE_STOPPED` (0x00) and `MOVIE_UNABLE` (0x02) as completion
- Detect status changes as a completion signal
- For timeouts >= 90s, assume processing complete (HFR typically finishes in 70-80s)

## PTP Response Codes Encountered
| Code | Meaning | Context |
|------|---------|---------|
| 0x2019 | Unknown / rejected | S1_BUTTON in HFR mode |
| 0x201E | Session already open | OpenSession after reset |
| PIPE (-9) | Endpoint stalled | SET_CONTENTS_TRANSFER_MODE after HFR |

## Key Technical Details

### HFR Exposure Modes (added to ExposureMode enum)
- `HFR_P = 0x00088080` — HFR Program Auto
- `HFR_A = 0x00088081` — HFR Aperture Priority
- `HFR_S = 0x00088082` — HFR Shutter Priority
- `HFR_M = 0x00088083` — HFR Manual

### HFR Recording Flow (physical camera)
1. Set camera dial to HFR mode
2. Configure frame rate (240/480/960/1000fps), trigger timing (Start/End/End Half), quality in camera menu
3. Press **center button** → camera enters STBY (high-fps buffering begins)
4. Press **REC button** or **shutter button** → triggers recording based on timing mode
5. Camera processes clip (~70-90s at 960fps)
6. Clip saved to SD card as MP4

### Movie Recording Control
- `MOVIE_REC` (0xD2C8): `0x0002` = press/start, `0x0001` = release/stop
- Movie status values: `0x00` = Stopped, `0x01` = Recording, `0x02` = Unable to Record

### Contents Transfer Mode (from C++ SDK)
- `SDIOSetContentsTransferMode` (0x9212) takes 3 params:
  - Param 1: `0x00000002` (SELECT_ON_REMOTE_DEVICE)
  - Param 2: `0x00000001` (MODE_ON) or `0x00000000` (MODE_OFF)
  - Param 3: `0x00000000` (ADD_INFO_NONE)
- Works fine for stills (JPEG/RAW via `GetObject` with `SHOT_OBJECT_HANDLE`)
- **Has NOT been tested for video download in non-HFR movie modes**
- MP4 object format code: `0xB982`
- Storage ID: `0x00010001`

### Video vs. Still Transfer Differences
- Stills use `SHOT_OBJECT_HANDLE` (0xFFFFC001) for immediate transfer — no mode switch needed
- Videos are saved to SD card only — requires Contents Transfer Mode to browse/download
- The C++ SDK example code (`mp4filetransfer`) uses the same `SDIOSetContentsTransferMode` + `GetObjectHandles` + `GetObject` flow

## Resolved Questions
6. ~~Is there a PTP command equivalent to the center button for entering HFR STBY?~~
   **YES — `HFR_STANDBY` (0xD2D5)**, documented on page 92 of Camera Control PTP 2 Reference.
7. ~~Is `SDIOSetContentsTransferMode` supported in Remote Control Mode?~~
   **NO.** The v3 spec requires `SDIO_OpenSession(FunctionMode=1)` to enter Content Transfer Mode.
   Standard PTP OpenSession only supports Remote Control Mode.
8. ~~send() or receive() for 0x9212?~~
   **send().** V3 spec page 0126 clearly states `Data: None, Data Direction: N/A`. The C++ SDK's
   `PTP_NEXTPHASE_READ_DATA` is a WPD escape API artifact, not a PTP protocol requirement.

## Remaining Questions
1. Does SDIO_OpenSession(FunctionMode=1) work on the user's specific camera model?
2. Does the session reconnection cycle complete without errors?
3. Are GetObjectHandles / GetObject supported in Content Transfer Mode?
4. Which cameras support FunctionMode=2 ("Remote Control with Transfer")? Check
   `X_PTP_ContentsTransferSupport` in DigitalImagingDesc.xml — if "Enable", mode 2 is available.
5. Can SDIO_GetContentInfoList + SDIO_GetContentData be used as an alternative
   to GetObjectHandles + GetObject in transfer mode?

## Files Modified
- `pysonycam/constants.py` — Added HFR_P/A/S/M to ExposureMode, HFR_STANDBY (0xD2D5),
  HFR_RECORDING_CANCEL (0xD2D6), SDIO_OPEN_SESSION (0x9210), and all control codes from SDK
- `pysonycam/ptp.py` — Added `clear_halt()` and `reset_device()` methods
- `pysonycam/camera.py` — Added USB reset retry to `connect()`, added `sdio_open_session()` method
- `examples/hfr_slow_motion.py` — Full unattended HFR loop with session reconnection for
  content transfer, improved processing detection, HFR mode restoration after download

## Code Location
- Example script: `examples/hfr_slow_motion.py`
- Transport layer: `pysonycam/ptp.py` (clear_halt, reset_device)
- Camera connection retry: `pysonycam/camera.py` (connect method)
- C++ SDK reference for transfer: `CameraRemoteCommadExamples/example-v3-windows/CameraControlPTP/CaptureDlg.cpp` (mp4filetransfer function, line ~1764)

# Missing SDK Features

**Scope:** Sony Camera Remote Command SDK v3 reference (consumer focus; v2 partial).  
**Methodology:** Cross-reference `constants.py` + `camera.py` against SDK pages 59–750.  
**Excluded:** PTZ/PTZF, broadcast paint/look, FTP server management, firmware update.

---

## 1. Missing Operations (SDIO/PTP)

Source: SDK pages 57–120; `SDIOOpCode` and `PTPOpCode` enums in `constants.py`.

### Standard PTP

Five opcodes are absent from `PTPOpCode` entirely; three others are present as enum values but have
no public `SonyCamera` method.

| Operation | Opcode | SDK page | Status | Notes |
|---|---|---|---|---|
| GetDeviceInfo | 0x1001 | page_0040 | Opcode defined; no public method | Device capabilities info |
| GetStorageInfo | 0x1005 | ~page_0050 | Opcode defined; no public method | Storage capacity/type |
| GetNumObjects | 0x1006 | ~page_0052 | Opcode defined; no public method | Count objects in a container |
| GetThumb | 0x100A | ~page_0054 | Not in constants, no method | Thumbnail download |
| SendObject | 0x100D | ~page_0055 | Not in constants, no method | Upload object to camera |
| GetPartialObject | 0x101B | ~page_0056 | Not in constants, no method | Resume-support partial download |
| GetObjectPropValue | 0x9803 | ~page_0057 | Not in constants, no method | MTP object property read |
| GetObjectPropList | 0x9805 | ~page_0058 | Not in constants, no method | MTP bulk object property read |

### SDIO — High Priority

| Operation | Opcode | SDK page | Notes |
|---|---|---|---|
| SDIO_GetExtDeviceProp | 0x9251 | page_0019 | Single-property query (supplement to GetAll) |
| SDIO_GetContentInfoList | 0x923C | ~page_0100–0107 | Browse all media on card with metadata |
| SDIO_GetContentData | 0x923D | ~page_0107 | Download image/video by content ID |
| SDIO_DeleteContent | 0x9250 | ~page_0110 | Delete content by content ID |

### SDIO — Medium Priority

| Operation | Opcode | SDK page | Notes |
|---|---|---|---|
| SDIO_GetContentCompressedData | 0x923E | ~page_0108 | Proxy/compressed preview download |
| SDIO_UploadData | 0x921A | ~page_0080 | Upload data to camera temp storage |
| SDIO_ControlUploadData | 0x921B | ~page_0081 | Start/stop/cancel upload |
| SDIO_DownloadData | 0x921D | ~page_0082 | Retrieve files from camera |
| SDIO_GetLensInformation | 0x9223 | ~page_0085 | Attached lens metadata |
| SDIO_OperationResultsSupported | 0x922F | ~page_0090 | Capability query for async results |
| SDIO_GetVendorCodeVersion | 0x9216 | ~page_0072 | SDK version info |

### SDIO — Low Priority / Professional

**FTP server management:** `SetFTPSettingFilePassword`, `GetFTPJobList`, `ControlFTPJobList`,
`GetFTPSettingList`, `SetFTPSettingList`

**Streaming:** `GetStreamSettingList`, `SetStreamSettingList`

**General settings:** `ControlGeneralSettingFile`, `GetControlGeneralSettingResultFile`,
`GetLicenseInfoList`

**OSD/info:** `GetOSDImage`, `GetRestrictionInfo`, `GetDeviceDescriptionFile`,
`GetDisplayFTPResult`

**Date/time:** `GetCapturedDateList`, `GetAreaTimeZoneSetting`, `SetAreaTimeZoneSetting`

**Firmware (risky):** `RequestFirmwareUpdateCheck`, `SetFirmwareUpdateMode`,
`UploadPartialData`, `GetFirmwareUpdateInfo`

**PTZ (not consumer):** `ControlPTZF`, `SetPresetPTZF`

**Misc:** `ExecuteEFraming`, `GetPresetInfoList`, `GetDisplayStringList`

---

## 2. Missing Device Properties

Source: SDK reference pages 59–84 (index), ~120–500 (detail per property).

> **Note on naming conflicts:** Three codes are already present in `constants.py` under different
> names — `VIEW` (0xD231, SDK: *LiveView Display Effect*), `LIVEVIEW_MODE` (0xD26A, SDK: *Live View
> Image Quality*), and `MOVIE_QUALITY` (0xD242, SDK: *Recording Setting — Movie*). They are excluded
> from the tables below; consider renaming or aliasing them to match SDK terminology.

### Exposure & Metering

| Property | Code | SDK page | R/W |
|---|---|---|---|
| Shutter Speed Value | 0xD016 | page_0059 | R/W |
| Shutter Speed Current Value | 0xD017 | page_0059 | R |
| Gain Control Setting | 0xD01C | page_0060 | R/W |
| Gain Unit Setting (ISO vs dB) | 0xD01D | page_0060 | R/W |
| Gain dB Value | 0xD01E | page_0060 | R/W |
| Gain Base ISO Sensitivity | 0xD020 | page_0060 | R/W |
| Exposure Index | 0xD022 | page_0060 | R/W |
| ISO Current Sensitivity | 0xD023 | page_0060 | R |
| Exposure Step (1/3 or 1/2 EV) | 0xD237 | page_0073 | R/W |
| Exposure Ctrl Type | 0xD099 | page_0062 | R/W |

### White Balance — Advanced

| Property | Code | SDK page | R/W |
|---|---|---|---|
| White Balance Mode Setting | 0xD00C | page_0059 | R/W |
| White Balance Tint | 0xD00D | page_0059 | R/W |
| WB Preset Color Temperature | 0xD086 | page_0062 | R/W |
| White Balance R Gain | 0xD087 | page_0062 | R/W |
| White Balance B Gain | 0xD088 | page_0062 | R/W |
| WB Offset Color Temp ATW | 0xD089 | page_0062 | R/W |
| WB Offset Tint ATW | 0xD08A | page_0062 | R/W |
| WB Offset Setting | 0xD0A9 | page_0063 | R/W |
| WB Offset Color Temp | 0xD0AA | page_0063 | R/W |

### Focus — Advanced

| Property | Code | SDK page | R/W |
|---|---|---|---|
| Focus Mode Setting | 0xD007 | page_0059 | R/W |
| Focus Speed Range | 0xD008 | page_0059 | R |
| Digital Zoom Scale | 0xD00A | page_0059 | R/W |
| Zoom Distance | 0xD00B | page_0059 | R/W |
| Zoom Distance Unit Setting | 0xD029 | page_0060 | R/W |
| AF Transition Speed | 0xD061 | page_0061 | R/W |
| AF Subject Shift Sensitivity | 0xD062 | page_0061 | R/W |
| Subject Recognition in AF | 0xD060 | page_0061 | R/W |
| Focal Position Current Value | 0xD24C | page_0073 | R |
| Near Far Enable Status | 0xD235 | page_0073 | R |

### Drive Mode / Special Capture

| Property | Code | SDK page | R/W |
|---|---|---|---|
| Pixel Shift Shooting Mode | 0xD239 | page_0073 | R |
| Pixel Shift Shooting Number | 0xD23A | page_0073 | R/W |
| Pixel Shift Shooting Interval | 0xD23B | page_0073 | R/W |
| Pixel Shift Shooting Status | 0xD23C | page_0073 | R |
| Progress Number of Pixel Shift | 0xD23D | page_0073 | R |
| Flicker Less Shooting | 0xD133 | page_0066 | R/W |
| Flicker Less Shooting Status | 0xD134 | page_0066 | R |
| Interval REC (Still) Mode | 0xD24F | page_0073 | R/W |

### HFR / S&Q / Interval Movie

| Property | Code | SDK page | R/W |
|---|---|---|---|
| S&Q Mode Setting | 0xD051 | page_0061 | R/W |
| S&Q Frame Rate | 0xD052 | page_0061 | R/W |
| S&Q Record Setting | 0xD0D1 | page_0063 | R/W |
| S&Q Rec Frame Rate | 0xD0D0 | page_0063 | R/W |
| Interval REC (Movie) Time | 0xD055 | page_0061 | R/W |
| Interval REC (Movie) Frames | 0xD056 | page_0061 | R/W |
| Interval REC (Movie) Frame Rate | 0xD151 | page_0067 | R/W |
| Interval REC (Movie) Record Setting | 0xD152 | page_0067 | R/W |

### Movie Settings

| Property | Code | SDK page | R/W |
|---|---|---|---|
| Recording Frame Rate Setting (Movie) | 0xD286 | page_0075 | R/W |
| Recording Duration | 0xD120 | page_0066 | R |
| Recording Resolution Main (Movie) | 0xD024 | page_0060 | R/W |
| Recording Resolution Proxy (Movie) | 0xD025 | page_0060 | R/W |
| Proxy File Format (Movie) | 0xD027 | page_0060 | R/W |
| Recording Frame Rate Proxy (Movie) | 0xD028 | page_0060 | R/W |
| Proxy Record Setting | 0xD109 | page_0065 | R/W |

> 0xD242 (*Recording Setting — Movie*) is already present as `MOVIE_QUALITY`; see note above.

### Audio

| Property | Code | SDK page | R/W |
|---|---|---|---|
| Audio Signals (Start/End) | 0xD220 | page_0073 | R/W |
| Audio Recording | 0xD0D2 | page_0063 | R/W |

### Display / Monitoring

| Property | Code | SDK page | R/W |
|---|---|---|---|
| Monitor DISP Mode Candidates (Still) | 0xD044 | page_0061 | R |
| Monitor DISP Mode Setting (Still) | 0xD045 | page_0061 | R/W |
| Monitor DISP Mode (Still) | 0xD046 | page_0061 | R/W |
| OSD Image Mode | 0xD207 | page_0072 | R/W |
| Monitor Brightness Type | 0xD1FB | page_0072 | R/W |
| Monitor Brightness Manual | 0xD1FC | page_0072 | R/W |

> 0xD231 (*LiveView Display Effect*) is already present as `VIEW`; 0xD26A (*Live View Image Quality*)
> as `LIVEVIEW_MODE` — see note above.

### Media / Storage

| Property | Code | SDK page | R/W |
|---|---|---|---|
| Media SLOT1 Status | 0xD248 | page_0073 | R |
| Media SLOT1 Remaining Shots | 0xD249 | page_0073 | R |
| Media SLOT1 Remaining Shooting Time | 0xD24A | page_0073 | R |
| Media SLOT2 Status | 0xD256 | page_0074 | R |
| Media SLOT2 Remaining Shots | 0xD257 | page_0074 | R |
| Media SLOT2 Remaining Shooting Time | 0xD258 | page_0074 | R |
| Media SLOT1 Image Quality | 0xD28D | page_0075 | R/W |
| Media SLOT2 Image Quality | 0xD28E | page_0075 | R/W |
| Media SLOT1 Image Size | 0xD28F | page_0075 | R/W |
| Media SLOT2 Image Size | 0xD290 | page_0075 | R/W |
| Recording Media (Still Image) | 0xD15F | page_0067 | R/W |
| Recording Media (Movie) | 0xD160 | page_0067 | R/W |
| Auto Switch Media | 0xD161 | page_0067 | R/W |
| RAW File Type | 0xD288 | page_0075 | R/W |
| Media SLOT1 RAW File Type | 0xD289 | page_0075 | R/W |
| Media SLOT2 RAW File Type | 0xD28A | page_0075 | R/W |
| Media SLOT1 File Format (Still) | 0xD28B | page_0075 | R/W |
| Media SLOT2 File Format (Still) | 0xD28C | page_0075 | R/W |

### Image Quality / Processing

| Property | Code | SDK page | R/W |
|---|---|---|---|
| CompRAW Shooting NR | 0xD148 | page_0066 | R/W |
| CompRAW Shooting NR RAW File Type | 0xD149 | page_0066 | R/W |
| CompRAW Shooting NR Number of Sheets | 0xD15A | page_0067 | R/W |
| Long Exposure NR | 0xD15B | page_0067 | R/W |
| High ISO NR | 0xD15C | page_0067 | R/W |
| Color Space (Still Image) | 0xD15E | page_0067 | R/W |
| HLG Still Image | 0xD15D | page_0067 | R/W |
| Compression File Format (Still) | 0xD287 | page_0075 | R/W |

### Creative

| Property | Code | SDK page | R/W |
|---|---|---|---|
| Picture Profile | 0xD23F | page_0073 | R/W |
| Creative Look | 0xD0FA | page_0065 | R/W |
| Creative Look Contrast | 0xD0FB | page_0065 | R/W |
| Creative Look Highlights | 0xD0FC | page_0065 | R/W |
| Creative Look Shadows | 0xD0FD | page_0065 | R/W |
| Creative Look Fade | 0xD0FE | page_0065 | R/W |
| Creative Look Saturation | 0xD0FF | page_0065 | R/W |
| Creative Look Sharpness | 0xD100 | page_0065 | R/W |
| Creative Look Sharpness Range | 0xD101 | page_0065 | R/W |
| Creative Look Clarity | 0xD102 | page_0065 | R/W |

> 0xD23F (*Picture Profile*) is referenced by raw hex in `format.py` but is absent from the
> `DeviceProperty` enum — add it there.

### Subject Recognition

| Property | Code | SDK page | R/W |
|---|---|---|---|
| Subject Recognition in AF | 0xD157 | page_0067 | R/W |
| Recognition Target | 0xD158 | page_0067 | R/W |
| Right/Left Eye Select | 0xD159 | page_0067 | R/W |
| Focus Bracket Shooting Status | 0xD0AB | page_0063 | R |

### Battery / Power

| Property | Code | SDK page | R/W |
|---|---|---|---|
| Battery Remain Display Unit | 0xD037 | page_0060 | R/W |
| Battery Remaining in Minutes | 0xD038 | page_0060 | R |
| Battery Remaining in Voltage | 0xD039 | page_0060 | R |
| Power Source | 0xD03A | page_0060 | R/W |
| DC Voltage | 0xD03E | page_0060 | R |
| Total Battery Remaining | 0xD204 | page_0072 | R |
| Total Battery Level Indicator | 0xD205 | page_0072 | R |
| USB Power Supply | 0xD150 | page_0067 | R/W |

### System Info

| Property | Code | SDK page | R/W |
|---|---|---|---|
| Software Version | 0xD040 | page_0060 | R |
| Lens Model Name | 0xD07B | page_0062 | R |
| Lens Serial Number | 0xD07C | page_0062 | R |
| Lens Version Number | 0xD07D | page_0062 | R |
| Camera System Error Info | 0xD07A | page_0062 | R |
| Camera Operating Mode | 0xD0BC | page_0063 | R |
| Device Overheating State | 0xD251 | page_0073 | R |

### Playback

| Property | Code | SDK page | R/W |
|---|---|---|---|
| Playback Media | 0xD042 | page_0060 | R/W |
| Playback View Mode | 0xD0BD | page_0063 | R |
| Playback Contents Recording Date/Time | 0xD09C | page_0062 | R |
| Playback Contents Name | 0xD09D | page_0062 | R |
| Playback Contents Number | 0xD09E | page_0062 | R |
| Playback Contents Total Number | 0xD09F | page_0062 | R |
| Playback Contents Recording Resolution | 0xD0A0 | page_0063 | R |
| Playback Contents Recording Frame Rate | 0xD0A1 | page_0063 | R |
| Playback Contents Recording File Format | 0xD0A2 | page_0063 | R |
| Playback Contents Gamma Type | 0xD0A4 | page_0063 | R |

---

## 3. Missing Controls

Source: SDK pages 655–691; control index in pages 034–035.

### High Priority — Not in `constants.py`

| Code | Control | SDK page | Notes |
|---|---|---|---|
| 0xD2DF | Custom WB Capture Standby | page_0660 | Starts active WB measurement mode |
| 0xD2E0 | Custom WB Capture Standby Cancel | page_0660 | Cancels WB measurement |
| 0xD2E1 | Custom WB Capture Execute | page_0661 | Applies measured WB |
| 0xD2E2 | Focus Magnification + | page_0661 | Increase magnification level |
| 0xD2E3 | Focus Magnification − | page_0661 | Decrease magnification level |
| 0xD2E5 | Tracking On + AF On Button | page_0034 | Activate subject tracking |
| 0xD2E7 | Cancel Media Format | page_0665 | Cancel in-progress format |
| 0xD2E9 | Save Zoom/Focus Position | page_0665 | Store focal preset to memory |
| 0xD2EA | Load Zoom/Focus Position | page_0666 | Recall focal preset from memory |
| 0xD2EB | Set PostView Enable | page_0666 | Enable/disable post-capture review display |
| 0xD2EC | Movie Rec Button (Toggle) | page_0667 | Single command to toggle recording |
| 0xF003 | Zoom Operation (INT16 Range) | page_0690 | −32767…+32767 smooth continuous speed |
| 0xF004 | Focus Operation (INT16 Range) | page_0690 | −32767…+32767 smooth continuous speed |

### Medium Priority — In `constants.py` but no `SonyCamera` method

| Constant | Code | Notes |
|---|---|---|
| `AE_LOCK` (0xD2C3) | AEL Button | No `press_ael()` / `release_ael()` helpers |
| `AF_LOCK` (0xD2C9) | FEL Button | No dedicated helper (note: also used as AF lock) |
| `AWB_LOCK` (0xD2D9) | AWBL Button | No `press_awbl()` helper |
| `FOCUS_MAGNIFIER` (0xD2CB) | Focus Magnifier On | No `enable_focus_magnifier()` helper |
| `FOCUS_MAGNIFIER_CANCEL` (0xD2CC) | Focus Magnifier Off | No `disable_focus_magnifier()` helper |
| `REMOTE_KEY_UP` (0xD2CD) | Remote Key UP | No menu navigation helpers |
| `REMOTE_KEY_DOWN` (0xD2CE) | Remote Key DOWN | — |
| `REMOTE_KEY_LEFT` (0xD2CF) | Remote Key LEFT | — |
| `REMOTE_KEY_RIGHT` (0xD2D0) | Remote Key RIGHT | — |
| `FOCUS_AREA_XY` (0xD2DC) | AF Area Position XY | No `set_focus_point(x, y)` helper |

### Low Priority / Professional

Assignable Buttons 1–11, Camera Button/Dial/Lever Function, Pixel Mapping, Sensor Cleaning,
Stream Button, PTZF operations — not relevant for consumer camera workflows.

---

## 4. Missing Events

Source: SDK pages 693–704.

### Missing Event Codes

`SDIOEventCode` currently defines only three codes (`OBJECT_ADDED` 0xC201, `OBJECT_REMOVED`
0xC202, `PROPERTY_CHANGED` 0xC203). The following 17 are absent:

| Code | Event | SDK page | Use case |
|---|---|---|---|
| 0x4004 | StoreAdded (PIMA 15740) | page_0693 | SD card inserted |
| 0x4005 | StoreRemoved (PIMA 15740) | page_0693 | SD card removed |
| 0xC205 | SDIE_DateTimeSettingResult | page_0694 | Clock sync complete |
| 0xC206 | SDIE_CapturedEvent | page_0694 | Capture sequence done (before ObjectAdded) |
| 0xC208 | SDIE_CWBCapturedResult | page_0695 | Custom WB done — returns colour temp |
| 0xC20B | SDIE_MediaFormatResult | page_0696 | Format complete/cancelled |
| 0xC20D | SDIE_MovieRecOperationResults | page_0697 | Clip written to card |
| 0xC20E | SDIE_FocusPositionResult | page_0697 | Focus move finished (OK/NG/Canceled) |
| 0xC20F | SDIE_ZoomandFocusPositionEvent | page_0698 | Continuous position struct (v1.1+) |
| 0xC210 | SDIE_OperationResults | page_0699 | Generic async operation result |
| 0xC211 | SDIE_OperationResults (variant) | page_0699 | Generic async operation result |
| 0xC214 | SDIE_CameraSettingFileReadResult | page_0700 | Settings file imported |
| 0xC217 | SDIE_ZoomPositionResult | page_0701 | Zoom move finished |
| 0xC218 | SDIE_FocusPositionResult (v2) | page_0701 | Focus move finished (variant) |
| 0xC21A | SDIE_MediaProfileChanged | page_0702 | Recording profile switched |
| 0xC21B | SDIE_MediaProfileChanged (variant) | page_0702 | Recording profile switched |
| 0xC21D | SDIE_AFStatus | page_0702 | AF tracking frame data (complex struct) |
| 0xC21E | SDIE_AFStatus (variant) | page_0703 | AF tracking frame data |
| 0xC21F | SDIE_RecordingTimeResult | page_0703 | Movie recording time remaining |
| 0xC222 | SDIE_ControlJobListEvent | page_0704 | Job queue state changed |

### Missing Event Infrastructure

`ptp.py` exposes `PTPTransport.wait_event()` which reads the interrupt endpoint and returns a
`PTPEvent` — the low-level primitive exists. However, `SonyCamera` has zero event-facing methods.
The following are needed:

- **Complete `SDIOEventCode` enum** — expand to cover all 20 codes (currently 3).
- **Event listener thread / async polling wrapper** — background thread or `asyncio` task that
  calls `wait_event()` in a loop and dispatches to registered callbacks.
- **Callback-based dispatch interface** — `camera.on_event(code, callback)` or similar.
- **At least one example script** demonstrating event-driven usage (e.g. reacting to
  `PROPERTY_CHANGED` or `SDIE_CapturedEvent`).

---

## 5. `format.py` Coverage Gaps

Current coverage: ~76% of properties in `constants.py` have formatters. Consumer-essential
properties (ISO, aperture, shutter, WB, focus, zoom, metering, battery) are all covered. Gaps:

| Code | Property | Gap | Impact |
|---|---|---|---|
| 0xD2DC | `FOCUS_AREA_XY` | No x,y coordinate unpacking — returns raw 4-byte hex | Medium — needed for focus-point feedback |
| 0xD2DF–0xD2E1 | Custom WB controls | Not in `constants.py` yet | N/A until added |
| 0xD2E9–0xD2EA | Position presets | Not in `constants.py` yet | N/A until added |
| 0xE0xx range | ~20 advanced/broadcast props | Fall through to generic hex | Low — rarely used on consumer cameras |

---

## 6. Page Reference Index

| Section | SDK pages |
|---|---|
| Document history / version changelog | pages 0003–0017 |
| Contents / TOC | pages 0018–0019 |
| Overview (connect, LiveView, movie, events) | pages 0025–0038 |
| Operations index | pages 0018–0019 |
| Operations detail | pages 0040–0120 |
| Device Properties index | pages 0059–0084 |
| Device Properties detail | pages 0120–0500 |
| Controls index | pages 0034–0035 |
| Controls detail | pages 0655–0691 |
| Events | pages 0693–0704 |
| Vendor Response Codes | pages 0705–0708 |
| Data Formats | pages 0709–0730 |
| Tips (HFR, FTP, firmware etc.) | pages 0731–0750 |

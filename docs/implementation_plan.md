# Implementation Plan — Missing SDK Features

Cross-reference: [docs/missing_features.md](missing_features.md)

**How to use:** Work through phases in order. Check off each item only after it has been
implemented, tested with mocked transport (`pytest tests/`), and manually verified against real
hardware (`pytest tests/test_hardware.py --run-hardware`).

---

## Phase 1 — Enum / Constants Expansion

*No logic changes. Pure data; zero risk of breaking existing behaviour. Must be done first because
every later phase depends on these names being available.*

### 1.1 Expand `PTPOpCode` in `constants.py`

Add opcodes that are absent from the enum (three already present as GET_STORAGE_INFO etc. are
excluded — only add the truly missing ones):

- [ ] `GET_THUMB = 0x100A`
- [ ] `SEND_OBJECT = 0x100D`
- [ ] `GET_PARTIAL_OBJECT = 0x101B`
- [ ] `GET_OBJECT_PROP_VALUE = 0x9803`
- [ ] `GET_OBJECT_PROP_LIST = 0x9805`

**Verify:** `pytest tests/test_constants.py` passes. Confirm enum members exist and hold correct
hex values.

---

### 1.2 Expand `SDIOOpCode` in `constants.py`

Add all missing SDIO vendor opcodes:

**High priority:**
- [ ] `GET_EXT_DEVICE_PROP = 0x9251`
- [ ] `GET_CONTENT_INFO_LIST = 0x923C`
- [ ] `GET_CONTENT_DATA = 0x923D`
- [ ] `DELETE_CONTENT = 0x9250`

**Medium priority:**
- [ ] `GET_CONTENT_COMPRESSED_DATA = 0x923E`
- [ ] `UPLOAD_DATA = 0x921A`
- [ ] `CONTROL_UPLOAD_DATA = 0x921B`
- [ ] `DOWNLOAD_DATA = 0x921D`
- [ ] `GET_LENS_INFORMATION = 0x9223`
- [ ] `OPERATION_RESULTS_SUPPORTED = 0x922F`
- [ ] `GET_VENDOR_CODE_VERSION = 0x9216`

**Verify:** `pytest tests/test_constants.py` passes.

---

### 1.3 Expand `SDIOEventCode` in `constants.py`

Replace current 3-member enum with the full set:

- [ ] `STORE_ADDED = 0x4004`
- [ ] `STORE_REMOVED = 0x4005`
- [ ] `DATE_TIME_SETTING_RESULT = 0xC205`
- [ ] `CAPTURED_EVENT = 0xC206`
- [ ] `CWB_CAPTURED_RESULT = 0xC208`
- [ ] `MEDIA_FORMAT_RESULT = 0xC20B`
- [ ] `MOVIE_REC_OPERATION_RESULTS = 0xC20D`
- [ ] `FOCUS_POSITION_RESULT = 0xC20E`
- [ ] `ZOOM_AND_FOCUS_POSITION_EVENT = 0xC20F`
- [ ] `OPERATION_RESULTS = 0xC210`
- [ ] `OPERATION_RESULTS_2 = 0xC211`
- [ ] `CAMERA_SETTING_FILE_READ_RESULT = 0xC214`
- [ ] `ZOOM_POSITION_RESULT = 0xC217`
- [ ] `FOCUS_POSITION_RESULT_2 = 0xC218`
- [ ] `MEDIA_PROFILE_CHANGED = 0xC21A`
- [ ] `MEDIA_PROFILE_CHANGED_2 = 0xC21B`
- [ ] `AF_STATUS = 0xC21D`
- [ ] `AF_STATUS_2 = 0xC21E`
- [ ] `RECORDING_TIME_RESULT = 0xC21F`
- [ ] `CONTROL_JOB_LIST_EVENT = 0xC222`

Keep existing three values (`OBJECT_ADDED = 0xC201`, `OBJECT_REMOVED = 0xC202`,
`PROPERTY_CHANGED = 0xC203`) intact.

**Verify:** `pytest tests/test_constants.py` passes.

---

### 1.4 Expand `DeviceProperty` — properties

Add all missing property codes to the `DeviceProperty` enum, grouped in comments matching
`missing_features.md`. Also add `PICTURE_PROFILE = 0xD23F` which is already referenced by raw
hex in `format.py` but absent from the enum.

**Exposure & Metering:**
- [ ] `SHUTTER_SPEED_VALUE = 0xD016`
- [ ] `SHUTTER_SPEED_CURRENT = 0xD017`
- [ ] `GAIN_CONTROL_SETTING = 0xD01C`
- [ ] `GAIN_UNIT_SETTING = 0xD01D`
- [ ] `GAIN_DB_VALUE = 0xD01E`
- [ ] `GAIN_BASE_ISO = 0xD020`
- [ ] `EXPOSURE_INDEX = 0xD022`
- [ ] `ISO_CURRENT = 0xD023`
- [ ] `EXPOSURE_STEP = 0xD237`
- [ ] `EXPOSURE_CTRL_TYPE = 0xD099`

**White Balance — Advanced:**
- [ ] `WB_MODE_SETTING = 0xD00C`
- [ ] `WB_TINT = 0xD00D`
- [ ] `WB_PRESET_COLOR_TEMP = 0xD086`
- [ ] `WB_R_GAIN = 0xD087`
- [ ] `WB_B_GAIN = 0xD088`
- [ ] `WB_OFFSET_COLOR_TEMP_ATW = 0xD089`
- [ ] `WB_OFFSET_TINT_ATW = 0xD08A`
- [ ] `WB_OFFSET_SETTING = 0xD0A9`
- [ ] `WB_OFFSET_COLOR_TEMP = 0xD0AA`

**Focus — Advanced:**
- [ ] `FOCUS_MODE_SETTING = 0xD007`
- [ ] `FOCUS_SPEED_RANGE = 0xD008`
- [ ] `DIGITAL_ZOOM_SCALE = 0xD00A`
- [ ] `ZOOM_DISTANCE = 0xD00B`
- [ ] `ZOOM_DISTANCE_UNIT = 0xD029`
- [ ] `AF_TRANSITION_SPEED = 0xD061`
- [ ] `AF_SUBJECT_SHIFT_SENSITIVITY = 0xD062`
- [ ] `SUBJECT_RECOGNITION_AF = 0xD060`
- [ ] `FOCAL_POSITION_CURRENT = 0xD24C`
- [ ] `NEAR_FAR_ENABLE_STATUS = 0xD235`

**Drive Mode / Special Capture:**
- [ ] `PIXEL_SHIFT_MODE = 0xD239`
- [ ] `PIXEL_SHIFT_NUMBER = 0xD23A`
- [ ] `PIXEL_SHIFT_INTERVAL = 0xD23B`
- [ ] `PIXEL_SHIFT_STATUS = 0xD23C`
- [ ] `PIXEL_SHIFT_PROGRESS = 0xD23D`
- [ ] `FLICKER_LESS_SHOOTING = 0xD133`
- [ ] `FLICKER_LESS_SHOOTING_STATUS = 0xD134`
- [ ] `INTERVAL_REC_STILL_MODE = 0xD24F`

**HFR / S&Q / Interval Movie:**
- [ ] `SQ_MODE_SETTING = 0xD051`
- [ ] `SQ_FRAME_RATE = 0xD052`
- [ ] `SQ_RECORD_SETTING = 0xD0D1`
- [ ] `SQ_REC_FRAME_RATE = 0xD0D0`
- [ ] `INTERVAL_REC_MOVIE_TIME = 0xD055`
- [ ] `INTERVAL_REC_MOVIE_FRAMES = 0xD056`
- [ ] `INTERVAL_REC_MOVIE_FRAME_RATE = 0xD151`
- [ ] `INTERVAL_REC_MOVIE_RECORD_SETTING = 0xD152`

**Movie Settings:**
- [ ] `RECORDING_FRAME_RATE_SETTING = 0xD286`
- [ ] `RECORDING_DURATION = 0xD120`
- [ ] `RECORDING_RESOLUTION_MAIN = 0xD024`
- [ ] `RECORDING_RESOLUTION_PROXY = 0xD025`
- [ ] `PROXY_FILE_FORMAT = 0xD027`
- [ ] `RECORDING_FRAME_RATE_PROXY = 0xD028`
- [ ] `PROXY_RECORD_SETTING = 0xD109`

**Audio:**
- [ ] `AUDIO_SIGNALS = 0xD220`
- [ ] `AUDIO_RECORDING = 0xD0D2`

**Display / Monitoring:**
- [ ] `MONITOR_DISP_MODE_CANDIDATES = 0xD044`
- [ ] `MONITOR_DISP_MODE_SETTING = 0xD045`
- [ ] `MONITOR_DISP_MODE = 0xD046`
- [ ] `OSD_IMAGE_MODE = 0xD207`
- [ ] `MONITOR_BRIGHTNESS_TYPE = 0xD1FB`
- [ ] `MONITOR_BRIGHTNESS_MANUAL = 0xD1FC`

**Media / Storage:**
- [ ] `MEDIA_SLOT1_STATUS = 0xD248`
- [ ] `MEDIA_SLOT1_REMAINING_SHOTS = 0xD249`
- [ ] `MEDIA_SLOT1_REMAINING_TIME = 0xD24A`
- [ ] `MEDIA_SLOT2_STATUS = 0xD256`
- [ ] `MEDIA_SLOT2_REMAINING_SHOTS = 0xD257`
- [ ] `MEDIA_SLOT2_REMAINING_TIME = 0xD258`
- [ ] `MEDIA_SLOT1_IMAGE_QUALITY = 0xD28D`
- [ ] `MEDIA_SLOT2_IMAGE_QUALITY = 0xD28E`
- [ ] `MEDIA_SLOT1_IMAGE_SIZE = 0xD28F`
- [ ] `MEDIA_SLOT2_IMAGE_SIZE = 0xD290`
- [ ] `RECORDING_MEDIA_STILL = 0xD15F`
- [ ] `RECORDING_MEDIA_MOVIE = 0xD160`
- [ ] `AUTO_SWITCH_MEDIA = 0xD161`
- [ ] `RAW_FILE_TYPE = 0xD288`
- [ ] `MEDIA_SLOT1_RAW_FILE_TYPE = 0xD289`
- [ ] `MEDIA_SLOT2_RAW_FILE_TYPE = 0xD28A`
- [ ] `MEDIA_SLOT1_FILE_FORMAT = 0xD28B`
- [ ] `MEDIA_SLOT2_FILE_FORMAT = 0xD28C`

**Image Quality / Processing:**
- [ ] `COMP_RAW_NR = 0xD148`
- [ ] `COMP_RAW_NR_RAW_FILE_TYPE = 0xD149`
- [ ] `COMP_RAW_NR_SHEETS = 0xD15A`
- [ ] `LONG_EXPOSURE_NR = 0xD15B`
- [ ] `HIGH_ISO_NR = 0xD15C`
- [ ] `COLOR_SPACE = 0xD15E`
- [ ] `HLG_STILL = 0xD15D`
- [ ] `COMPRESSION_FILE_FORMAT = 0xD287`

**Creative:**
- [ ] `PICTURE_PROFILE = 0xD23F`  *(also fixes the raw-hex reference in `format.py`)*
- [ ] `CREATIVE_LOOK = 0xD0FA`
- [ ] `CREATIVE_LOOK_CONTRAST = 0xD0FB`
- [ ] `CREATIVE_LOOK_HIGHLIGHTS = 0xD0FC`
- [ ] `CREATIVE_LOOK_SHADOWS = 0xD0FD`
- [ ] `CREATIVE_LOOK_FADE = 0xD0FE`
- [ ] `CREATIVE_LOOK_SATURATION = 0xD0FF`
- [ ] `CREATIVE_LOOK_SHARPNESS = 0xD100`
- [ ] `CREATIVE_LOOK_SHARPNESS_RANGE = 0xD101`
- [ ] `CREATIVE_LOOK_CLARITY = 0xD102`

**Subject Recognition:**
- [ ] `SUBJECT_RECOGNITION = 0xD157`
- [ ] `RECOGNITION_TARGET = 0xD158`
- [ ] `EYE_SELECT = 0xD159`
- [ ] `FOCUS_BRACKET_STATUS = 0xD0AB`

**Battery / Power:**
- [ ] `BATTERY_REMAIN_DISPLAY_UNIT = 0xD037`
- [ ] `BATTERY_REMAINING_MINUTES = 0xD038`
- [ ] `BATTERY_REMAINING_VOLTAGE = 0xD039`
- [ ] `POWER_SOURCE = 0xD03A`
- [ ] `DC_VOLTAGE = 0xD03E`
- [ ] `TOTAL_BATTERY_REMAINING = 0xD204`
- [ ] `TOTAL_BATTERY_LEVEL_INDICATOR = 0xD205`
- [ ] `USB_POWER_SUPPLY = 0xD150`

**System Info:**
- [ ] `SOFTWARE_VERSION = 0xD040`
- [ ] `LENS_MODEL_NAME = 0xD07B`
- [ ] `LENS_SERIAL_NUMBER = 0xD07C`
- [ ] `LENS_VERSION_NUMBER = 0xD07D`
- [ ] `CAMERA_SYSTEM_ERROR = 0xD07A`
- [ ] `CAMERA_OPERATING_MODE = 0xD0BC`
- [ ] `DEVICE_OVERHEATING = 0xD251`

**Playback:**
- [ ] `PLAYBACK_MEDIA = 0xD042`
- [ ] `PLAYBACK_VIEW_MODE = 0xD0BD`
- [ ] `PLAYBACK_CONTENTS_DATE_TIME = 0xD09C`
- [ ] `PLAYBACK_CONTENTS_NAME = 0xD09D`
- [ ] `PLAYBACK_CONTENTS_NUMBER = 0xD09E`
- [ ] `PLAYBACK_CONTENTS_TOTAL = 0xD09F`
- [ ] `PLAYBACK_CONTENTS_RESOLUTION = 0xD0A0`
- [ ] `PLAYBACK_CONTENTS_FRAME_RATE = 0xD0A1`
- [ ] `PLAYBACK_CONTENTS_FILE_FORMAT = 0xD0A2`
- [ ] `PLAYBACK_CONTENTS_GAMMA = 0xD0A4`

**Verify:** `pytest tests/test_constants.py` passes with no duplicate-value warnings or enum
conflicts.

---

### 1.5 Expand `DeviceProperty` — controls not yet present

- [ ] `CUSTOM_WB_STANDBY = 0xD2DF`
- [ ] `CUSTOM_WB_STANDBY_CANCEL = 0xD2E0`
- [ ] `CUSTOM_WB_EXECUTE = 0xD2E1`
- [ ] `FOCUS_MAG_PLUS = 0xD2E2`
- [ ] `FOCUS_MAG_MINUS = 0xD2E3`
- [ ] `TRACKING_AF_ON = 0xD2E5`
- [ ] `CANCEL_MEDIA_FORMAT = 0xD2E7`
- [ ] `SAVE_ZOOM_FOCUS_POSITION = 0xD2E9`
- [ ] `LOAD_ZOOM_FOCUS_POSITION = 0xD2EA`
- [ ] `SET_POST_VIEW_ENABLE = 0xD2EB`
- [ ] `MOVIE_REC_TOGGLE = 0xD2EC`
- [ ] `ZOOM_RANGE = 0xF003`
- [ ] `FOCUS_RANGE = 0xF004`

**Verify:** `pytest tests/test_constants.py` passes.

---

## Phase 2 — PTP Operation Methods

*Wraps already-defined opcodes with public `SonyCamera` methods. Each item: add method to
`camera.py` + unit test in `test_camera.py` (mocked transport) + hardware test in
`test_hardware.py`.*

### 2.1 `get_device_info() -> bytes`

- [ ] Implement: call `self._transport.receive(PTPOpCode.GET_DEVICE_INFO)`, return raw bytes.
- [ ] Unit test: mock returns `(OK, b"\x00" * 10)`; verify opcode is sent.
- [ ] Hardware test: call on live camera; verify response is non-empty bytes.

### 2.2 `get_storage_info(storage_id: int) -> bytes`

- [ ] Implement: call `self._transport.receive(PTPOpCode.GET_STORAGE_INFO, [storage_id])`.
- [ ] Unit test: mock; verify correct opcode + parameter forwarded.
- [ ] Hardware test: call with first ID from `_get_storage_ids()`; verify non-empty.

### 2.3 `get_num_objects(storage_id, format_code, parent_handle) -> int`

- [ ] Implement: call `GET_NUM_OBJECTS`, parse 4-byte LE uint from response payload.
- [ ] Unit test: payload `struct.pack("<I", 42)` → returns `42`.
- [ ] Hardware test: verify count is ≥ 0.

### 2.4 `get_thumb(handle: int) -> bytes`

- [ ] Add `GET_THUMB = 0x100A` (done in 1.1).
- [ ] Implement: `receive(PTPOpCode.GET_THUMB, [handle])`; return raw bytes (JPEG thumbnail).
- [ ] Unit test: mock with dummy bytes; assert returned.
- [ ] Hardware test: call with a known object handle; write to `.jpg` and visually verify.

### 2.5 `get_partial_object(handle: int, offset: int, max_bytes: int) -> bytes`

- [ ] Add `GET_PARTIAL_OBJECT = 0x101B` (done in 1.1).
- [ ] Implement: `receive(PTPOpCode.GET_PARTIAL_OBJECT, [handle, offset, max_bytes])`.
- [ ] Unit test: verify three parameters forwarded correctly.
- [ ] Hardware test: fetch first 4096 bytes of an object; verify starts with JPEG SOI marker
  `\xFF\xD8`.

---

## Phase 3 — SDIO Single-Property Query

### 3.1 `get_ext_device_prop(prop_code: int) -> DevicePropInfo`

- [ ] Add `GET_EXT_DEVICE_PROP = 0x9251` (done in 1.2).
- [ ] Implement in `camera.py`: `receive(SDIOOpCode.GET_EXT_DEVICE_PROP, [prop_code])`. Parse
  the response with the existing `parse_all_device_props()` or a new `parse_single_device_prop()`
  helper in `parser.py` (whichever the SDK wire format requires — confirm from SDK page_0019).
- [ ] Unit test: mock transport returns a minimal serialised `DevicePropInfo`; assert the
  returned object has the expected `prop_code`.
- [ ] Hardware test: round-trip — call `get_ext_device_prop(DeviceProperty.ISO)` and compare
  result to `get_property(DeviceProperty.ISO)`.

---

## Phase 4 — Content Management (SDIO)

*Enables browsing and downloading files directly without entering Contents Transfer mode.*

### 4.1 `get_content_info_list(...) -> list[dict]`

- [ ] Add `GET_CONTENT_INFO_LIST = 0x923C` (done in 1.2).
- [ ] Study SDK pages ~0100–0107 for the request parameter format and response struct layout.
- [ ] Implement: `receive(SDIOOpCode.GET_CONTENT_INFO_LIST, params)`. Add a
  `parse_content_info_list(data)` function in `parser.py` that returns a list of dicts
  `{content_id, file_name, date_time, size, format_code}`.
- [ ] Unit test: hand-craft a minimal response buffer; assert parsed list length and field values.
- [ ] Hardware test: list contents of SLOT1; print the first five entries; verify file names
  look correct.

### 4.2 `get_content_data(content_id: int, ...) -> bytes`

- [ ] Add `GET_CONTENT_DATA = 0x923D` (done in 1.2).
- [ ] Study SDK page ~0107 for parameter/response format.
- [ ] Implement: `receive(SDIOOpCode.GET_CONTENT_DATA, [content_id, ...])`.
- [ ] Unit test: mock; assert opcode and content_id forwarded.
- [ ] Hardware test: download first item from `get_content_info_list()`; save to disk; verify
  file is a valid JPEG or video by inspecting magic bytes.

### 4.3 `delete_content(content_id: int) -> None`

- [ ] Add `DELETE_CONTENT = 0x9250` (done in 1.2).
- [ ] Study SDK page ~0110.
- [ ] Implement: `send(SDIOOpCode.DELETE_CONTENT, [content_id])`; raise `TransactionError` on
  non-OK response.
- [ ] Unit test: mock returns OK; assert send called with correct opcode.
- [ ] **Hardware test: use a dedicated test file on the card; verify it is no longer returned by
  `get_content_info_list()` after deletion.**

---

## Phase 5 — Control Helpers in `SonyCamera`

*All controls here use existing `control_device()` — just thin named wrappers.*

### 5.1 Exposure lock helpers

- [ ] `press_ael() / release_ael()` — `DeviceProperty.AE_LOCK`, values 0x0002 / 0x0001
- [ ] `press_awbl() / release_awbl()` — `DeviceProperty.AWB_LOCK`
- [ ] Unit test: assert `control_device` called with correct property code and value.
- [ ] Hardware test: call `press_ael()`; read `AE_LOCK_INDICATION` property; assert locked.

### 5.2 Focus magnifier helpers

- [ ] `enable_focus_magnifier()` — `DeviceProperty.FOCUS_MAGNIFIER`, value 0x0002
- [ ] `disable_focus_magnifier()` — `DeviceProperty.FOCUS_MAGNIFIER_CANCEL`, value 0x0002
- [ ] `focus_mag_increase()` — `DeviceProperty.FOCUS_MAG_PLUS`
- [ ] `focus_mag_decrease()` — `DeviceProperty.FOCUS_MAG_MINUS`
- [ ] Unit test: verify control codes.
- [ ] Hardware test: enable magnifier; verify `FOCUS_MAGNIFY` property reads On; disable.

### 5.3 Remote key navigation helpers

- [ ] `remote_key_up() / down() / left() / right()` — `REMOTE_KEY_UP/DOWN/LEFT/RIGHT`,
  value 0x0002 for press, 0x0001 for release. Each helper should press then release.
- [ ] Unit test: verify two `control_device` calls per helper (press + release).
- [ ] Hardware test: call in sequence; confirm camera menu navigates (visual inspection).

### 5.4 `set_focus_point(x: int, y: int) -> None`

- [ ] Study SDK page for `FOCUS_AREA_XY` (0xD2DC) payload format (likely two INT16 packed as
  a 4-byte UINT32).
- [ ] Implement: pack `x, y` into the correct wire format; call `control_device`.
- [ ] Unit test: verify packing logic.
- [ ] Hardware test: set a focus point; read `FOCUS_AREA` or liveview overlay; verify movement.

### 5.5 Custom WB capture sequence

- [ ] `custom_wb_standby()` — `DeviceProperty.CUSTOM_WB_STANDBY`
- [ ] `custom_wb_cancel()` — `DeviceProperty.CUSTOM_WB_STANDBY_CANCEL`
- [ ] `custom_wb_execute()` — `DeviceProperty.CUSTOM_WB_EXECUTE`
- [ ] Unit test: verify control codes.
- [ ] Hardware test: point camera at grey card; call standby → execute; verify WB property
  changed.

### 5.6 Movie rec toggle helper

- [ ] `toggle_movie()` — `DeviceProperty.MOVIE_REC_TOGGLE`, value 0x0002
- [ ] Unit test: verify control code.
- [ ] Hardware test (movie mode): call once to start recording; call again to stop; verify clip
  appears via `get_content_info_list()`.

### 5.7 Zoom/Focus position presets

- [ ] `save_zoom_focus_position()` — `DeviceProperty.SAVE_ZOOM_FOCUS_POSITION`
- [ ] `load_zoom_focus_position()` — `DeviceProperty.LOAD_ZOOM_FOCUS_POSITION`
- [ ] Unit test: verify control codes.
- [ ] Hardware test: set a zoom position; save; move zoom; load; verify zoom returns.

### 5.8 Continuous zoom/focus (INT16 range)

- [ ] `zoom_continuous(speed: int) -> None` — uses `DeviceProperty.ZOOM_RANGE` (0xF003),
  INT16 value −32767…+32767; positive = tele, negative = wide. Size = 2 bytes signed.
- [ ] `focus_continuous(speed: int) -> None` — `DeviceProperty.FOCUS_RANGE` (0xF004), same
  range.
- [ ] Unit test: verify correct property code and value packing.
- [ ] Hardware test: call with speed=10000, sleep 0.5 s, call with speed=0; verify lens moved.

---

## Phase 6 — Extended Property Setters/Getters

*Thin wrappers around `set_property()` / `get_property()`. Implement as a group, test as a group.*

### 6.1 Focus advanced

- [ ] `set_focus_mode_setting(value: int)` → `FOCUS_MODE_SETTING`
- [ ] `set_af_transition_speed(value: int)` → `AF_TRANSITION_SPEED` (0–7)
- [ ] `set_af_subject_shift_sensitivity(value: int)` → `AF_SUBJECT_SHIFT_SENSITIVITY` (0–5)
- [ ] `set_subject_recognition_af(value: int)` → `SUBJECT_RECOGNITION_AF`
- [ ] `get_focal_position() -> int` → reads `FOCAL_POSITION_CURRENT`
- [ ] Hardware test: read focal position before and after a `focus_near()` call; verify change.

### 6.2 White balance advanced

- [ ] `set_wb_preset_color_temp(kelvin: int)` → `WB_PRESET_COLOR_TEMP`; valid range typically
  2500–9900 K in 100 K steps — validate at boundary.
- [ ] `set_wb_r_gain(value: int)` / `set_wb_b_gain(value: int)` → `WB_R_GAIN` / `WB_B_GAIN`
- [ ] Hardware test: set WB to Color Temp mode; adjust preset temp; read back; verify.

### 6.3 S&Q / HFR mode

- [ ] `set_sq_mode(value: int)` → `SQ_MODE_SETTING`
- [ ] `set_sq_frame_rate(value: int)` → `SQ_FRAME_RATE`
- [ ] `set_sq_record_setting(value: int)` → `SQ_RECORD_SETTING`
- [ ] Hardware test: set S&Q mode on a compatible body; verify `EXPOSURE_MODE` reads an
  `SQ_MOVIE_*` value.

### 6.4 Media slot status readers

- [ ] `get_media_slot1_status() -> dict` — reads `MEDIA_SLOT1_STATUS`, `_REMAINING_SHOTS`,
  `_REMAINING_TIME`; returns a dict.
- [ ] `get_media_slot2_status() -> dict` — same for SLOT2.
- [ ] Hardware test: insert card; call; verify remaining_shots > 0. Remove card; call; verify
  status indicates no card.

### 6.5 Battery extended info

- [ ] `get_battery_info() -> dict` — reads `BATTERY_REMAINING_MINUTES`,
  `BATTERY_REMAINING_VOLTAGE`, `TOTAL_BATTERY_REMAINING`, `POWER_SOURCE`.
- [ ] Hardware test: call and print; verify values are plausible (voltage > 6 V for NP-FZ100).

### 6.6 System info readers

- [ ] `get_lens_info() -> dict` — reads `LENS_MODEL_NAME`, `LENS_SERIAL_NUMBER`,
  `LENS_VERSION_NUMBER`.
- [ ] `get_software_version() -> str` — reads `SOFTWARE_VERSION`.
- [ ] Hardware test: call with lens attached; verify model name is a non-empty string.

---

## Phase 7 — Event System

### 7.1 Expand `SDIOEventCode` enum *(done in Phase 1.3)*

### 7.2 `EventDispatcher` class in `camera.py`

- [ ] Implement a private `_EventDispatcher` that runs a background thread, calls
  `self._transport.wait_event()` in a loop with a short timeout (e.g. 500 ms), and dispatches
  to registered callbacks keyed by `SDIOEventCode`.
- [ ] API on `SonyCamera`:
  - `camera.on_event(code: SDIOEventCode, callback: Callable[[PTPEvent], None]) -> None`
  - `camera.start_event_listener() -> None`
  - `camera.stop_event_listener() -> None`
- [ ] The listener thread must stop cleanly when `disconnect()` is called.
- [ ] Unit test (mocked transport):
  - `wait_event()` raises `TimeoutError` once (simulates idle), then returns a mock
    `PTPEvent(code=0xC203, params=[0xD21E, 0, 0, 0, 0])`; assert the callback is invoked
    with that event.
  - Assert that after `stop_event_listener()` the thread is no longer alive.
- [ ] Hardware test: register callback for `PROPERTY_CHANGED`; change ISO on camera dial;
  verify callback fires within 2 s with `params[0] == DeviceProperty.ISO`.

### 7.3 Example script `examples/event_listener.py`

- [ ] Demonstrate: connect → authenticate → register callbacks for `PROPERTY_CHANGED` and
  `CAPTURED_EVENT` → start listener → loop printing events for 30 s → stop listener.
- [ ] Manual test: run script; change settings on camera; verify events print to console.

---

## Phase 8 — `format.py` Fixes & Extensions

### 8.1 Fix `PICTURE_PROFILE` key in `_VALUE_FORMATTERS`

- [ ] Replace raw `0xD23F` key with `DeviceProperty.PICTURE_PROFILE` (available after Phase 1.4).
- [ ] Verify: `pytest tests/test_format.py` passes with no change in output.

### 8.2 Add `FOCUS_AREA_XY` formatter

- [ ] Study SDK page for `FOCUS_AREA_XY` (0xD2DC) to confirm the 4-byte packing
  (expected: `INT16 x` at bytes 0–1, `INT16 y` at bytes 2–3, or a single UINT32).
- [ ] Add `_fmt_focus_xy(v: int) -> str` that returns `f"({x}, {y})"`.
- [ ] Register in `_VALUE_FORMATTERS`.
- [ ] Unit test: `format_value(DeviceProperty.FOCUS_AREA_XY, 0x00640096)` →
  `"(100, 150)"` (adjust expected based on confirmed byte order).

### 8.3 Add formatters for new controls (after Phase 1.5)

- [ ] `CUSTOM_WB_STANDBY / CANCEL / EXECUTE` — simple `{0x0001: "Off", 0x0002: "On"}` dict.
- [ ] `ZOOM_RANGE / FOCUS_RANGE` — `_fmt_signed_speed(v: int) -> str` that sign-extends
  INT16 and returns `f"{sv:+d}"`.

---

## Phase 9 — Medium-Priority SDIO Operations

*Lower day-to-day value; implement after all higher phases are verified.*

### 9.1 `get_lens_information() -> bytes`

- [ ] `SDIO_GetLensInformation = 0x9223`
- [ ] Implement, unit test, hardware test.

### 9.2 `get_vendor_code_version() -> int`

- [ ] `SDIO_GetVendorCodeVersion = 0x9216`; returns a 2-byte LE uint.
- [ ] Hardware test: verify result matches `SDI_VERSION_V3` (0x012C) on a v3 camera.

### 9.3 `operation_results_supported() -> bool`

- [ ] `SDIO_OperationResultsSupported = 0x922F`; check response code.
- [ ] Hardware test: call before registering event listener; log support status.

### 9.4 `get_content_compressed_data(content_id: int) -> bytes`

- [ ] `SDIO_GetContentCompressedData = 0x923E`
- [ ] Study SDK page ~0108 for parameters.
- [ ] Hardware test: download proxy thumbnail of a video clip; verify it is a valid image.

### 9.5 Upload/Download data (`SDIO_UploadData`, `SDIO_ControlUploadData`, `SDIO_DownloadData`)

- [ ] These require studying SDK pages ~0080–0082 for multi-step transaction protocol.
- [ ] Implement each as a separate method.
- [ ] Hardware test: roundtrip — upload a small test file, download it back, verify byte-for-byte
  match.

---

## Appendix — Deferred / Out of Scope

The following items from `missing_features.md` are tracked here for completeness but are **not
planned for the immediate implementation backlog**:

- **MTP bulk ops** (`GetObjectPropValue` 0x9803, `GetObjectPropList` 0x9805) — opcodes added in
  Phase 1.1 so callers can use `_transport` directly if needed; no high-level wrappers planned.
- **FTP server management** — `SetFTPSettingFilePassword`, `GetFTPJobList`, etc.
- **Streaming** — `GetStreamSettingList`, `SetStreamSettingList`
- **Firmware update** — `RequestFirmwareUpdateCheck`, `SetFirmwareUpdateMode`, etc.
- **Date/time** — `GetAreaTimeZoneSetting`, `SetAreaTimeZoneSetting`
- **PTZ/PTZF** — not consumer-relevant
- **`SendObject` (0x100D)** — opcode added in Phase 1.1; no high-level method planned until a
  concrete transfer use-case is identified
- **`0xE0xx` property range** — broadcast/professional; low consumer impact
- **Constants naming conflicts** (`VIEW`, `LIVEVIEW_MODE`, `MOVIE_QUALITY`) — consider aliasing
  to SDK names in a future clean-up pass; not blocking anything

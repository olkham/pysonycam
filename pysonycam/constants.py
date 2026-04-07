"""
PTP and Sony SDIO constants: opcodes, property codes, and value enumerations.

All hex values are taken directly from the Sony Camera Remote Command SDK.
"""

from enum import IntEnum


# ---------------------------------------------------------------------------
# PTP container types
# ---------------------------------------------------------------------------
class ContainerType(IntEnum):
    """PTP bulk container types."""
    COMMAND = 0x0001
    DATA = 0x0002
    RESPONSE = 0x0003
    EVENT = 0x0004


# ---------------------------------------------------------------------------
# PTP data-type codes  (used inside DevicePropInfo datasets)
# ---------------------------------------------------------------------------
class DataType(IntEnum):
    UNDEF = 0x0000
    INT8 = 0x0001
    UINT8 = 0x0002
    INT16 = 0x0003
    UINT16 = 0x0004
    INT32 = 0x0005
    UINT32 = 0x0006
    INT64 = 0x0007
    UINT64 = 0x0008
    INT128 = 0x0009
    UINT128 = 0x000A
    AINT8 = 0x4001
    AUINT8 = 0x4002
    AINT16 = 0x4003
    AUINT16 = 0x4004
    AINT32 = 0x4005
    AUINT32 = 0x4006
    AINT64 = 0x4007
    AUINT64 = 0x4008
    AINT128 = 0x4009
    AUINT128 = 0x400A
    STR = 0xFFFF


# Size in bytes of each scalar type
DATA_TYPE_SIZE: dict[int, int] = {
    DataType.INT8: 1, DataType.UINT8: 1,
    DataType.INT16: 2, DataType.UINT16: 2,
    DataType.INT32: 4, DataType.UINT32: 4,
    DataType.INT64: 8, DataType.UINT64: 8,
    DataType.INT128: 16, DataType.UINT128: 16,
}

# struct format characters for scalar types (little-endian)
DATA_TYPE_FMT: dict[int, str] = {
    DataType.INT8: "b", DataType.UINT8: "B",
    DataType.INT16: "<h", DataType.UINT16: "<H",
    DataType.INT32: "<i", DataType.UINT32: "<I",
    DataType.INT64: "<q", DataType.UINT64: "<Q",
}


def scalar_type_for_array(dt: int) -> int:
    """Return the scalar DataType code for an array DataType code."""
    if 0x4001 <= dt <= 0x400A:
        return dt - 0x4000
    raise ValueError(f"0x{dt:04X} is not an array DataType")


# ---------------------------------------------------------------------------
# PTP response / status codes
# ---------------------------------------------------------------------------
class ResponseCode(IntEnum):
    UNDEFINED = 0x2000
    OK = 0x2001
    GENERAL_ERROR = 0x2002
    SESSION_NOT_OPEN = 0x2003
    INVALID_TRANSACTION_ID = 0x2004
    OPERATION_NOT_SUPPORTED = 0x2005
    PARAMETER_NOT_SUPPORTED = 0x2006
    INCOMPLETE_TRANSFER = 0x2007
    INVALID_STORAGE_ID = 0x2008
    INVALID_OBJECT_HANDLE = 0x2009
    DEVICE_PROP_NOT_SUPPORTED = 0x200A
    STORE_FULL = 0x200C
    ACCESS_DENIED = 0x200F
    SPECIFICATION_BY_FORMAT_UNSUPPORTED = 0x2014
    INVALID_DEVICE_PROP_VALUE = 0x201C


# ---------------------------------------------------------------------------
# Standard PTP operation codes
# ---------------------------------------------------------------------------
class PTPOpCode(IntEnum):
    GET_DEVICE_INFO = 0x1001
    OPEN_SESSION = 0x1002
    CLOSE_SESSION = 0x1003
    GET_STORAGE_ID = 0x1004
    GET_STORAGE_INFO = 0x1005
    GET_NUM_OBJECTS = 0x1006
    GET_OBJECT_HANDLES = 0x1007
    GET_OBJECT_INFO = 0x1008
    GET_OBJECT = 0x1009
    DELETE_OBJECT = 0x100B
    GET_THUMB = 0x100A
    SEND_OBJECT = 0x100D
    GET_PARTIAL_OBJECT = 0x101B
    # MTP vendor extensions (outside standard 0x1xxx range)
    GET_OBJECT_PROP_VALUE = 0x9803
    GET_OBJECT_PROP_LIST = 0x9805


# ---------------------------------------------------------------------------
# Sony SDIO vendor operation codes
# ---------------------------------------------------------------------------
class SDIOOpCode(IntEnum):
    CONNECT = 0x9201
    GET_EXT_DEVICE_INFO = 0x9202
    SET_EXT_DEVICE_PROP_VALUE = 0x9205
    CONTROL_DEVICE = 0x9207
    GET_ALL_EXT_DEVICE_INFO = 0x9209
    SDIO_OPEN_SESSION = 0x9210
    SET_CONTENTS_TRANSFER_MODE = 0x9212
    # Medium priority
    GET_VENDOR_CODE_VERSION = 0x9216
    UPLOAD_DATA = 0x921A
    CONTROL_UPLOAD_DATA = 0x921B
    DOWNLOAD_DATA = 0x921D
    GET_LENS_INFORMATION = 0x9223
    OPERATION_RESULTS_SUPPORTED = 0x922F
    # High priority content management
    DELETE_CONTENT = 0x9250
    GET_EXT_DEVICE_PROP = 0x9251
    GET_CONTENT_INFO_LIST = 0x923C
    GET_CONTENT_DATA = 0x923D
    GET_CONTENT_COMPRESSED_DATA = 0x923E


# ---------------------------------------------------------------------------
# Sony SDIO event codes
# ---------------------------------------------------------------------------
class SDIOEventCode(IntEnum):
    # Standard PIMA 15740
    STORE_ADDED = 0x4004
    STORE_REMOVED = 0x4005
    # Sony vendor events
    OBJECT_ADDED = 0xC201
    OBJECT_REMOVED = 0xC202
    PROPERTY_CHANGED = 0xC203
    DATE_TIME_SETTING_RESULT = 0xC205
    CAPTURED_EVENT = 0xC206
    CWB_CAPTURED_RESULT = 0xC208
    MEDIA_FORMAT_RESULT = 0xC20B
    MOVIE_REC_OPERATION_RESULTS = 0xC20D
    FOCUS_POSITION_RESULT = 0xC20E
    ZOOM_AND_FOCUS_POSITION_EVENT = 0xC20F
    OPERATION_RESULTS = 0xC210
    OPERATION_RESULTS_2 = 0xC211
    CAMERA_SETTING_FILE_READ_RESULT = 0xC214
    ZOOM_POSITION_RESULT = 0xC217
    FOCUS_POSITION_RESULT_2 = 0xC218
    MEDIA_PROFILE_CHANGED = 0xC21A
    MEDIA_PROFILE_CHANGED_2 = 0xC21B
    AF_STATUS = 0xC21D
    AF_STATUS_2 = 0xC21E
    RECORDING_TIME_RESULT = 0xC21F
    CONTROL_JOB_LIST_EVENT = 0xC222


# ---------------------------------------------------------------------------
# SDIO extension version constants
# ---------------------------------------------------------------------------
SDI_VERSION_V2 = 0x00C8  # 200
SDI_VERSION_V3 = 0x012C  # 300

# Special object handles
SHOT_OBJECT_HANDLE = 0xFFFFC001
LIVEVIEW_OBJECT_HANDLE = 0xFFFFC002


# ---------------------------------------------------------------------------
# Device Property Codes
# ---------------------------------------------------------------------------
class DeviceProperty(IntEnum):
    """Sony SDIO device property codes."""
    # Image quality
    COMPRESSION_SETTING = 0x5004
    WHITE_BALANCE = 0x5005
    F_NUMBER = 0x5007
    FOCUS_MODE = 0x500A
    METERING_MODE = 0x500B
    FLASH_MODE = 0x500C
    EXPOSURE_MODE = 0x500E
    EXPOSURE_COMPENSATION = 0x5010
    OPERATING_MODE = 0x5013

    # Sony vendor properties
    FLASH_COMP = 0xD200
    DRO_HDR_MODE = 0xD201
    IMAGE_SIZE = 0xD203
    SHUTTER_SPEED = 0xD20D
    BATTERY_LEVEL = 0xD20E
    COLOR_TEMP = 0xD20F
    WB_GM = 0xD210
    ASPECT_RATIO = 0xD211
    AF_STATUS = 0xD213
    SHOOTING_FILE_INFO = 0xD215
    AE_LOCK_INDICATION = 0xD217
    PICTURE_EFFECTS = 0xD21B
    WB_AB = 0xD21C
    ISO = 0xD21E
    AF_LOCK_INDICATION = 0xD21F
    LIVEVIEW_STATUS = 0xD221
    SAVE_MEDIA = 0xD222
    FOCUS_AREA = 0xD22C
    VIEW = 0xD231
    CREATIVE_STYLE = 0xD240
    MOVIE_FORMAT = 0xD241
    MOVIE_QUALITY = 0xD242
    JPEG_QUALITY = 0xD252
    FILE_FORMAT = 0xD253
    FOCUS_MAGNIFY = 0xD254
    POSITION_KEY = 0xD25A
    ZOOM_SCALE = 0xD25C
    ZOOM_OPTIC = 0xD25D
    ZOOM_SETTING = 0xD25F
    WIRELESS_FLASH = 0xD262
    LIVEVIEW_MODE = 0xD26A

    # Still Capture Mode / Drive Mode (same register as OPERATING_MODE)
    STILL_CAPTURE_MODE = 0x5013  # alias — drive mode (Normal, Cont. Hi, etc.)

    # Button controls (used with ControlDevice)
    S1_BUTTON = 0xD2C1
    S2_BUTTON = 0xD2C2
    AE_LOCK = 0xD2C3
    REQUEST_ONE_SHOOTING = 0xD2C7
    MOVIE_REC = 0xD2C8
    AF_LOCK = 0xD2C9
    MEDIA_FORMAT = 0xD2CA
    FOCUS_MAGNIFIER = 0xD2CB
    FOCUS_MAGNIFIER_CANCEL = 0xD2CC
    REMOTE_KEY_UP = 0xD2CD
    REMOTE_KEY_DOWN = 0xD2CE
    REMOTE_KEY_LEFT = 0xD2CF
    REMOTE_KEY_RIGHT = 0xD2D0
    NEAR_FAR = 0xD2D1
    AF_MF_HOLD = 0xD2D2
    CANCEL_PIXEL_SHIFT = 0xD2D3
    PIXEL_SHIFT_MODE = 0xD2D4
    HFR_STANDBY = 0xD2D5
    HFR_RECORDING_CANCEL = 0xD2D6
    FOCUS_STEP_NEAR = 0xD2D7
    FOCUS_STEP_FAR = 0xD2D8
    AWB_LOCK = 0xD2D9
    FOCUS_AREA_XY = 0xD2DC
    ZOOM = 0xD2DD

    # ------------------------------------------------------------------
    # Phase 1.4 additions — missing device properties
    # ------------------------------------------------------------------

    # Exposure & Metering
    SHUTTER_SPEED_VALUE = 0xD016
    SHUTTER_SPEED_CURRENT = 0xD017
    GAIN_CONTROL_SETTING = 0xD01C
    GAIN_UNIT_SETTING = 0xD01D
    GAIN_DB_VALUE = 0xD01E
    GAIN_BASE_ISO = 0xD020
    EXPOSURE_INDEX = 0xD022
    ISO_CURRENT = 0xD023
    EXPOSURE_STEP = 0xD237
    EXPOSURE_CTRL_TYPE = 0xD099

    # White Balance — Advanced
    WB_MODE_SETTING = 0xD00C
    WB_TINT = 0xD00D
    WB_PRESET_COLOR_TEMP = 0xD086
    WB_R_GAIN = 0xD087
    WB_B_GAIN = 0xD088
    WB_OFFSET_COLOR_TEMP_ATW = 0xD089
    WB_OFFSET_TINT_ATW = 0xD08A
    WB_OFFSET_SETTING = 0xD0A9
    WB_OFFSET_COLOR_TEMP = 0xD0AA

    # Focus — Advanced
    FOCUS_MODE_SETTING = 0xD007
    FOCUS_SPEED_RANGE = 0xD008
    DIGITAL_ZOOM_SCALE = 0xD00A
    ZOOM_DISTANCE = 0xD00B
    ZOOM_DISTANCE_UNIT = 0xD029
    AF_TRANSITION_SPEED = 0xD061
    AF_SUBJECT_SHIFT_SENSITIVITY = 0xD062
    SUBJECT_RECOGNITION_AF = 0xD060
    FOCAL_POSITION_CURRENT = 0xD24C
    NEAR_FAR_ENABLE_STATUS = 0xD235

    # Drive Mode / Special Capture
    PIXEL_SHIFT_SHOOTING_MODE = 0xD239
    PIXEL_SHIFT_NUMBER = 0xD23A
    PIXEL_SHIFT_INTERVAL = 0xD23B
    PIXEL_SHIFT_STATUS = 0xD23C
    PIXEL_SHIFT_PROGRESS = 0xD23D
    FLICKER_LESS_SHOOTING = 0xD133
    FLICKER_LESS_SHOOTING_STATUS = 0xD134
    INTERVAL_REC_STILL_MODE = 0xD24F

    # HFR / S&Q / Interval Movie
    SQ_MODE_SETTING = 0xD051
    SQ_FRAME_RATE = 0xD052
    SQ_RECORD_SETTING = 0xD0D1
    SQ_REC_FRAME_RATE = 0xD0D0
    INTERVAL_REC_MOVIE_TIME = 0xD055
    INTERVAL_REC_MOVIE_FRAMES = 0xD056
    INTERVAL_REC_MOVIE_FRAME_RATE = 0xD151
    INTERVAL_REC_MOVIE_RECORD_SETTING = 0xD152

    # Movie Settings
    RECORDING_FRAME_RATE_SETTING = 0xD286
    RECORDING_DURATION = 0xD120
    RECORDING_RESOLUTION_MAIN = 0xD024
    RECORDING_RESOLUTION_PROXY = 0xD025
    PROXY_FILE_FORMAT = 0xD027
    RECORDING_FRAME_RATE_PROXY = 0xD028
    PROXY_RECORD_SETTING = 0xD109

    # Audio
    AUDIO_SIGNALS = 0xD220
    AUDIO_RECORDING = 0xD0D2

    # Display / Monitoring
    MONITOR_DISP_MODE_CANDIDATES = 0xD044
    MONITOR_DISP_MODE_SETTING = 0xD045
    MONITOR_DISP_MODE = 0xD046
    OSD_IMAGE_MODE = 0xD207
    MONITOR_BRIGHTNESS_TYPE = 0xD1FB
    MONITOR_BRIGHTNESS_MANUAL = 0xD1FC

    # Media / Storage
    MEDIA_SLOT1_STATUS = 0xD248
    MEDIA_SLOT1_REMAINING_SHOTS = 0xD249
    MEDIA_SLOT1_REMAINING_TIME = 0xD24A
    MEDIA_SLOT2_STATUS = 0xD256
    MEDIA_SLOT2_REMAINING_SHOTS = 0xD257
    MEDIA_SLOT2_REMAINING_TIME = 0xD258
    MEDIA_SLOT1_IMAGE_QUALITY = 0xD28D
    MEDIA_SLOT2_IMAGE_QUALITY = 0xD28E
    MEDIA_SLOT1_IMAGE_SIZE = 0xD28F
    MEDIA_SLOT2_IMAGE_SIZE = 0xD290
    RECORDING_MEDIA_STILL = 0xD15F
    RECORDING_MEDIA_MOVIE = 0xD160
    AUTO_SWITCH_MEDIA = 0xD161
    RAW_FILE_TYPE = 0xD288
    MEDIA_SLOT1_RAW_FILE_TYPE = 0xD289
    MEDIA_SLOT2_RAW_FILE_TYPE = 0xD28A
    MEDIA_SLOT1_FILE_FORMAT = 0xD28B
    MEDIA_SLOT2_FILE_FORMAT = 0xD28C

    # Image Quality / Processing
    COMP_RAW_NR = 0xD148
    COMP_RAW_NR_RAW_FILE_TYPE = 0xD149
    COMP_RAW_NR_SHEETS = 0xD15A
    LONG_EXPOSURE_NR = 0xD15B
    HIGH_ISO_NR = 0xD15C
    COLOR_SPACE = 0xD15E
    HLG_STILL = 0xD15D
    COMPRESSION_FILE_FORMAT = 0xD287

    # Creative
    PICTURE_PROFILE = 0xD23F
    CREATIVE_LOOK = 0xD0FA
    CREATIVE_LOOK_CONTRAST = 0xD0FB
    CREATIVE_LOOK_HIGHLIGHTS = 0xD0FC
    CREATIVE_LOOK_SHADOWS = 0xD0FD
    CREATIVE_LOOK_FADE = 0xD0FE
    CREATIVE_LOOK_SATURATION = 0xD0FF
    CREATIVE_LOOK_SHARPNESS = 0xD100
    CREATIVE_LOOK_SHARPNESS_RANGE = 0xD101
    CREATIVE_LOOK_CLARITY = 0xD102

    # Subject Recognition
    SUBJECT_RECOGNITION = 0xD157
    RECOGNITION_TARGET = 0xD158
    EYE_SELECT = 0xD159
    FOCUS_BRACKET_STATUS = 0xD0AB

    # Battery / Power
    BATTERY_REMAIN_DISPLAY_UNIT = 0xD037
    BATTERY_REMAINING_MINUTES = 0xD038
    BATTERY_REMAINING_VOLTAGE = 0xD039
    POWER_SOURCE = 0xD03A
    DC_VOLTAGE = 0xD03E
    TOTAL_BATTERY_REMAINING = 0xD204
    TOTAL_BATTERY_LEVEL_INDICATOR = 0xD205
    USB_POWER_SUPPLY = 0xD150

    # System Info
    SOFTWARE_VERSION = 0xD040
    LENS_MODEL_NAME = 0xD07B
    LENS_SERIAL_NUMBER = 0xD07C
    LENS_VERSION_NUMBER = 0xD07D
    CAMERA_SYSTEM_ERROR = 0xD07A
    CAMERA_OPERATING_MODE = 0xD0BC
    DEVICE_OVERHEATING = 0xD251

    # Playback
    PLAYBACK_MEDIA = 0xD042
    PLAYBACK_VIEW_MODE = 0xD0BD
    PLAYBACK_CONTENTS_DATE_TIME = 0xD09C
    PLAYBACK_CONTENTS_NAME = 0xD09D
    PLAYBACK_CONTENTS_NUMBER = 0xD09E
    PLAYBACK_CONTENTS_TOTAL = 0xD09F
    PLAYBACK_CONTENTS_RESOLUTION = 0xD0A0
    PLAYBACK_CONTENTS_FRAME_RATE = 0xD0A1
    PLAYBACK_CONTENTS_FILE_FORMAT = 0xD0A2
    PLAYBACK_CONTENTS_GAMMA = 0xD0A4

    # ------------------------------------------------------------------
    # Phase 1.5 additions — missing control codes
    # ------------------------------------------------------------------
    CUSTOM_WB_STANDBY = 0xD2DF
    CUSTOM_WB_STANDBY_CANCEL = 0xD2E0
    CUSTOM_WB_EXECUTE = 0xD2E1
    FOCUS_MAG_PLUS = 0xD2E2
    FOCUS_MAG_MINUS = 0xD2E3
    TRACKING_AF_ON = 0xD2E5
    CANCEL_MEDIA_FORMAT = 0xD2E7
    SAVE_ZOOM_FOCUS_POSITION = 0xD2E9
    LOAD_ZOOM_FOCUS_POSITION = 0xD2EA
    SET_POST_VIEW_ENABLE = 0xD2EB
    MOVIE_REC_TOGGLE = 0xD2EC
    ZOOM_RANGE = 0xF003
    FOCUS_RANGE = 0xF004


# ---------------------------------------------------------------------------
# Value enumerations for common properties
# ---------------------------------------------------------------------------
class ExposureMode(IntEnum):
    MANUAL = 0x00000001
    PROGRAM_AUTO = 0x00010002
    APERTURE_PRIORITY = 0x00020003
    SHUTTER_PRIORITY = 0x00030004
    AUTO = 0x00048000
    AUTO_PLUS = 0x00048001
    SPORTS_ACTION = 0x00058011
    SUNSET = 0x00058012
    NIGHT_SCENE = 0x00058013
    LANDSCAPE = 0x00058014
    MACRO = 0x00058015
    HANDHELD_TWILIGHT = 0x00058016
    NIGHT_PORTRAIT = 0x00058017
    ANTI_MOTION_BLUR = 0x00058018
    MOVIE_P = 0x00078050
    MOVIE_A = 0x00078051
    MOVIE_S = 0x00078052
    MOVIE_M = 0x00078053
    MOVIE_AUTO = 0x00078054
    SQ_MOVIE_P = 0x00098059
    SQ_MOVIE_A = 0x0009805A
    SQ_MOVIE_S = 0x0009805B
    SQ_MOVIE_M = 0x0009805C
    HFR_P = 0x00088080
    HFR_A = 0x00088081
    HFR_S = 0x00088082
    HFR_M = 0x00088083


class OperatingMode(IntEnum):
    STANDBY = 0x01
    STILL_REC = 0x02
    MOVIE_REC = 0x03
    CONTENTS_TRANSFER = 0x04


class WhiteBalance(IntEnum):
    MANUAL = 0x0001
    AWB = 0x0002
    ONE_PUSH_AUTO = 0x0003
    DAYLIGHT = 0x0004
    FLUORESCENT = 0x0005
    TUNGSTEN = 0x0006
    FLASH = 0x0007
    FLUOR_WARM_WHITE = 0x8001
    FLUOR_COOL_WHITE = 0x8002
    FLUOR_DAY_WHITE = 0x8003
    FLUOR_DAYLIGHT = 0x8004
    CLOUDY = 0x8010
    SHADE = 0x8011
    COLOR_TEMP = 0x8012
    CUSTOM_1 = 0x8020
    CUSTOM_2 = 0x8021
    CUSTOM_3 = 0x8022
    UNDERWATER_AUTO = 0x8030


class FocusMode(IntEnum):
    MANUAL = 0x0001
    AF_S = 0x0002
    AF_C = 0x8004
    AF_AUTO = 0x8005
    DMF = 0x8006


class FocusArea(IntEnum):
    WIDE = 0x0001
    ZONE = 0x0002
    CENTER = 0x0003
    FLEXIBLE_SPOT_S = 0x0101
    FLEXIBLE_SPOT_M = 0x0102
    FLEXIBLE_SPOT_L = 0x0103
    EXPAND_FLEXIBLE_SPOT = 0x0104
    LOCK_ON_WIDE = 0x0201
    LOCK_ON_ZONE = 0x0202
    LOCK_ON_CENTER = 0x0203
    LOCK_ON_FLEX_S = 0x0204
    LOCK_ON_FLEX_M = 0x0205
    LOCK_ON_FLEX_L = 0x0206
    LOCK_ON_EXPAND_FLEX = 0x0207


class ImageSize(IntEnum):
    LARGE = 0x01
    MEDIUM = 0x02
    SMALL = 0x03


class JpegQuality(IntEnum):
    EXTRA_FINE = 0x01
    FINE = 0x02
    STANDARD = 0x03
    LIGHT = 0x04


class FileFormat(IntEnum):
    RAW = 0x01
    RAW_JPEG = 0x02
    JPEG = 0x03


class AspectRatio(IntEnum):
    AR_3_2 = 0x01
    AR_16_9 = 0x02
    AR_4_3 = 0x03
    AR_1_1 = 0x04


class LiveViewMode(IntEnum):
    LOW = 0x01
    HIGH = 0x02


class SaveMedia(IntEnum):
    HOST = 0x0001
    CAMERA = 0x0010
    HOST_AND_CAMERA = 0x0011


class ZoomSetting(IntEnum):
    OPTICAL_ONLY = 0x01
    SMART_ZOOM = 0x02
    CLEAR_IMAGE_ZOOM = 0x03
    DIGITAL_ZOOM = 0x04


class MeteringMode(IntEnum):
    MULTI = 0x8001
    CENTER_WEIGHTED = 0x8002
    ENTIRE_SCREEN_AVG = 0x8003
    SPOT_STANDARD = 0x8004
    SPOT_LARGE = 0x8005
    HIGHLIGHT = 0x8006


class DriveMode(IntEnum):
    """Still Capture Mode / Drive Mode values (property 0x5013).

    Values use the v3 (32-bit) encoding where the upper 16 bits indicate
    the mode group (0x0001 = continuous, 0x0003 = self-timer, etc.).
    """
    SINGLE = 0x00000001
    CONTINUOUS_HI = 0x00010002
    CONTINUOUS_HI_PLUS = 0x00018010
    CONTINUOUS_HI_LIVE = 0x00018011
    CONTINUOUS_LO = 0x00018012
    CONTINUOUS = 0x00018013
    CONTINUOUS_SPEED_PRIORITY = 0x00018014
    CONTINUOUS_MID = 0x00018015
    CONTINUOUS_MID_LIVE = 0x00018016
    CONTINUOUS_LO_LIVE = 0x00018017
    SELF_TIMER_5 = 0x00038003
    SELF_TIMER_10 = 0x00038004
    SELF_TIMER_2 = 0x00038005


class BatteryLevel(IntEnum):
    DUMMY = 0x01
    UNUSABLE = 0x02
    PRE_END = 0x03
    LEVEL_1_4 = 0x04
    LEVEL_2_4 = 0x05
    LEVEL_3_4 = 0x06
    LEVEL_4_4 = 0x07
    LEVEL_1_3 = 0x08
    LEVEL_2_3 = 0x09
    LEVEL_3_3 = 0x0A
    USB_POWER = 0x10


# ---------------------------------------------------------------------------
# Human-readable lookup tables (for display / logging)
# ---------------------------------------------------------------------------

SHUTTER_SPEED_TABLE = {
    0x00000000: "Bulb",
    0x012C000A: "30\"", 0x00FA000A: "25\"", 0x00C8000A: "20\"",
    0x0096000A: "15\"", 0x0082000A: "13\"", 0x0064000A: "10\"",
    0x0050000A: "8\"", 0x003C000A: "6\"", 0x0032000A: "5\"",
    0x0028000A: "4\"", 0x0020000A: "3.2\"", 0x0019000A: "2.5\"",
    0x0014000A: "2\"", 0x0010000A: "1.6\"", 0x000D000A: "1.3\"",
    0x000A000A: "1\"", 0x0008000A: "0.8\"", 0x0006000A: "0.6\"",
    0x0005000A: "0.5\"", 0x0004000A: "0.4\"",
    0x00010003: "1/3", 0x00010004: "1/4", 0x00010005: "1/5",
    0x00010006: "1/6", 0x00010008: "1/8", 0x0001000A: "1/10",
    0x0001000D: "1/13", 0x0001000F: "1/15", 0x00010014: "1/20",
    0x00010019: "1/25", 0x0001001E: "1/30", 0x00010028: "1/40",
    0x00010032: "1/50", 0x0001003C: "1/60", 0x00010050: "1/80",
    0x00010064: "1/100", 0x0001007D: "1/125", 0x000100A0: "1/160",
    0x000100C8: "1/200", 0x000100FA: "1/250", 0x00010140: "1/320",
    0x00010190: "1/400", 0x000101F4: "1/500", 0x00010320: "1/800",
    0x000103E8: "1/1000", 0x000104E2: "1/1250", 0x00010640: "1/1600",
    0x000107D0: "1/2000", 0x000109C4: "1/2500", 0x00010C80: "1/3200",
    0x00010FA0: "1/4000", 0x00011388: "1/5000", 0x00011770: "1/6000",
    0x00011900: "1/6400", 0x00011F40: "1/8000",
}

F_NUMBER_TABLE = {
    0x006E: "F1.1", 0x0078: "F1.2", 0x0082: "F1.3", 0x008C: "F1.4",
    0x00A0: "F1.6", 0x00AA: "F1.7", 0x00B4: "F1.8", 0x00C8: "F2",
    0x00DC: "F2.2", 0x00F0: "F2.4", 0x00FA: "F2.5", 0x0118: "F2.8",
    0x0140: "F3.2", 0x015E: "F3.5", 0x0190: "F4", 0x01C2: "F4.5",
    0x01F4: "F5", 0x0230: "F5.6", 0x0276: "F6.3", 0x029E: "F6.7",
    0x02C6: "F7.1", 0x0320: "F8", 0x0384: "F9", 0x03B6: "F9.5",
    0x03E8: "F10", 0x044C: "F11", 0x0514: "F13", 0x0578: "F14",
    0x0640: "F16", 0x0708: "F18", 0x076C: "F19", 0x07D0: "F20",
    0x0898: "F22", 0x09C4: "F25", 0x0A8C: "F27", 0x0B54: "F29",
    0x0C80: "F32",
}

ISO_TABLE = {
    0x00000032: "50", 0x00000040: "64", 0x00000050: "80",
    0x00000064: "100", 0x0000007D: "125", 0x000000A0: "160",
    0x000000C8: "200", 0x000000FA: "250", 0x00000140: "320",
    0x00000190: "400", 0x000001F4: "500", 0x00000280: "640",
    0x00000320: "800", 0x000003E8: "1000", 0x000004E2: "1250",
    0x00000640: "1600", 0x000007D0: "2000", 0x000009C4: "2500",
    0x00000C80: "3200", 0x00000FA0: "4000", 0x00001388: "5000",
    0x00001900: "6400", 0x00001F40: "8000", 0x00002710: "10000",
    0x00003200: "12800", 0x00003E80: "16000", 0x00004E20: "20000",
    0x00006400: "25600", 0x00007D00: "32000", 0x00009C40: "40000",
    0x0000C800: "51200", 0x0000FA00: "64000", 0x00013880: "80000",
    0x00019000: "102400",
    0x00FFFFFF: "AUTO",
}

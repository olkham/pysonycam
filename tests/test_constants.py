"""Tests for pysonycam.constants — enums, tables, and helpers."""

import struct
import pytest

from pysonycam.constants import (
    ContainerType,
    DataType,
    ResponseCode,
    PTPOpCode,
    SDIOOpCode,
    SDIOEventCode,
    DeviceProperty,
    ExposureMode,
    OperatingMode,
    WhiteBalance,
    FocusMode,
    FocusArea,
    ImageSize,
    JpegQuality,
    FileFormat,
    AspectRatio,
    LiveViewMode,
    SaveMedia,
    ZoomSetting,
    MeteringMode,
    DriveMode,
    BatteryLevel,
    DATA_TYPE_SIZE,
    DATA_TYPE_FMT,
    SDI_VERSION_V2,
    SDI_VERSION_V3,
    SHOT_OBJECT_HANDLE,
    LIVEVIEW_OBJECT_HANDLE,
    SHUTTER_SPEED_TABLE,
    F_NUMBER_TABLE,
    ISO_TABLE,
    scalar_type_for_array,
)


# ══════════════════════════════════════════════════════════════════════════
# scalar_type_for_array
# ══════════════════════════════════════════════════════════════════════════

class TestScalarTypeForArray:
    @pytest.mark.parametrize("array_dt, expected_scalar", [
        (DataType.AINT8, DataType.INT8),
        (DataType.AUINT8, DataType.UINT8),
        (DataType.AINT16, DataType.INT16),
        (DataType.AUINT16, DataType.UINT16),
        (DataType.AINT32, DataType.INT32),
        (DataType.AUINT32, DataType.UINT32),
        (DataType.AINT64, DataType.INT64),
        (DataType.AUINT64, DataType.UINT64),
        (DataType.AINT128, DataType.INT128),
        (DataType.AUINT128, DataType.UINT128),
    ])
    def test_valid_conversions(self, array_dt, expected_scalar):
        assert scalar_type_for_array(array_dt) == expected_scalar

    @pytest.mark.parametrize("bad_dt", [
        DataType.UINT8, DataType.UINT16, DataType.UINT32,
        DataType.INT8, DataType.STR, DataType.UNDEF, 0x9999,
    ])
    def test_non_array_raises(self, bad_dt):
        with pytest.raises(ValueError, match="is not an array DataType"):
            scalar_type_for_array(bad_dt)


# ══════════════════════════════════════════════════════════════════════════
# ContainerType
# ══════════════════════════════════════════════════════════════════════════

class TestContainerType:
    def test_values(self):
        assert ContainerType.COMMAND == 1
        assert ContainerType.DATA == 2
        assert ContainerType.RESPONSE == 3
        assert ContainerType.EVENT == 4


# ══════════════════════════════════════════════════════════════════════════
# DataType sizes & formats
# ══════════════════════════════════════════════════════════════════════════

class TestDataTypeTables:
    def test_all_scalar_types_have_sizes(self):
        """Every non-array, non-string, non-UNDEF DataType should have a size."""
        for dt in DataType:
            if dt == DataType.UNDEF or dt == DataType.STR or 0x4001 <= dt <= 0x400A:
                continue
            assert dt in DATA_TYPE_SIZE, f"Missing size for {dt.name}"

    def test_sizes_match_struct_format(self):
        """Size values should match the struct format string sizes."""
        for dt, fmt in DATA_TYPE_FMT.items():
            expected = struct.calcsize(fmt)
            assert DATA_TYPE_SIZE[dt] == expected, f"Size mismatch for {DataType(dt).name}"

    def test_128bit_not_in_fmt(self):
        """128-bit types use custom parsing, should not be in DATA_TYPE_FMT."""
        assert DataType.INT128 not in DATA_TYPE_FMT
        assert DataType.UINT128 not in DATA_TYPE_FMT
        assert DATA_TYPE_SIZE[DataType.INT128] == 16
        assert DATA_TYPE_SIZE[DataType.UINT128] == 16


# ══════════════════════════════════════════════════════════════════════════
# ResponseCode
# ══════════════════════════════════════════════════════════════════════════

class TestResponseCode:
    def test_ok(self):
        assert ResponseCode.OK == 0x2001

    def test_common_errors(self):
        assert ResponseCode.GENERAL_ERROR == 0x2002
        assert ResponseCode.DEVICE_PROP_NOT_SUPPORTED == 0x200A
        assert ResponseCode.INVALID_DEVICE_PROP_VALUE == 0x201C


# ══════════════════════════════════════════════════════════════════════════
# PTPOpCode / SDIOOpCode
# ══════════════════════════════════════════════════════════════════════════

class TestOpCodes:
    def test_ptp_range(self):
        """Standard PTP opcodes are in the 0x1000 range; MTP extensions allowed in 0x9xxx."""
        _mtp_extensions = {PTPOpCode.GET_OBJECT_PROP_VALUE, PTPOpCode.GET_OBJECT_PROP_LIST}
        for op in PTPOpCode:
            if op in _mtp_extensions:
                assert 0x9000 <= op <= 0x9FFF
            else:
                assert 0x1000 <= op <= 0x1FFF

    def test_sdio_range(self):
        """Sony SDIO opcodes are in the 0x9000 range."""
        for op in SDIOOpCode:
            assert 0x9000 <= op <= 0x9FFF

    def test_key_sdio_codes(self):
        assert SDIOOpCode.CONNECT == 0x9201
        assert SDIOOpCode.GET_ALL_EXT_DEVICE_INFO == 0x9209
        assert SDIOOpCode.CONTROL_DEVICE == 0x9207

    def test_new_ptp_opcodes(self):
        assert PTPOpCode.GET_THUMB == 0x100A
        assert PTPOpCode.SEND_OBJECT == 0x100D
        assert PTPOpCode.GET_PARTIAL_OBJECT == 0x101B
        assert PTPOpCode.GET_OBJECT_PROP_VALUE == 0x9803
        assert PTPOpCode.GET_OBJECT_PROP_LIST == 0x9805

    def test_new_sdio_opcodes(self):
        assert SDIOOpCode.GET_EXT_DEVICE_PROP == 0x9251
        assert SDIOOpCode.GET_CONTENT_INFO_LIST == 0x923C
        assert SDIOOpCode.GET_CONTENT_DATA == 0x923D
        assert SDIOOpCode.DELETE_CONTENT == 0x9250
        assert SDIOOpCode.GET_CONTENT_COMPRESSED_DATA == 0x923E
        assert SDIOOpCode.GET_VENDOR_CODE_VERSION == 0x9216
        assert SDIOOpCode.UPLOAD_DATA == 0x921A
        assert SDIOOpCode.CONTROL_UPLOAD_DATA == 0x921B
        assert SDIOOpCode.DOWNLOAD_DATA == 0x921D
        assert SDIOOpCode.GET_LENS_INFORMATION == 0x9223
        assert SDIOOpCode.OPERATION_RESULTS_SUPPORTED == 0x922F

    def test_expanded_event_codes(self):
        assert SDIOEventCode.OBJECT_ADDED == 0xC201
        assert SDIOEventCode.OBJECT_REMOVED == 0xC202
        assert SDIOEventCode.PROPERTY_CHANGED == 0xC203
        assert SDIOEventCode.STORE_ADDED == 0x4004
        assert SDIOEventCode.STORE_REMOVED == 0x4005
        assert SDIOEventCode.CAPTURED_EVENT == 0xC206
        assert SDIOEventCode.CWB_CAPTURED_RESULT == 0xC208
        assert SDIOEventCode.MEDIA_FORMAT_RESULT == 0xC20B
        assert SDIOEventCode.MOVIE_REC_OPERATION_RESULTS == 0xC20D
        assert SDIOEventCode.FOCUS_POSITION_RESULT == 0xC20E
        assert SDIOEventCode.ZOOM_AND_FOCUS_POSITION_EVENT == 0xC20F
        assert SDIOEventCode.OPERATION_RESULTS == 0xC210
        assert SDIOEventCode.OPERATION_RESULTS_2 == 0xC211
        assert SDIOEventCode.CAMERA_SETTING_FILE_READ_RESULT == 0xC214
        assert SDIOEventCode.ZOOM_POSITION_RESULT == 0xC217
        assert SDIOEventCode.FOCUS_POSITION_RESULT_2 == 0xC218
        assert SDIOEventCode.MEDIA_PROFILE_CHANGED == 0xC21A
        assert SDIOEventCode.MEDIA_PROFILE_CHANGED_2 == 0xC21B
        assert SDIOEventCode.AF_STATUS == 0xC21D
        assert SDIOEventCode.AF_STATUS_2 == 0xC21E
        assert SDIOEventCode.RECORDING_TIME_RESULT == 0xC21F
        assert SDIOEventCode.CONTROL_JOB_LIST_EVENT == 0xC222

    def test_new_device_properties(self):
        # Exposure
        assert DeviceProperty.SHUTTER_SPEED_VALUE == 0xD016
        assert DeviceProperty.ISO_CURRENT == 0xD023
        assert DeviceProperty.EXPOSURE_STEP == 0xD237
        # WB
        assert DeviceProperty.WB_MODE_SETTING == 0xD00C
        assert DeviceProperty.WB_PRESET_COLOR_TEMP == 0xD086
        assert DeviceProperty.WB_R_GAIN == 0xD087
        assert DeviceProperty.WB_B_GAIN == 0xD088
        # Focus
        assert DeviceProperty.FOCUS_MODE_SETTING == 0xD007
        assert DeviceProperty.AF_TRANSITION_SPEED == 0xD061
        assert DeviceProperty.FOCAL_POSITION_CURRENT == 0xD24C
        # S&Q
        assert DeviceProperty.SQ_MODE_SETTING == 0xD051
        assert DeviceProperty.SQ_FRAME_RATE == 0xD052
        # Media
        assert DeviceProperty.MEDIA_SLOT1_STATUS == 0xD248
        assert DeviceProperty.MEDIA_SLOT2_STATUS == 0xD256
        # Creative
        assert DeviceProperty.PICTURE_PROFILE == 0xD23F
        assert DeviceProperty.CREATIVE_LOOK == 0xD0FA
        # Battery
        assert DeviceProperty.BATTERY_REMAINING_MINUTES == 0xD038
        assert DeviceProperty.POWER_SOURCE == 0xD03A
        # System
        assert DeviceProperty.LENS_MODEL_NAME == 0xD07B
        assert DeviceProperty.SOFTWARE_VERSION == 0xD040
        # Controls
        assert DeviceProperty.CUSTOM_WB_STANDBY == 0xD2DF
        assert DeviceProperty.MOVIE_REC_TOGGLE == 0xD2EC
        assert DeviceProperty.ZOOM_RANGE == 0xF003
        assert DeviceProperty.FOCUS_RANGE == 0xF004

    def test_no_duplicate_values_in_device_property(self):
        """Each non-alias DeviceProperty value should be unique (except known aliases)."""
        # STILL_CAPTURE_MODE = 0x5013 is intentionally the same as OPERATING_MODE
        seen: dict[int, str] = {}
        for prop in DeviceProperty:
            val = int(prop)
            if val in seen:
                # Only the known alias is permitted
                assert val == 0x5013, (
                    f"Unexpected duplicate DeviceProperty value 0x{val:04X}: "
                    f"{seen[val]} and {prop.name}"
                )
            else:
                seen[val] = prop.name


# ══════════════════════════════════════════════════════════════════════════
# Version constants
# ══════════════════════════════════════════════════════════════════════════

class TestVersionConstants:
    def test_v2(self):
        assert SDI_VERSION_V2 == 200

    def test_v3(self):
        assert SDI_VERSION_V3 == 300

    def test_object_handles(self):
        assert SHOT_OBJECT_HANDLE == 0xFFFFC001
        assert LIVEVIEW_OBJECT_HANDLE == 0xFFFFC002


# ══════════════════════════════════════════════════════════════════════════
# DeviceProperty
# ══════════════════════════════════════════════════════════════════════════

class TestDeviceProperty:
    def test_key_properties(self):
        assert DeviceProperty.F_NUMBER == 0x5007
        assert DeviceProperty.EXPOSURE_MODE == 0x500E
        assert DeviceProperty.ISO == 0xD21E
        assert DeviceProperty.SHUTTER_SPEED == 0xD20D

    def test_button_controls(self):
        assert DeviceProperty.S1_BUTTON == 0xD2C1
        assert DeviceProperty.S2_BUTTON == 0xD2C2
        assert DeviceProperty.ZOOM == 0xD2DD


# ══════════════════════════════════════════════════════════════════════════
# Value enumerations
# ══════════════════════════════════════════════════════════════════════════

class TestValueEnums:
    def test_exposure_modes(self):
        assert ExposureMode.MANUAL == 0x00000001
        assert ExposureMode.PROGRAM_AUTO == 0x00010002
        assert ExposureMode.APERTURE_PRIORITY == 0x00020003
        assert ExposureMode.SHUTTER_PRIORITY == 0x00030004

    def test_operating_modes(self):
        assert OperatingMode.STANDBY == 1
        assert OperatingMode.STILL_REC == 2
        assert OperatingMode.MOVIE_REC == 3
        assert OperatingMode.CONTENTS_TRANSFER == 4

    def test_white_balance(self):
        assert WhiteBalance.AWB == 2
        assert WhiteBalance.DAYLIGHT == 4
        assert WhiteBalance.COLOR_TEMP == 0x8012

    def test_focus_modes(self):
        assert FocusMode.MANUAL == 1
        assert FocusMode.AF_S == 2
        assert FocusMode.AF_C == 0x8004

    def test_image_quality(self):
        assert ImageSize.LARGE == 1
        assert JpegQuality.EXTRA_FINE == 1
        assert FileFormat.RAW_JPEG == 2

    def test_aspect_ratios(self):
        assert AspectRatio.AR_3_2 == 1
        assert AspectRatio.AR_16_9 == 2

    def test_save_media(self):
        assert SaveMedia.HOST == 1
        assert SaveMedia.CAMERA == 0x10
        assert SaveMedia.HOST_AND_CAMERA == 0x11


# ══════════════════════════════════════════════════════════════════════════
# Lookup tables
# ══════════════════════════════════════════════════════════════════════════

class TestLookupTables:
    def test_shutter_speed_table_has_bulb(self):
        assert 0x00000000 in SHUTTER_SPEED_TABLE
        assert SHUTTER_SPEED_TABLE[0] == "Bulb"

    def test_shutter_speed_common_values(self):
        assert SHUTTER_SPEED_TABLE[0x00010064] == "1/100"
        assert SHUTTER_SPEED_TABLE[0x000100FA] == "1/250"
        assert SHUTTER_SPEED_TABLE[0x000103E8] == "1/1000"

    def test_f_number_table(self):
        assert F_NUMBER_TABLE[0x0118] == "F2.8"
        assert F_NUMBER_TABLE[0x0190] == "F4"
        assert F_NUMBER_TABLE[0x0C80] == "F32"

    def test_iso_table(self):
        assert ISO_TABLE[0x64] == "100"
        assert ISO_TABLE[0x0190] == "400"
        assert ISO_TABLE[0x00FFFFFF] == "AUTO"

    def test_tables_have_no_duplicate_keys(self):
        """Dict keys are unique by construction, but values should map correctly."""
        for table_name, table in [
            ("SHUTTER_SPEED_TABLE", SHUTTER_SPEED_TABLE),
            ("F_NUMBER_TABLE", F_NUMBER_TABLE),
            ("ISO_TABLE", ISO_TABLE),
        ]:
            assert len(table) > 0, f"{table_name} is empty"
            for k, v in table.items():
                assert isinstance(k, int), f"{table_name} key {k} not int"
                assert isinstance(v, str), f"{table_name} value for {k} not str"

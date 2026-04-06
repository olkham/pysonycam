"""Tests for pysonycam.exceptions — exception hierarchy."""

import pytest

from pysonycam.exceptions import (
    SonyCameraError,
    ConnectionError,
    DeviceNotFoundError,
    AuthenticationError,
    TransactionError,
    TimeoutError,
    PropertyError,
)


class TestExceptionHierarchy:
    def test_all_inherit_from_base(self):
        for exc_cls in [
            ConnectionError, DeviceNotFoundError, AuthenticationError,
            TransactionError, TimeoutError, PropertyError,
        ]:
            assert issubclass(exc_cls, SonyCameraError)

    def test_device_not_found_is_connection_error(self):
        assert issubclass(DeviceNotFoundError, ConnectionError)

    def test_base_is_exception(self):
        assert issubclass(SonyCameraError, Exception)


class TestTransactionError:
    def test_default_response_code(self):
        err = TransactionError("fail")
        assert err.response_code == 0
        assert str(err) == "fail"

    def test_custom_response_code(self):
        err = TransactionError("bad prop", response_code=0x201C)
        assert err.response_code == 0x201C
        assert "bad prop" in str(err)

    def test_catchable_as_base(self):
        with pytest.raises(SonyCameraError):
            raise TransactionError("test", response_code=0x2002)


class TestExceptionMessages:
    def test_connection_error_message(self):
        err = ConnectionError("USB disconnected")
        assert str(err) == "USB disconnected"

    def test_property_error_message(self):
        err = PropertyError("Cannot set F_NUMBER")
        assert "F_NUMBER" in str(err)

    def test_timeout_error(self):
        err = TimeoutError("Shutter timed out")
        assert "timed out" in str(err)

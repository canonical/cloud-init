# This file is part of cloud-init. See LICENSE file for license information.

from typing import Type

try:
    from serial import Serial as _Serial

    Serial: Type
except ImportError:
    # For older versions of python (ie 2.6) pyserial may not exist and/or
    # work and/or be installed, so make a dummy/fake serial that blows up
    # when used...
    class FakeSerial(object):
        def __init__(self, *args, **kwargs):
            pass

        @staticmethod
        def isOpen():
            return False

        @staticmethod
        def write(data):
            raise IOError(
                "Unable to perform serial `write` operation,"
                " pyserial not installed."
            )

        @staticmethod
        def readline():
            raise IOError(
                "Unable to perform serial `readline` operation,"
                " pyserial not installed."
            )

        @staticmethod
        def flush():
            raise IOError(
                "Unable to perform serial `flush` operation,"
                " pyserial not installed."
            )

        @staticmethod
        def read(size=1):
            raise IOError(
                "Unable to perform serial `read` operation,"
                " pyserial not installed."
            )

    Serial = FakeSerial
else:
    Serial = _Serial


# vi: ts=4 expandtab

# This file is part of cloud-init. See LICENSE file for license information.

from __future__ import absolute_import

try:
    from serial import Serial
except ImportError:
    # For older versions of python (ie 2.6) pyserial may not exist and/or
    # work and/or be installed, so make a dummy/fake serial that blows up
    # when used...
    class Serial(object):
        def __init__(self, *args, **kwargs):
            pass

        @staticmethod
        def isOpen():
            return False

        @staticmethod
        def write(data):
            raise IOError("Unable to perform serial `write` operation,"
                          " pyserial not installed.")

        @staticmethod
        def readline():
            raise IOError("Unable to perform serial `readline` operation,"
                          " pyserial not installed.")

        @staticmethod
        def flush():
            raise IOError("Unable to perform serial `flush` operation,"
                          " pyserial not installed.")

        @staticmethod
        def read(size=1):
            raise IOError("Unable to perform serial `read` operation,"
                          " pyserial not installed.")

# vi: ts=4 expandtab

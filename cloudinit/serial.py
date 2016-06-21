# vi: ts=4 expandtab
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License version 3, as
#    published by the Free Software Foundation.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.


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

# vi: ts=4 expandtab
#
#    Copyright (C) 2014 CloudSigma
#
#    Author: Kiril Vladimiroff <kiril.vladimiroff@cloudsigma.com>
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
"""
cepko implements easy-to-use communication with CloudSigma's VMs through
a virtual serial port without bothering with formatting the messages
properly nor parsing the output with the specific and sometimes
confusing shell tools for that purpose.

Having the server definition accessible by the VM can ve useful in various
ways. For example it is possible to easily determine from within the VM,
which network interfaces are connected to public and which to private network.
Another use is to pass some data to initial VM setup scripts, like setting the
hostname to the VM name or passing ssh public keys through server meta.

For more information take a look at the Server Context section of CloudSigma
API Docs: http://cloudsigma-docs.readthedocs.org/en/latest/server_context.html
"""
import json
import platform

import serial

# these high timeouts are necessary as read may read a lot of data.
READ_TIMEOUT = 60
WRITE_TIMEOUT = 10

SERIAL_PORT = '/dev/ttyS1'
if platform.system() == 'Windows':
    SERIAL_PORT = 'COM2'


class Cepko(object):
    """
    One instance of that object could be use for one or more
    queries to the serial port.
    """
    request_pattern = "<\n{}\n>"

    def get(self, key="", request_pattern=None):
        if request_pattern is None:
            request_pattern = self.request_pattern
        return CepkoResult(request_pattern.format(key))

    def all(self):
        return self.get()

    def meta(self, key=""):
        request_pattern = self.request_pattern.format("/meta/{}")
        return self.get(key, request_pattern)

    def global_context(self, key=""):
        request_pattern = self.request_pattern.format("/global_context/{}")
        return self.get(key, request_pattern)


class CepkoResult(object):
    """
    CepkoResult executes the request to the virtual serial port as soon
    as the instance is initialized and stores the result in both raw and
    marshalled format.
    """
    def __init__(self, request):
        self.request = request
        self.raw_result = self._execute()
        self.result = self._marshal(self.raw_result)

    def _execute(self):
        connection = serial.Serial(port=SERIAL_PORT,
                                   timeout=READ_TIMEOUT,
                                   writeTimeout=WRITE_TIMEOUT)
        connection.write(self.request)
        return connection.readline().strip('\x04\n')

    def _marshal(self, raw_result):
        try:
            return json.loads(raw_result)
        except ValueError:
            return raw_result

    def __len__(self):
        return self.result.__len__()

    def __getitem__(self, key):
        return self.result.__getitem__(key)

    def __contains__(self, item):
        return self.result.__contains__(item)

    def __iter__(self):
        return self.result.__iter__()

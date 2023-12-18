#!/usr/bin/python3

import subprocess
import re
import os
import socket
from StringIO import StringIO

hostname_conf_fn = "/tmp/hosts"
resolve_conf_fn = "/tmp/resolv.conf"


BASE_NET_CFG = '''
auto lo
iface lo inet loopback

auto eth1
iface eth1 inet static
    address 192.168.1.5
    netmask 255.255.255.0
    network 192.168.1.0
    broadcast 192.168.1.255
    gateway 192.168.1.254

#auto eth1
#iface eth1 inet dhcp

dns-nameservers 9.3.1.200
dns-search aus.stglabs.ibm.com
'''

class ProcessExecutionError(IOError):

    MESSAGE_TMPL = ('%(description)s\n'
                    'Command: %(cmd)s\n'
                    'Exit code: %(exit_code)s\n'
                    'Reason: %(reason)s\n'
                    'Stdout: %(stdout)r\n'
                    'Stderr: %(stderr)r')

    def __init__(self, stdout=None, stderr=None,
                 exit_code=None, cmd=None,
                 description=None, reason=None):
        print("SCOTT::DEBUG :: /usr/opt/python3/lib/python3.9/site-packages/cloudinit/util.py : CLASS ProcessExecutionError : __init__() : begin")
        if not cmd:
            self.cmd = '-'
        else:
            self.cmd = cmd

        if not description:
            self.description = 'Unexpected error while running command.'
        else:
            self.description = description

        if not isinstance(exit_code, (long, int)):
            self.exit_code = '-'
        else:
            self.exit_code = exit_code

        if not stderr:
            self.stderr = ''
        else:
            self.stderr = stderr

        if not stdout:
            self.stdout = ''
        else:
            self.stdout = stdout

        if reason:
            self.reason = reason
        else:
            self.reason = '-'

        message = self.MESSAGE_TMPL % {
            'description': self.description,
            'cmd': self.cmd,
            'exit_code': self.exit_code,
            'stdout': self.stdout,
            'stderr': self.stderr,
            'reason': self.reason,
        }
        print("SCOTT::DEBUG :: /usr/opt/python3/lib/python3.9/site-packages/cloudinit/util.py : CLASS ProcessExecutionError : __init__() : message=%s" % message)
        print("SCOTT::DEBUG :: /usr/opt/python3/lib/python3.9/site-packages/cloudinit/util.py : CLASS ProcessExecutionError : __init__() : end")
        IOError.__init__(self, message)


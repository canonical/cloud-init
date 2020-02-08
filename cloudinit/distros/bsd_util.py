# This file is part of cloud-init. See LICENSE file for license information.

import shlex

from cloudinit import util

# On NetBSD, /etc/rc.conf comes with a if block:
#   if [ -r /etc/defaults/rc.conf ]; then
# as a consequence, the file is not a regular key/value list
# anymore and we cannot use cloudinit.distros.parsers.sys_conf
# The module comes with a more naive parser, but is able to
# preserve these if blocks.


def get_rc_config_value(key, fn='/etc/rc.conf'):
    contents = {}
    for line in util.load_file(fn).splitlines():
        if '=' in line:
            k, v = line.split('=', 1)
            contents[k] = v
    return contents.get(key)


def set_rc_config_value(key, value, fn='/etc/rc.conf'):
    lines = []
    done = False
    value = shlex.quote(value)
    for line in util.load_file(fn).splitlines():
        if '=' in line:
            k, v = line.split('=', 1)
            if k == key:
                v = value
                done = True
            lines.append('='.join([k, v]))
        else:
            lines.append(line)
    if not done:
        lines.append('='.join([key, value]))
    with open(fn, 'w') as fd:
        fd.write('\n'.join(lines) + '\n')


# vi: ts=4 expandtab

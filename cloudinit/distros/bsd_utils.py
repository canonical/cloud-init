# This file is part of cloud-init. See LICENSE file for license information.

import shlex

from cloudinit import util

# On NetBSD, /etc/rc.conf comes with a if block:
#   if [ -r /etc/defaults/rc.conf ]; then
# as a consequence, the file is not a regular key/value list
# anymore and we cannot use cloudinit.distros.parsers.sys_conf
# The module comes with a more naive parser, but is able to
# preserve these if blocks.


def _unquote(value):
    if value[0] == value[-1] and value[0] in ['"', "'"]:
        return value[1:-1]
    return value


def get_rc_config_value(key, fn="/etc/rc.conf"):
    key_prefix = "{}=".format(key)
    for line in util.load_text_file(fn).splitlines():
        if line.startswith(key_prefix):
            value = line.replace(key_prefix, "")
            return _unquote(value)


def set_rc_config_value(key, value, fn="/etc/rc.conf"):
    lines = []
    done = False
    value = shlex.quote(value)
    original_content = util.load_text_file(fn)
    for line in original_content.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            if k == key:
                v = value
                done = True
            lines.append("=".join([k, v]))
        else:
            lines.append(line)
    if not done:
        lines.append("=".join([key, value]))
    new_content = "\n".join(lines) + "\n"
    if new_content != original_content:
        util.write_file(fn, new_content)

#!/usr/bin/python
# vi: ts=4 expandtab
#
#    Copyright (C) 2009-2010 Canonical Ltd.
#
#    Author: Scott Moser <scott.moser@canonical.com>
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

import sys
import cloudinit

def Usage(out = sys.stdout):
    out.write("Usage: %s name\n" % sys.argv[0])
    
def main():
    # expect to be called with
    #   name freq [ args ]
    if len(sys.argv) < 2:
        Usage(sys.stderr)
        sys.exit(1)

    name=sys.argv[1]
    run_args=sys.argv[2:]

    import cloudinit.CloudConfig
    import os

    cfg_path = cloudinit.cloud_config
    cfg_env_name = cloudinit.cfg_env_name
    if os.environ.has_key(cfg_env_name):
        cfg_path = os.environ[cfg_env_name]

    cc = cloudinit.CloudConfig.CloudConfig(cfg_path)

    try:
        cc.handle(name,run_args)
    except:
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.stderr.write("config handling of %s failed\n" % name)
        sys.exit(1)

    sys.exit(0)

if __name__ == '__main__':
    main()

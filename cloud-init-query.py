#!/usr/bin/python
# vi: ts=4 expandtab
#
#    Copyright (C) 2009-2010 Canonical Ltd.
#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Juerg Haefliger <juerg.haefliger@hp.com>
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
import cloudinit.CloudConfig


def Usage(out=sys.stdout):
    out.write("Usage: %s name\n" % sys.argv[0])


def main():
    # expect to be called with name of item to fetch
    if len(sys.argv) != 2:
        Usage(sys.stderr)
        sys.exit(1)

    cfg_path = cloudinit.get_ipath_cur("cloud_config")
    cc = cloudinit.CloudConfig.CloudConfig(cfg_path)
    data = {
        'user_data': cc.cloud.get_userdata(),
        'user_data_raw': cc.cloud.get_userdata_raw(),
        'instance_id': cc.cloud.get_instance_id(),
    }

    name = sys.argv[1].replace('-', '_')

    if name not in data:
        sys.stderr.write("unknown name '%s'.  Known values are:\n  %s\n" %
            (sys.argv[1], ' '.join(data.keys())))
        sys.exit(1)

    print data[name]
    sys.exit(0)

if __name__ == '__main__':
    main()

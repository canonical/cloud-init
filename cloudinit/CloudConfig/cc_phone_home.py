# vi: ts=4 expandtab
#
#    Copyright (C) 2011 Canonical Ltd.
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
from cloudinit.CloudConfig import per_instance
import cloudinit.util as util
frequency = per_instance

def handle(name,cfg,cloud,log,args):
    if len(args) != 0:
        value = args[0]
    else:
        value = util.get_cfg_option_str(cfg,"phone_home_url",False)

    if not value:
        return

    # TODO:
    # implement phone_home
    # pass to it
    #  - ssh key fingerprints
    #  - mac addr ?
    #  - ip address
    #  
    log.warn("TODO: write cc_phone_home")
    return

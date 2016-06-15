#   Copyright (C) 2013-2014 Canonical Ltd.
#
#   Author: Scott Moser <scott.moser@canonical.com>
#   Author: Blake Rouse <blake.rouse@canonical.com>
#
#   Curtin is free software: you can redistribute it and/or modify it under
#   the terms of the GNU Affero General Public License as published by the
#   Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   Curtin is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for
#   more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with Curtin.  If not, see <http://www.gnu.org/licenses/>.

import six

from .udev import generate_udev_rule


def filter_by_type(match_type):
    return lambda iface: match_type == iface['type']


def filter_by_name(match_name):
    return lambda iface: match_name == iface['name']


filter_by_physical = filter_by_type('physical')


class Renderer(object):

    @staticmethod
    def _render_persistent_net(network_state):
        """Given state, emit udev rules to map mac to ifname."""
        # TODO(harlowja): this seems shared between eni renderer and
        # this, so move it to a shared location.
        content = six.StringIO()
        for iface in network_state.iter_interfaces(filter_by_physical):
            # for physical interfaces write out a persist net udev rule
            if 'name' in iface and iface.get('mac_address'):
                content.write(generate_udev_rule(iface['name'],
                                                 iface['mac_address']))
        return content.getvalue()

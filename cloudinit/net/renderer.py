# Copyright (C) 2013-2014 Canonical Ltd.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Blake Rouse <blake.rouse@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import abc
import six

from .network_state import parse_net_config_data
from .udev import generate_udev_rule


def filter_by_type(match_type):
    return lambda iface: match_type == iface['type']


def filter_by_name(match_name):
    return lambda iface: match_name == iface['name']


def filter_by_attr(match_name):
    return lambda iface: (match_name in iface and iface[match_name])


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
                driver = iface.get('driver', None)
                content.write(generate_udev_rule(iface['name'],
                                                 iface['mac_address'],
                                                 driver=driver))
        return content.getvalue()

    @abc.abstractmethod
    def render_network_state(self, network_state, templates=None,
                             target=None):
        """Render network state."""

    def render_network_config(self, network_config, templates=None,
                              target=None):
        return self.render_network_state(
            network_state=parse_net_config_data(network_config),
            templates=templates, target=target)

# vi: ts=4 expandtab

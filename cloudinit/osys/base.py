# Copyright (C) 2015 Canonical Ltd.
# Copyright 2015 Cloudbase Solutions Srl
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Claudiu Popa <cpopa@cloudbasesolutions.com>
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import abc
import importlib
import platform

import six


__all__ = (
    'get_osutils',
    'OSUtils',
)


def get_osutils():
    """Obtain the OS utils object for the underlying platform."""
    name, _, _ = platform.linux_distribution()
    if not name:
        name = platform.system()

    name = name.lower()
    location = "cloudinit.osys.{0}.base".format(name)
    module = importlib.import_module(location)
    return module.OSUtils


@six.add_metaclass(abc.ABCMeta)
class OSUtils(object):
    """Base class for an OS utils namespace.

    This base class provides a couple of hooks
    which needs to be implemented by subclasses, for each
    particular OS and distro.
    """

    name = None

    @abc.abstractproperty
    def network(self):
        """Get the network object for the underlying platform."""

    @abc.abstractproperty
    def filesystem(self):
        """Get the filesystem object for the underlying platform."""

    @abc.abstractproperty
    def users(self):
        """Get the users object for the underlying platform."""

    @abc.abstractproperty
    def general(self):
        """Get the general object for the underlying platform."""

    @abc.abstractproperty
    def user_class(self):
        """Get the user class specific to this operating system."""

    @abc.abstractproperty
    def route_class(self):
        """Get the route class specific to this operating system."""

    @abc.abstractproperty
    def interface_class(self):
        """Get the interface class specific to this operating system."""

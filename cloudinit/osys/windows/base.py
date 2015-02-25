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

from cloudinit.osys import base
from cloudinit.osys.windows import filesystem as filesystem_module
from cloudinit.osys.windows import general as general_module
from cloudinit.osys.windows import network as network_module
from cloudinit.osys.windows import users as users_module


__all__ = ('OSUtils', )


class OSUtils(base.OSUtils):
    """The OS utils namespace for the Windows platform."""

    name = "windows"

    network = network_module.Network()
    filesystem = filesystem_module.Filesystem()
    users = users_module.Users()
    general = general_module.General()
    user_class = users_module.User
    route_class = network_module.Route
    interface_class = network_module.Interface

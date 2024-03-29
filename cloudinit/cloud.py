# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
# Copyright (C) 2012 Yahoo! Inc.
#
# This file is part of cloud-init. See LICENSE file for license information.

import copy
import logging
import os
from typing import Optional

from cloudinit.distros import Distro
from cloudinit.helpers import Paths, Runners
from cloudinit.reporting import events
from cloudinit.sources import DataSource

LOG = logging.getLogger(__name__)

# This class is the high level wrapper that provides
# access to cloud-init objects without exposing the stage objects
# to handler and or module manipulation. It allows for cloud
# init to restrict what those types of user facing code may see
# and or adjust (which helps avoid code messing with each other)
#
# It also provides util functions that avoid having to know
# how to get a certain member from this submembers as well
# as providing a backwards compatible object that can be maintained
# while the stages/other objects can be worked on independently...


class Cloud:
    def __init__(
        self,
        datasource: DataSource,
        paths: Paths,
        cfg: dict,
        distro: Distro,
        runners: Runners,
        reporter: Optional[events.ReportEventStack] = None,
    ):
        self.datasource = datasource
        self.paths = paths
        self.distro = distro
        self._cfg = cfg
        self._runners = runners
        if reporter is None:
            reporter = events.ReportEventStack(
                name="unnamed-cloud-reporter",
                description="unnamed-cloud-reporter",
                reporting_enabled=False,
            )
        self.reporter = reporter

    @property
    def cfg(self):
        # Ensure that cfg is not indirectly modified
        return copy.deepcopy(self._cfg)

    def run(self, name, functor, args, freq=None, clear_on_fail=False):
        """Run a function gated by a named semaphore for a desired frequency.

        The typical case for this method would be to limit running of the
        provided func to a single well-defined frequency:
            PER_INSTANCE, PER_BOOT or PER_ONCE

        The semaphore provides a gate that persists across cloud-init
        boot stage boundaries so multiple modules can share this state
        even if they happen to be run in different boot stages or across
        reboots.
        """
        return self._runners.run(name, functor, args, freq, clear_on_fail)

    def get_template_filename(self, name):
        fn = self.paths.template_tpl % (name)
        if not os.path.isfile(fn):
            LOG.warning(
                "No template found in %s for template named %s",
                os.path.dirname(fn),
                name,
            )
            return None
        return fn

    # The rest of these are just useful proxies
    def get_userdata(self, apply_filter=True):
        return self.datasource.get_userdata(apply_filter)

    def get_instance_id(self):
        return self.datasource.get_instance_id()

    @property
    def launch_index(self):
        return self.datasource.launch_index

    def get_public_ssh_keys(self):
        return self.datasource.get_public_ssh_keys()

    def get_locale(self):
        return self.datasource.get_locale()

    def get_hostname(self, fqdn=False, metadata_only=False):
        return self.datasource.get_hostname(
            fqdn=fqdn, metadata_only=metadata_only
        )

    def device_name_to_device(self, name):
        return self.datasource.device_name_to_device(name)

    def get_ipath_cur(self, name=None):
        return self.paths.get_ipath_cur(name)

    def get_cpath(self, name=None):
        return self.paths.get_cpath(name)

    def get_ipath(self, name=None):
        return self.paths.get_ipath(name)

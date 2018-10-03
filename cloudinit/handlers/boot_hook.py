# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import os

from cloudinit import handlers
from cloudinit import log as logging
from cloudinit import util

from cloudinit.settings import (PER_ALWAYS)

LOG = logging.getLogger(__name__)


class BootHookPartHandler(handlers.Handler):

    # The content prefixes this handler understands.
    prefixes = ['#cloud-boothook']

    def __init__(self, paths, datasource, **_kwargs):
        handlers.Handler.__init__(self, PER_ALWAYS)
        self.boothook_dir = paths.get_ipath("boothooks")
        self.instance_id = None
        if datasource:
            self.instance_id = datasource.get_instance_id()

    def _write_part(self, payload, filename):
        filename = util.clean_filename(filename)
        filepath = os.path.join(self.boothook_dir, filename)
        contents = util.strip_prefix_suffix(util.dos2unix(payload),
                                            prefix=self.prefixes[0])
        util.write_file(filepath, contents.lstrip(), 0o700)
        return filepath

    def handle_part(self, data, ctype, filename, payload, frequency):
        if ctype in handlers.CONTENT_SIGNALS:
            return

        filepath = self._write_part(payload, filename)
        try:
            env = os.environ.copy()
            if self.instance_id is not None:
                env['INSTANCE_ID'] = str(self.instance_id)
            util.subp([filepath], env=env)
        except util.ProcessExecutionError:
            util.logexc(LOG, "Boothooks script %s execution error", filepath)
        except Exception:
            util.logexc(LOG, "Boothooks unknown error when running %s",
                        filepath)

# vi: ts=4 expandtab

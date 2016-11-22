# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import copy

from cloudinit import log as logging
from cloudinit import user_data as ud
from cloudinit import util

LOG = logging.getLogger(__name__)


class Filter(object):
    def __init__(self, wanted_idx, allow_none=True):
        self.wanted_idx = wanted_idx
        self.allow_none = allow_none

    def _select(self, message):
        msg_idx = message.get('Launch-Index', None)
        if self.allow_none and msg_idx is None:
            return True
        msg_idx = util.safe_int(msg_idx)
        if msg_idx != self.wanted_idx:
            return False
        return True

    def _do_filter(self, message):
        # Don't use walk() here since we want to do the reforming of the
        # messages ourselves and not flatten the message listings...
        if not self._select(message):
            return None
        if message.is_multipart():
            # Recreate it and its child messages
            prev_msgs = message.get_payload(decode=False)
            new_msgs = []
            discarded = 0
            for m in prev_msgs:
                m = self._do_filter(m)
                if m is not None:
                    new_msgs.append(m)
                else:
                    discarded += 1
            LOG.debug(("Discarding %s multipart messages "
                       "which do not match launch index %s"),
                      discarded, self.wanted_idx)
            new_message = copy.copy(message)
            new_message.set_payload(new_msgs)
            new_message[ud.ATTACHMENT_FIELD] = str(len(new_msgs))
            return new_message
        else:
            return copy.copy(message)

    def apply(self, root_message):
        if self.wanted_idx is None:
            return root_message
        return self._do_filter(root_message)

# vi: ts=4 expandtab

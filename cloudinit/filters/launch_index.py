# vi: ts=4 expandtab
#
#    Copyright (C) 2012 Canonical Ltd.
#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#    Copyright (C) 2012 Yahoo! Inc.
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Juerg Haefliger <juerg.haefliger@hp.com>
#    Author: Joshua Harlow <harlowja@yahoo-inc.com>
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
        if ud.is_skippable(message):
            return False
        msg_idx = message.get('Launch-Index', None)
        if self.allow_none and msg_idx is None:
            return True
        msg_idx = util.safe_int(msg_idx)
        if msg_idx != self.wanted_idx:
            return False
        return True

    def apply(self, base_message):
        if not base_message.is_multipart() or self.wanted_idx is None:
            return base_message
        prev_msgs = base_message.get_payload(decode=False)
        to_attach = []
        for sub_msg in base_message.walk():
            if self._select(sub_msg):
                to_attach.append(sub_msg)
        if len(prev_msgs) != len(to_attach):
            LOG.debug(("Discarding %s multipart messages "
                       "which do not match launch index %s"),
                      (len(prev_msgs) - len(to_attach)), self.wanted_idx)
        filtered_msg = copy.deepcopy(base_message)
        filtered_msg.set_payload(to_attach)
        filtered_msg[ud.ATTACHMENT_FIELD] = str(len(to_attach))
        return filtered_msg

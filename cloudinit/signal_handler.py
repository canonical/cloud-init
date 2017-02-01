# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import inspect
import signal
import sys

from six import StringIO

from cloudinit import log as logging
from cloudinit import util
from cloudinit import version as vr

LOG = logging.getLogger(__name__)


BACK_FRAME_TRACE_DEPTH = 3
EXIT_FOR = {
    signal.SIGINT: ('Cloud-init %(version)s received SIGINT, exiting...', 1),
    signal.SIGTERM: ('Cloud-init %(version)s received SIGTERM, exiting...', 1),
    # Can't be caught...
    # signal.SIGKILL: ('Cloud-init killed, exiting...', 1),
    signal.SIGABRT: ('Cloud-init %(version)s received SIGABRT, exiting...', 1),
}


def _pprint_frame(frame, depth, max_depth, contents):
    if depth > max_depth or not frame:
        return
    frame_info = inspect.getframeinfo(frame)
    prefix = " " * (depth * 2)
    contents.write("%sFilename: %s\n" % (prefix, frame_info.filename))
    contents.write("%sFunction: %s\n" % (prefix, frame_info.function))
    contents.write("%sLine number: %s\n" % (prefix, frame_info.lineno))
    _pprint_frame(frame.f_back, depth + 1, max_depth, contents)


def _handle_exit(signum, frame):
    (msg, rc) = EXIT_FOR[signum]
    msg = msg % ({'version': vr.version_string()})
    contents = StringIO()
    contents.write("%s\n" % (msg))
    _pprint_frame(frame, 1, BACK_FRAME_TRACE_DEPTH, contents)
    util.multi_log(contents.getvalue(),
                   console=True, stderr=False, log=LOG)
    sys.exit(rc)


def attach_handlers():
    sigs_attached = 0
    for signum in EXIT_FOR.keys():
        signal.signal(signum, _handle_exit)
    sigs_attached += len(EXIT_FOR)
    return sigs_attached

# vi: ts=4 expandtab

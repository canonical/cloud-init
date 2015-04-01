# Copyright (C) 2015 Canonical Ltd.
# Copyright (C) 2015 Cloudbase Solutions Srl
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

__all__ = ('abstractclassmethod', )


import logging
import subprocess

import six

from cloudinit import exceptions


LOG = logging.getLogger(__name__)


class abstractclassmethod(classmethod):
    """A backport for abc.abstractclassmethod from Python 3."""

    __isabstractmethod__ = True

    def __init__(self, func):
        func.__isabstractmethod__ = True
        super(abstractclassmethod, self).__init__(func)


def subp(args, data=None, rcs=None, env=None, capture=True, shell=False,
         logstring=False):
    if rcs is None:
        rcs = [0]
    try:

        if not logstring:
            LOG.debug(("Running command %s with allowed return codes %s"
                       " (shell=%s, capture=%s)"), args, rcs, shell, capture)
        else:
            LOG.debug(("Running hidden command to protect sensitive "
                       "input/output logstring: %s"), logstring)

        if not capture:
            stdout = None
            stderr = None
        else:
            stdout = subprocess.PIPE
            stderr = subprocess.PIPE
        stdin = subprocess.PIPE
        kws = dict(stdout=stdout, stderr=stderr, stdin=stdin,
                   env=env, shell=shell)
        if six.PY3:
            # Use this so subprocess output will be (Python 3) str, not bytes.
            kws['universal_newlines'] = True
        sp = subprocess.Popen(args, **kws)
        (out, err) = sp.communicate(data)
    except OSError as exc:
        raise exceptions.ProcessExecutionError(cmd=args, reason=exc)
    rc = sp.returncode
    if rc not in rcs:
        raise exceptions.ProcessExecutionError(
            stdout=out, stderr=err,
            exit_code=rc, cmd=args)
    # Just ensure blank instead of none?? (iff capturing)
    if not out and capture:
        out = ''
    if not err and capture:
        err = ''
    return (out, err)

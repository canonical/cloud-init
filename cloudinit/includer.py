import os
import re

from cloudinit import downloader as down
from cloudinit import exceptions as excp
from cloudinit import log as logging
from cloudinit import shell as sh

INCLUDE_PATT = re.compile("^#(opt_include|include)[ \t](.*)$", re.MULTILINE)
OPT_PATS = ['opt_include']

LOG = logging.getLogger(__name__)


class Includer(object):

    def __init__(self, root_fn, stack_limit=10):
        self.root_fn = root_fn
        self.stack_limit = stack_limit

    def _read_file(self, fname):
        return sh.read_file(fname)

    def _read(self, fname, stack, rel):
        if len(stack) >= self.stack_limit:
            raise excp.StackExceeded("Stack limit of %s reached while including %s" % (self.stack_limit, fname))

        canon_fname = self._canon_name(fname, rel)
        if canon_fname in stack:
            raise excp.RecursiveInclude("File %s recursively included" % (canon_fname))

        stack.add(canon_fname)
        new_rel = os.path.dirname(canon_fname)
        contents = self._read_file(canon_fname)

        def include_cb(match):
            is_optional = (match.group(1).lower() in OPT_PATS)
            fn = match.group(2).strip()
            if not fn:
                # Should we die??
                return match.group(0)
            else:
                try:
                    LOG.debug("Including file %s", fn)
                    return self._read(fn, stack, new_rel)
                except IOError:
                    if is_optional:
                        return ''
                    else:
                        raise

        adjusted_contents = INCLUDE_PATT.sub(include_cb, contents)
        stack.remove(fname)
        return adjusted_contents

    def _canon_name(self, fname, rel):
        fname = fname.strip()
        if not fname.startswith("/"):
            fname = os.path.sep.join([rel, fname])
        return os.path.realpath(fname)

    def read(self, relative_to="."):
        stack = set()
        return self._read(self.root_fn, stack, rel=relative_to)
    

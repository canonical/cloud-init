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

from cloudinit import handlers
from cloudinit import log as logging
from cloudinit import mergers
from cloudinit import util

from cloudinit.settings import (PER_ALWAYS)

LOG = logging.getLogger(__name__)

MERGE_HEADER = 'Merge-Type'

# Due to the way the loading of yaml configuration was done previously,
# where previously each cloud config part was appended to a larger yaml
# file and then finally that file was loaded as one big yaml file we need
# to mimic that behavior by altering the default strategy to be replacing
# keys of prior merges.
#
#
# For example
# #file 1
# a: 3
# #file 2
# a: 22
# #combined file (comments not included)
# a: 3
# a: 22
#
# This gets loaded into yaml with final result {'a': 22}
DEF_MERGERS = mergers.string_extract_mergers('dict(replace)+list()+str()')


class CloudConfigPartHandler(handlers.Handler):
    def __init__(self, paths, **_kwargs):
        handlers.Handler.__init__(self, PER_ALWAYS, version=3)
        self.cloud_buf = None
        self.cloud_fn = paths.get_ipath("cloud_config")
        self.file_names = []

    def list_types(self):
        return [
            handlers.type_from_starts_with("#cloud-config"),
        ]

    def _write_cloud_config(self):
        if not self.cloud_fn:
            return
        # Capture which files we merged from...
        file_lines = []
        if self.file_names:
            file_lines.append("# from %s files" % (len(self.file_names)))
            for fn in self.file_names:
                if not fn:
                    fn = '?'
                file_lines.append("# %s" % (fn))
            file_lines.append("")
        if self.cloud_buf is not None:
            # Something was actually gathered....
            lines = [
                "#cloud-config",
                '',
            ]
            lines.extend(file_lines)
            lines.append(util.yaml_dumps(self.cloud_buf))
        else:
            lines = []
        util.write_file(self.cloud_fn, "\n".join(lines), 0600)

    def _extract_mergers(self, payload, headers):
        merge_header_headers = ''
        for h in [MERGE_HEADER, 'X-%s' % (MERGE_HEADER)]:
            tmp_h = headers.get(h, '')
            if tmp_h:
                merge_header_headers = tmp_h
                break
        # Select either the merge-type from the content
        # or the merge type from the headers or default to our own set
        # if neither exists (or is empty) from the later.
        payload_yaml = util.load_yaml(payload)
        mergers_yaml = mergers.dict_extract_mergers(payload_yaml)
        mergers_header = mergers.string_extract_mergers(merge_header_headers)
        all_mergers = []
        all_mergers.extend(mergers_yaml)
        all_mergers.extend(mergers_header)
        if not all_mergers:
            all_mergers = DEF_MERGERS
        return (payload_yaml, all_mergers)

    def _merge_part(self, payload, headers):
        (payload_yaml, my_mergers) = self._extract_mergers(payload, headers)
        LOG.debug("Merging by applying %s", my_mergers)
        merger = mergers.construct(my_mergers)
        if self.cloud_buf is None:
            # First time through, merge with an empty dict...
            self.cloud_buf = {}
        self.cloud_buf = merger.merge(self.cloud_buf, payload_yaml)

    def _reset(self):
        self.file_names = []
        self.cloud_buf = None

    def handle_part(self, _data, ctype, filename,  # pylint: disable=W0221
                    payload, _frequency, headers):  # pylint: disable=W0613
        if ctype == handlers.CONTENT_START:
            self._reset()
            return
        if ctype == handlers.CONTENT_END:
            self._write_cloud_config()
            self._reset()
            return
        try:
            self._merge_part(payload, headers)
            # Ensure filename is ok to store
            for i in ("\n", "\r", "\t"):
                filename = filename.replace(i, " ")
            self.file_names.append(filename.strip())
        except:
            util.logexc(LOG, "Failed at merging in cloud config part from %s",
                        filename)

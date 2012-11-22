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

DEF_MERGE_TYPE = "list+dict+str"
MERGE_HEADER = 'Merge-Type'


class CloudConfigPartHandler(handlers.Handler):
    def __init__(self, paths, **_kwargs):
        handlers.Handler.__init__(self, PER_ALWAYS, version=3)
        self.cloud_buf = {}
        self.cloud_fn = paths.get_ipath("cloud_config")
        self.file_names = []

    def list_types(self):
        return [
            handlers.type_from_starts_with("#cloud-config"),
        ]

    def _write_cloud_config(self, buf):
        if not self.cloud_fn:
            return
        # Write the combined & merged dictionary/yaml out
        lines = [
            "#cloud-config",
            '',
        ]
        # Write which files we merged from
        if self.file_names:
            lines.append("# from %s files" % (len(self.file_names)))
            for fn in self.file_names:
                lines.append("# %s" % (fn))
            lines.append("")
        lines.append(util.yaml_dumps(self.cloud_buf))
        util.write_file(self.cloud_fn, "\n".join(lines), 0600)

    def _merge_header_extract(self, payload_yaml):
        merge_header_yaml = ''
        for k in [MERGE_HEADER, MERGE_HEADER.lower(),
                  MERGE_HEADER.lower().replace("-", "_")]:
            if k in payload_yaml:
                merge_header_yaml = str(payload_yaml[k])
                break
        return merge_header_yaml

    def _merge_part(self, payload, headers):
        merge_header_headers = headers.get(MERGE_HEADER, '')
        payload_yaml = util.load_yaml(payload)
        merge_how = ''
        # Select either the merge-type from the content
        # or the merge type from the headers or default to our own set
        # if neither exists (or is empty) from the later
        merge_header_yaml = self._merge_header_extract(payload_yaml)
        for merge_i in [merge_header_yaml, merge_header_headers]:
            merge_i = merge_i.strip().lower()
            if merge_i:
                merge_how = merge_i
                break
        if not merge_how:
            merge_how = DEF_MERGE_TYPE
        merger = mergers.construct(merge_how)
        self.cloud_buf = merger.merge(self.cloud_buf, payload_yaml)

    def _reset(self):
        self.file_names = []
        self.cloud_buf = {}

    def handle_part(self, _data, ctype, filename, payload, _freq, headers):
        if ctype == handlers.CONTENT_START:
            self._reset()
            return
        if ctype == handlers.CONTENT_END:
            self._write_cloud_config(self.cloud_buf)
            self._reset()
            return
        try:
            self._merge_part(payload, headers)
            self.file_names.append(filename)
        except:
            util.logexc(LOG, "Failed at merging in cloud config part from %s",
                        filename)

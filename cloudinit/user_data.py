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

import os

import email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase

from cloudinit import handlers
from cloudinit import log as logging
from cloudinit import url_helper
from cloudinit import util

LOG = logging.getLogger(__name__)

# Constants copied in from the handler module
NOT_MULTIPART_TYPE = handlers.NOT_MULTIPART_TYPE
PART_FN_TPL = handlers.PART_FN_TPL
OCTET_TYPE = handlers.OCTET_TYPE

# Saves typing errors
CONTENT_TYPE = 'Content-Type'

# Various special content types that cause special actions
TYPE_NEEDED = ["text/plain", "text/x-not-multipart"]
INCLUDE_TYPES = ['text/x-include-url', 'text/x-include-once-url']
ARCHIVE_TYPES = ["text/cloud-config-archive"]
UNDEF_TYPE = "text/plain"
ARCHIVE_UNDEF_TYPE = "text/cloud-config"

# Msg header used to track attachments
ATTACHMENT_FIELD = 'Number-Attachments'


class UserDataProcessor(object):
    def __init__(self, paths):
        self.paths = paths

    def process(self, blob):
        base_msg = convert_string(blob)
        process_msg = MIMEMultipart()
        self._process_msg(base_msg, process_msg)
        return process_msg

    def _process_msg(self, base_msg, append_msg):
        for part in base_msg.walk():
            # multipart/* are just containers
            if part.get_content_maintype() == 'multipart':
                continue

            ctype = None
            ctype_orig = part.get_content_type()
            payload = part.get_payload(decode=True)

            if not ctype_orig:
                ctype_orig = UNDEF_TYPE

            if ctype_orig in TYPE_NEEDED:
                ctype = handlers.type_from_starts_with(payload)

            if ctype is None:
                ctype = ctype_orig

            if ctype in INCLUDE_TYPES:
                self._do_include(payload, append_msg)
                continue

            if ctype in ARCHIVE_TYPES:
                self._explode_archive(payload, append_msg)
                continue

            if CONTENT_TYPE in base_msg:
                base_msg.replace_header(CONTENT_TYPE, ctype)
            else:
                base_msg[CONTENT_TYPE] = ctype

            self._attach_part(append_msg, part)

    def _get_include_once_filename(self, entry):
        entry_fn = util.hash_blob(entry, 'md5', 64)
        return os.path.join(self.paths.get_ipath_cur('data'),
                            'urlcache', entry_fn)

    def _do_include(self, content, append_msg):
        # Include a list of urls, one per line
        # also support '#include <url here>'
        # or #include-once '<url here>'
        include_once_on = False
        for line in content.splitlines():
            lc_line = line.lower()
            if lc_line.startswith("#include-once"):
                line = line[len("#include-once"):].lstrip()
                # Every following include will now
                # not be refetched.... but will be
                # re-read from a local urlcache (if it worked)
                include_once_on = True
            elif lc_line.startswith("#include"):
                line = line[len("#include"):].lstrip()
                # Disable the include once if it was on
                # if it wasn't, then this has no effect.
                include_once_on = False
            if line.startswith("#"):
                continue
            include_url = line.strip()
            if not include_url:
                continue

            include_once_fn = None
            content = None
            if include_once_on:
                include_once_fn = self._get_include_once_filename(include_url)
            if include_once_on and os.path.isfile(include_once_fn):
                content = util.load_file(include_once_fn)
            else:
                resp = url_helper.readurl(include_url)
                if include_once_on and resp.ok():
                    util.write_file(include_once_fn, str(resp), mode=0600)
                if resp.ok():
                    content = str(resp)
                else:
                    LOG.warn(("Fetching from %s resulted in"
                              " a invalid http code of %s"),
                             include_url, resp.code)

            if content is not None:
                new_msg = convert_string(content)
                self._process_msg(new_msg, append_msg)

    def _explode_archive(self, archive, append_msg):
        entries = util.load_yaml(archive, default=[], allowed=[list, set])
        for ent in entries:
            # ent can be one of:
            #  dict { 'filename' : 'value', 'content' :
            #       'value', 'type' : 'value' }
            #    filename and type not be present
            # or
            #  scalar(payload)
            if isinstance(ent, (str, basestring)):
                ent = {'content': ent}
            if not isinstance(ent, (dict)):
                # TODO raise?
                continue

            content = ent.get('content', '')
            mtype = ent.get('type')
            if not mtype:
                mtype = handlers.type_from_starts_with(content,
                                                       ARCHIVE_UNDEF_TYPE)

            maintype, subtype = mtype.split('/', 1)
            if maintype == "text":
                msg = MIMEText(content, _subtype=subtype)
            else:
                msg = MIMEBase(maintype, subtype)
                msg.set_payload(content)

            if 'filename' in ent:
                msg.add_header('Content-Disposition',
                               'attachment', filename=ent['filename'])

            for header in list(ent.keys()):
                if header in ('content', 'filename', 'type'):
                    continue
                msg.add_header(header, ent['header'])

            self._attach_part(append_msg, msg)

    def _multi_part_count(self, outer_msg, new_count=None):
        """
        Return the number of attachments to this MIMEMultipart by looking
        at its 'Number-Attachments' header.
        """
        if ATTACHMENT_FIELD not in outer_msg:
            outer_msg[ATTACHMENT_FIELD] = '0'

        if new_count is not None:
            outer_msg.replace_header(ATTACHMENT_FIELD, str(new_count))

        fetched_count = 0
        try:
            fetched_count = int(outer_msg.get(ATTACHMENT_FIELD))
        except (ValueError, TypeError):
            outer_msg.replace_header(ATTACHMENT_FIELD, str(fetched_count))
        return fetched_count

    def _part_filename(self, unnamed_part, count):
        return PART_FN_TPL % (count + 1)

    def _attach_part(self, outer_msg, part):
        """
        Attach an part to an outer message. outermsg must be a MIMEMultipart.
        Modifies a header in the message to keep track of number of attachments.
        """
        cur_c = self._multi_part_count(outer_msg)
        if not part.get_filename():
            fn = self._part_filename(part, cur_c)
            part.add_header('Content-Disposition',
                            'attachment', filename=fn)
        outer_msg.attach(part)
        self._multi_part_count(outer_msg, cur_c + 1)


# Coverts a raw string into a mime message
def convert_string(raw_data, headers=None):
    if not raw_data:
        raw_data = ''
    if not headers:
        headers = {}
    data = util.decomp_str(raw_data)
    if "mime-version:" in data[0:4096].lower():
        msg = email.message_from_string(data)
        for (key, val) in headers.iteritems():
            if key in msg:
                msg.replace_header(key, val)
            else:
                msg[key] = val
    else:
        mtype = headers.get(CONTENT_TYPE, NOT_MULTIPART_TYPE)
        maintype, subtype = mtype.split("/", 1)
        msg = MIMEBase(maintype, subtype, *headers)
        msg.set_payload(data)
    return msg

# vi: ts=4 expandtab
#
#    Copyright (C) 2009-2010 Canonical Ltd.
#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Juerg Hafliger <juerg.haefliger@hp.com>
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

import hashlib
import os
import urllib

import email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase

import yaml

from cloudinit import url_helper
from cloudinit import util


# Different file beginnings to there content type
INCLUSION_TYPES_MAP = {
    '#include': 'text/x-include-url',
    '#include-once': 'text/x-include-once-url',
    '#!': 'text/x-shellscript',
    '#cloud-config': 'text/cloud-config',
    '#upstart-job': 'text/upstart-job',
    '#part-handler': 'text/part-handler',
    '#cloud-boothook': 'text/cloud-boothook',
    '#cloud-config-archive': 'text/cloud-config-archive',
}

# Various special content types
TYPE_NEEDED = ["text/plain", "text/x-not-multipart"]
INCLUDE_TYPES = ['text/x-include-url', 'text/x-include-once-url']
ARCHIVE_TYPES = ["text/cloud-config-archive"]
UNDEF_TYPE = "text/plain"
ARCHIVE_UNDEF_TYPE = "text/cloud-config"
NOT_MULTIPART_TYPE = "text/x-not-multipart"
OCTET_TYPE = 'application/octet-stream'

# Sorted longest first
INCLUSION_SRCH = sorted(INCLUSION_TYPES_MAP.keys(), key=(lambda e: 0 - len(e)))

# Msg header used to track attachments
ATTACHMENT_FIELD = 'Number-Attachments'

# This will be used to create a filename from a url (or like) entry
# When we want to make sure a entry isn't included more than once across sessions.
INCLUDE_ONCE_HASHER = 'md5'

# For those pieces without filenames
PART_FN_TPL = 'part-%03d'


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
                ctype = type_from_starts_with(payload)
    
            if ctype is None:
                ctype = ctype_orig
    
            if ctype in INCLUDE_TYPES:
                self._do_include(payload, append_msg)
                continue
    
            if ctype in ARCHIVE_TYPES:
                self._explode_archive(payload, append_msg)
                continue
    
            if 'Content-Type' in base_msg:
                base_msg.replace_header('Content-Type', ctype)
            else:
                base_msg['Content-Type'] = ctype
    
            self._attach_part(append_msg, part)

    def _get_include_once_filename(self, entry):
        msum = hashlib.new(INCLUDE_ONCE_HASHER)
        msum.update(entry)
        entry_fn = msum.hexdigest()[0:64]  # Don't get to long now
        return os.path.join(self.paths.get_ipath_cur('data'), 'urlcache', entry_fn)

    def _do_include(self, content, append_msg):
        # is just a list of urls, one per line
        # also support '#include <url here>'
        for line in content.splitlines():
            includeonce = False
            if line in ("#include", "#include-once"):
                continue
            if line.startswith("#include-once"):
                line = line[len("#include-once"):].lstrip()
                includeonce = True
            elif line.startswith("#include"):
                line = line[len("#include"):].lstrip()
            if line.startswith("#"):
                continue
            include_url = line.strip()
            if not include_url:
                continue

            includeonce_filename = self._get_include_once_filename(include_url)
            if includeonce and os.path.isfile(includeonce_filename):
                content = util.load_file(includeonce_filename)
            else:
                (content, st) = url_helper.readurl(include_url)
                if includeonce and url_helper.ok_http_code(st):
                    util.write_file(includeonce_filename, content, mode=0600)
                if not url_helper.ok_http_code(st):
                    content = ''

            new_msg = convert_string(content)
            self._process_msg(new_msg, append_msg)

    def _explode_archive(self, archive, append_msg):
        try:
            entries = yaml.load(archive)
        except:
            entries = []
        if not isinstance(entries, (list, set)):
            # TODO raise?
            entries = []

        for ent in entries:
            # ent can be one of:
            #  dict { 'filename' : 'value', 'content' : 'value', 'type' : 'value' }
            #    filename and type not be present
            # or
            #  scalar(payload)
            if isinstance(ent, str):
                ent = {'content': ent}
            if not isinstance(ent, (dict)):
                # TODO raise?
                continue

            content = ent.get('content', '')
            mtype = ent.get('type')
            if not mtype:
                mtype = type_from_starts_with(content, ARCHIVE_UNDEF_TYPE)

            maintype, subtype = mtype.split('/', 1)
            if maintype == "text":
                msg = MIMEText(content, _subtype=subtype)
            else:
                msg = MIMEBase(maintype, subtype)
                msg.set_payload(content)

            if 'filename' in ent:
                msg.add_header('Content-Disposition', 'attachment', filename=ent['filename'])

            for header in ent.keys():
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
            outer_msg[ATTACHMENT_FIELD] = str(0)
    
        if new_count is not None:
            outer_msg.replace_header(ATTACHMENT_FIELD, str(new_count))
    
        fetched_count = 0
        try:
            fetched_count = int(outer_msg.get(ATTACHMENT_FIELD))
        except (ValueError, TypeError):
            outer_msg.replace_header(ATTACHMENT_FIELD, str(fetched_count))
        return fetched_count

    def _attach_part(self, outer_msg, part):
        """
        Attach an part to an outer message. outermsg must be a MIMEMultipart.
        Modifies a header in the message to keep track of number of attachments.
        """
        cur = self._multi_part_count(outer_msg)
        if not part.get_filename():
            part.add_header('Content-Disposition', 'attachment', filename=PART_FN_TPL % (cur + 1))
        outer_msg.attach(part)
        self._multi_part_count(outer_msg, cur + 1)


# Callback is a function that will be called with 
# (data, content_type, filename, payload)
def walk(ud_msg, callback, data):
    partnum = 0
    for part in ud_msg.walk():
        # multipart/* are just containers
        if part.get_content_maintype() == 'multipart':
            continue

        ctype = part.get_content_type()
        if ctype is None:
            ctype = OCTET_TYPE

        filename = part.get_filename()
        if not filename:
            filename = PART_FN_TPL % partnum

        callback(data, ctype, filename, part.get_payload(decode=True))
        partnum = partnum + 1


def convert_string(self, raw_data, headers=None):
    if not data:
        data = ''
    if not headers:
        headers = {}
    data = util.decomp_str(raw_data)
    if "mime-version:" in data[0:4096].lower():
        msg = email.message_from_string(data)
        for (key, val) in headers.items():
            if key in msg:
                msg.replace_header(key, val)
            else:
                msg[key] = val
    else:
        mtype = headers.get("Content-Type", NOT_MULTIPART_TYPE)
        maintype, subtype = mtype.split("/", 1)
        msg = MIMEBase(maintype, subtype, *headers)
        msg.set_payload(data)
    return msg


def type_from_starts_with(payload, default=None):
    for text in INCLUSION_SRCH:
        if payload.startswith(text):
            return INCLUSION_TYPES_MAP[text]
    return default

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

import email

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
import yaml
import cloudinit
import cloudinit.util as util
import hashlib
import urllib


starts_with_mappings = {
    '#include': 'text/x-include-url',
    '#include-once': 'text/x-include-once-url',
    '#!': 'text/x-shellscript',
    '#cloud-config': 'text/cloud-config',
    '#upstart-job': 'text/upstart-job',
    '#part-handler': 'text/part-handler',
    '#cloud-boothook': 'text/cloud-boothook',
    '#cloud-config-archive': 'text/cloud-config-archive',
}


# if 'string' is compressed return decompressed otherwise return it
def decomp_str(string):
    import StringIO
    import gzip
    try:
        uncomp = gzip.GzipFile(None, "rb", 1, StringIO.StringIO(string)).read()
        return(uncomp)
    except:
        return(string)


def do_include(content, appendmsg):
    import os
    # is just a list of urls, one per line
    # also support '#include <url here>'
    includeonce = False
    for line in content.splitlines():
        if line == "#include":
            continue
        if line == "#include-once":
            includeonce = True
            continue
        if line.startswith("#include-once"):
            line = line[len("#include-once"):].lstrip()
            includeonce = True
        elif line.startswith("#include"):
            line = line[len("#include"):].lstrip()
        if line.startswith("#"):
            continue
        if line.strip() == "":
            continue

        # urls cannot not have leading or trailing white space
        msum = hashlib.md5()  # pylint: disable=E1101
        msum.update(line.strip())
        includeonce_filename = "%s/urlcache/%s" % (
            cloudinit.get_ipath_cur("data"), msum.hexdigest())
        try:
            if includeonce and os.path.isfile(includeonce_filename):
                with open(includeonce_filename, "r") as fp:
                    content = fp.read()
            else:
                content = urllib.urlopen(line).read()
                if includeonce:
                    util.write_file(includeonce_filename, content, mode=0600)
        except Exception:
            raise

        process_includes(message_from_string(decomp_str(content)), appendmsg)


def explode_cc_archive(archive, appendmsg):
    for ent in yaml.load(archive):
        # ent can be one of:
        #  dict { 'filename' : 'value', 'content' : 'value', 'type' : 'value' }
        #    filename and type not be present
        # or
        #  scalar(payload)

        def_type = "text/cloud-config"
        if isinstance(ent, str):
            ent = {'content': ent}

        content = ent.get('content', '')
        mtype = ent.get('type', None)
        if mtype == None:
            mtype = type_from_startswith(content, def_type)

        maintype, subtype = mtype.split('/', 1)
        if maintype == "text":
            msg = MIMEText(content, _subtype=subtype)
        else:
            msg = MIMEBase(maintype, subtype)
            msg.set_payload(content)

        if 'filename' in ent:
            msg.add_header('Content-Disposition', 'attachment',
                           filename=ent['filename'])

        for header in ent.keys():
            if header in ('content', 'filename', 'type'):
                continue
            msg.add_header(header, ent['header'])

        _attach_part(appendmsg, msg)


def multi_part_count(outermsg, newcount=None):
    """
    Return the number of attachments to this MIMEMultipart by looking
    at its 'Number-Attachments' header.
    """
    nfield = 'Number-Attachments'
    if nfield not in outermsg:
        outermsg[nfield] = "0"

    if newcount != None:
        outermsg.replace_header(nfield, str(newcount))

    return(int(outermsg.get('Number-Attachments', 0)))


def _attach_part(outermsg, part):
    """
    Attach an part to an outer message. outermsg must be a MIMEMultipart.
    Modifies a header in outermsg to keep track of number of attachments.
    """
    cur = multi_part_count(outermsg)
    if not part.get_filename(None):
        part.add_header('Content-Disposition', 'attachment',
            filename='part-%03d' % (cur + 1))
    outermsg.attach(part)
    multi_part_count(outermsg, cur + 1)


def type_from_startswith(payload, default=None):
    # slist is sorted longest first
    slist = sorted(starts_with_mappings.keys(), key=lambda e: 0 - len(e))
    for sstr in slist:
        if payload.startswith(sstr):
            return(starts_with_mappings[sstr])
    return default


def process_includes(msg, appendmsg=None):
    if appendmsg == None:
        appendmsg = MIMEMultipart()

    for part in msg.walk():
        # multipart/* are just containers
        if part.get_content_maintype() == 'multipart':
            continue

        ctype = None
        ctype_orig = part.get_content_type()

        payload = part.get_payload(decode=True)

        if ctype_orig in ("text/plain", "text/x-not-multipart"):
            ctype = type_from_startswith(payload)

        if ctype is None:
            ctype = ctype_orig

        if ctype in ('text/x-include-url', 'text/x-include-once-url'):
            do_include(payload, appendmsg)
            continue

        if ctype == "text/cloud-config-archive":
            explode_cc_archive(payload, appendmsg)
            continue

        if 'Content-Type' in msg:
            msg.replace_header('Content-Type', ctype)
        else:
            msg['Content-Type'] = ctype

        _attach_part(appendmsg, part)


def message_from_string(data, headers=None):
    if headers is None:
        headers = {}
    if "mime-version:" in data[0:4096].lower():
        msg = email.message_from_string(data)
        for (key, val) in headers.items():
            if key in msg:
                msg.replace_header(key, val)
            else:
                msg[key] = val
    else:
        mtype = headers.get("Content-Type", "text/x-not-multipart")
        maintype, subtype = mtype.split("/", 1)
        msg = MIMEBase(maintype, subtype, *headers)
        msg.set_payload(data)

    return(msg)


# this is heavily wasteful, reads through userdata string input
def preprocess_userdata(data):
    newmsg = MIMEMultipart()
    process_includes(message_from_string(decomp_str(data)), newmsg)
    return(newmsg.as_string())


# callback is a function that will be called with (data, content_type,
# filename, payload)
def walk_userdata(istr, callback, data=None):
    partnum = 0
    for part in message_from_string(istr).walk():
        # multipart/* are just containers
        if part.get_content_maintype() == 'multipart':
            continue

        ctype = part.get_content_type()
        if ctype is None:
            ctype = 'application/octet-stream'

        filename = part.get_filename()
        if not filename:
            filename = 'part-%03d' % partnum

        callback(data, ctype, filename, part.get_payload(decode=True))

        partnum = partnum + 1


if __name__ == "__main__":
    def main():
        import sys
        data = decomp_str(file(sys.argv[1]).read())
        newmsg = MIMEMultipart()
        process_includes(message_from_string(data), newmsg)
        print newmsg
        print "#found %s parts" % multi_part_count(newmsg)

    main()

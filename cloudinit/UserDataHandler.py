# vi: ts=4 expandtab
#
#    Copyright (C) 2009-2010 Canonical Ltd.
#
#    Author: Scott Moser <scott.moser@canonical.com>
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


starts_with_mappings={
    '#include' : 'text/x-include-url',
    '#!' : 'text/x-shellscript',
    '#cloud-config' : 'text/cloud-config',
    '#upstart-job'  : 'text/upstart-job',
    '#part-handler' : 'text/part-handler',
    '#cloud-boothook' : 'text/cloud-boothook'
}

# if 'str' is compressed return decompressed otherwise return it
def decomp_str(str):
    import StringIO
    import gzip
    try:
        uncomp = gzip.GzipFile(None,"rb",1,StringIO.StringIO(str)).read()
        return(uncomp)
    except:
        return(str)

def do_include(str,parts):
    import urllib
    # is just a list of urls, one per line
    for line in str.splitlines():
        if line == "#include": continue
        if line.startswith("#"): continue
        content = urllib.urlopen(line).read()
        process_includes(email.message_from_string(decomp_str(content)),parts)

def process_includes(msg,parts):
    # parts is a dictionary of arrays
    # parts['content']
    # parts['names']
    # parts['types']
    for t in ( 'content', 'names', 'types' ):
        if not parts.has_key(t):
            parts[t]=[ ]
    for part in msg.walk():
        # multipart/* are just containers
        if part.get_content_maintype() == 'multipart':
            continue

        payload = part.get_payload()

        ctype = None
        ctype_orig = part.get_content_type()
        if ctype_orig == "text/plain":
            for str, gtype in starts_with_mappings.items():
                if payload.startswith(str):
                    ctype = gtype
                    break

        if ctype is None:
            ctype = ctype_orig

        if ctype == 'text/x-include-url':
            do_include(payload,parts)
            continue

        filename = part.get_filename()
        if not filename:
            filename = 'part-%03d' % len(parts['content'])

        parts['content'].append(payload)
        parts['types'].append(ctype)
        parts['names'].append(filename)

def parts2mime(parts):
    outer = MIMEMultipart()

    i = 0
    while i < len(parts['content']):
        if parts['types'][i] is None:
            # No guess could be made, or the file is encoded (compressed), so
            # use a generic bag-of-bits type.
            ctype = 'application/octet-stream'
        else: ctype = parts['types'][i]
        maintype, subtype = ctype.split('/', 1)
        if maintype == 'text':
            msg = MIMEText(parts['content'][i], _subtype=subtype)
        else:
            msg = MIMEBase(maintype, subtype)
            msg.set_payload(parts['content'][i])
            # Encode the payload using Base64
            encoders.encode_base64(msg)
        # Set the filename parameter
        msg.add_header('Content-Disposition', 'attachment', 
            filename=parts['names'][i])
        outer.attach(msg)

        i=i+1
    return(outer.as_string())

# this is heavily wasteful, reads through userdata string input
def preprocess_userdata(data):
    parts = { }
    process_includes(email.message_from_string(decomp_str(data)),parts)
    return(parts2mime(parts))

# callbacks is a dictionary with:
#  { 'content-type': handler(data,content_type,filename,payload) }
def walk_userdata(str, callbacks, data = None):
    partnum = 0
    for part in email.message_from_string(str).walk():
        # multipart/* are just containers
        if part.get_content_maintype() == 'multipart':
            continue

        ctype = part.get_content_type()
        if ctype is None:
            ctype = 'application/octet-stream'

        filename = part.get_filename()
        if not filename:
            filename = 'part-%03d' % partnum

        if callbacks.has_key(ctype):
            callbacks[ctype](data,ctype,filename,part.get_payload())

        partnum = partnum+1

if __name__ == "__main__":
    import sys
    data = decomp_str(file(sys.argv[1]).read())
    parts = { }
    process_includes(email.message_from_string(data),parts)
    print "#found %s parts" % len(parts['content'])
    print parts2mime(parts)

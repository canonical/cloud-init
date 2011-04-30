#! /usr/bin/env python

import sys, os
import email
import mimetypes
import re

mimetypes.types_map['.sh'] = 'text/x-shellscript'
cloud_config_mark_strings = { '#!': 'text/x-shellscript', '#include': 'text/x-include-url',
    '#cloud-config': 'text/cloud-config', '#upstart-job': 'text/upstart-job',
    '#cloud-boothook': 'text/cloud-boothook'
    }
def write_mime_multipart():
    multipart_msg = email.mime.Multipart.MIMEMultipart()
    for arg in sys.argv[1:]:
        if ',' in arg:
            (msg_file, msg_type) = arg.split(',')
        else:
            msg_file = arg
            msg_type = None

        msg_file = os.path.expanduser(msg_file)
        if not os.path.isfile(msg_file):
            print >> sys.stderr, "Can't find file %s" % arg
            exit(1)

        if not msg_type: msg_type = get_type_from_file(arg)
        msg = email.mime.base.MIMEBase(*msg_type.split('/'))
        msg.set_payload(open(msg_file, 'r').read())
        multipart_msg.attach(msg)

    print multipart_msg.as_string()

def get_type_from_file(filename):
    first_line = open(filename).readline()
    m = re.match('Content-Type: (\w+/\w+)', first_line)
    if m:
        return m.groups[1]
    else:
        for mark_string, mime_type in cloud_config_mark_strings.items():
            if first_line.startswith(mark_string):
                return mime_type
    return mimetypes.guess_type(filename)[0] or 'text/plain'

if __name__ == '__main__':
    if len(sys.argv) == 1 or '-h' in sys.argv or '--help' in sys.argv:
        print "Usage: %s file1,application/cloud-config file2.sh ..." % os.path.basename(sys.argv[0])
        print "MIME Multipart message will be written to STDOUT"
        exit(0)
    write_mime_multipart()


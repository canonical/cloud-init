#!/usr/bin/python

import argparse
import sys

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

KNOWN_CONTENT_TYPES = [
    'text/x-include-once-url',
    'text/x-include-url',
    'text/cloud-config-archive',
    'text/upstart-job',
    'text/cloud-config',
    'text/part-handler',
    'text/x-shellscript',
    'text/cloud-boothook',
]


def file_content_type(text):
    try:
        filename, content_type = text.split(":", 1)
        return (open(filename, 'r'), filename, content_type.strip())
    except ValueError:
        raise argparse.ArgumentError(text, "Invalid value for %r" % (text))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-a", "--attach",
                        dest="files",
                        type=file_content_type,
                        action='append',
                        default=[],
                        required=True,
                        metavar="<file>:<content-type>",
                        help="attach the given file in the specified "
                             "content type")
    args = parser.parse_args()
    sub_messages = []
    for i, (fh, filename, format_type) in enumerate(args.files):
        contents = fh.read()
        sub_message = MIMEText(contents, format_type, sys.getdefaultencoding())
        sub_message.add_header('Content-Disposition',
                               'attachment; filename="%s"' % (filename))
        content_type = sub_message.get_content_type().lower()
        if content_type not in KNOWN_CONTENT_TYPES:
            sys.stderr.write(("WARNING: content type %r for attachment %s "
                             "may be incorrect!\n") % (content_type, i + 1))
        sub_messages.append(sub_message)
    combined_message = MIMEMultipart()
    for msg in sub_messages:
        combined_message.attach(msg)
    print(combined_message)
    return 0


if __name__ == '__main__':
    sys.exit(main())

# vi: ts=4 expandtab

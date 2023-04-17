#!/usr/bin/env python3

# This file is part of cloud-init. See LICENSE file for license information.

"""Generate multi-part mime messages for user-data."""

import argparse
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from cloudinit import log
from cloudinit.cmd.devel import addLogHandlerCLI
from cloudinit.handlers import INCLUSION_TYPES_MAP

NAME = "make-mime"
LOG = log.getLogger(NAME)
EPILOG = (
    "Example: make-mime -a config.yaml:cloud-config "
    "-a script.sh:x-shellscript > user-data"
)


def create_mime_message(files):
    sub_messages = []
    errors = []
    for i, (fh, filename, format_type) in enumerate(files):
        contents = fh.read()
        sub_message = MIMEText(contents, format_type, sys.getdefaultencoding())
        sub_message.add_header(
            "Content-Disposition", 'attachment; filename="%s"' % (filename)
        )
        content_type = sub_message.get_content_type().lower()
        if content_type not in get_content_types():
            msg = (
                "content type %r for attachment %s " "may be incorrect!"
            ) % (content_type, i + 1)
            errors.append(msg)
        sub_messages.append(sub_message)
    combined_message = MIMEMultipart()
    for msg in sub_messages:
        combined_message.attach(msg)
    return (combined_message, errors)


def file_content_type(text):
    """Return file content type by reading the first line of the input."""
    try:
        filename, content_type = text.split(":", 1)
        return (open(filename, "r"), filename, content_type.strip())
    except ValueError as e:
        raise argparse.ArgumentError(
            text, "Invalid value for %r" % (text)
        ) from e


def get_parser(parser=None):
    """Build or extend and arg parser for make-mime utility.

    @param parser: Optional existing ArgumentParser instance representing the
        subcommand which will be extended to support the args of this utility.

    @returns: ArgumentParser with proper argument configuration.
    """
    if not parser:
        parser = argparse.ArgumentParser()
    # update the parser's doc and add an epilog to show an example
    parser.description = __doc__
    parser.epilog = EPILOG
    parser.add_argument(
        "-a",
        "--attach",
        dest="files",
        type=file_content_type,
        action="append",
        default=[],
        metavar="<file>:<content-type>",
        help="attach the given file as the specified content-type",
    )
    parser.add_argument(
        "-l",
        "--list-types",
        action="store_true",
        default=False,
        help="List support cloud-init content types.",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        default=False,
        help="Ignore unknown content-type warnings",
    )
    return parser


def get_content_types(strip_prefix=False):
    """Return a list of cloud-init supported content types.  Optionally
    strip out the leading 'text/' of the type if strip_prefix=True.
    """
    return sorted(
        [
            ctype.replace("text/", "") if strip_prefix else ctype
            for ctype in INCLUSION_TYPES_MAP.values()
        ]
    )


def handle_args(name, args):
    """Create a multi-part MIME archive for use as user-data.  Optionally
       print out the list of supported content types of cloud-init.

    Also setup CLI log handlers to report to stderr since this is a development
    utility which should be run by a human on the CLI.

    @return 0 on success, 1 on failure.
    """
    addLogHandlerCLI(LOG, log.DEBUG if args.debug else log.WARNING)
    if args.list_types:
        print("\n".join(get_content_types(strip_prefix=True)))
        return 0

    combined_message, errors = create_mime_message(args.files)
    if errors:
        level = "WARNING" if args.force else "ERROR"
        for error in errors:
            sys.stderr.write(f"{level}: {error}\n")
        sys.stderr.write("Invalid content-types, override with --force\n")
        if not args.force:
            return 1
    print(combined_message)
    return 0


def main():
    args = get_parser().parse_args()
    return handle_args(NAME, args)


if __name__ == "__main__":
    sys.exit(main())

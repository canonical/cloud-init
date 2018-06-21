# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import os

from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.nonmultipart import MIMENonMultipart
from email.mime.text import MIMEText

import six

from cloudinit import handlers
from cloudinit import log as logging
from cloudinit.url_helper import read_file_or_url, UrlError
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
ARCHIVE_UNDEF_BINARY_TYPE = "application/octet-stream"

# This seems to hit most of the gzip possible content types.
DECOMP_TYPES = [
    'application/gzip',
    'application/gzip-compressed',
    'application/gzipped',
    'application/x-compress',
    'application/x-compressed',
    'application/x-gunzip',
    'application/x-gzip',
    'application/x-gzip-compressed',
]

# Msg header used to track attachments
ATTACHMENT_FIELD = 'Number-Attachments'

# Only the following content types can have there launch index examined
# in there payload, evey other content type can still provide a header
EXAMINE_FOR_LAUNCH_INDEX = ["text/cloud-config"]


def _replace_header(msg, key, value):
    del msg[key]
    msg[key] = value


def _set_filename(msg, filename):
    del msg['Content-Disposition']
    msg.add_header('Content-Disposition',
                   'attachment', filename=str(filename))


class UserDataProcessor(object):
    def __init__(self, paths):
        self.paths = paths
        self.ssl_details = util.fetch_ssl_details(paths)

    def process(self, blob):
        accumulating_msg = MIMEMultipart()
        if isinstance(blob, list):
            for b in blob:
                self._process_msg(convert_string(b), accumulating_msg)
        else:
            self._process_msg(convert_string(blob), accumulating_msg)
        return accumulating_msg

    def _process_msg(self, base_msg, append_msg):

        def find_ctype(payload):
            return handlers.type_from_starts_with(payload)

        for part in base_msg.walk():
            if is_skippable(part):
                continue

            ctype = None
            ctype_orig = part.get_content_type()
            payload = util.fully_decoded_payload(part)
            was_compressed = False

            # When the message states it is of a gzipped content type ensure
            # that we attempt to decode said payload so that the decompressed
            # data can be examined (instead of the compressed data).
            if ctype_orig in DECOMP_TYPES:
                try:
                    payload = util.decomp_gzip(payload, quiet=False)
                    # At this point we don't know what the content-type is
                    # since we just decompressed it.
                    ctype_orig = None
                    was_compressed = True
                except util.DecompressionError as e:
                    LOG.warning("Failed decompressing payload from %s of"
                                " length %s due to: %s",
                                ctype_orig, len(payload), e)
                    continue

            # Attempt to figure out the payloads content-type
            if not ctype_orig:
                ctype_orig = UNDEF_TYPE
            if ctype_orig in TYPE_NEEDED:
                ctype = find_ctype(payload)
            if ctype is None:
                ctype = ctype_orig

            # In the case where the data was compressed, we want to make sure
            # that we create a new message that contains the found content
            # type with the uncompressed content since later traversals of the
            # messages will expect a part not compressed.
            if was_compressed:
                maintype, subtype = ctype.split("/", 1)
                n_part = MIMENonMultipart(maintype, subtype)
                n_part.set_payload(payload)
                # Copy various headers from the old part to the new one,
                # but don't include all the headers since some are not useful
                # after decoding and decompression.
                if part.get_filename():
                    _set_filename(n_part, part.get_filename())
                for h in ('Launch-Index',):
                    if h in part:
                        _replace_header(n_part, h, str(part[h]))
                part = n_part

            if ctype != ctype_orig:
                _replace_header(part, CONTENT_TYPE, ctype)

            if ctype in INCLUDE_TYPES:
                self._do_include(payload, append_msg)
                continue

            if ctype in ARCHIVE_TYPES:
                self._explode_archive(payload, append_msg)
                continue

            # TODO(harlowja): Should this be happening, shouldn't
            # the part header be modified and not the base?
            _replace_header(base_msg, CONTENT_TYPE, ctype)

            self._attach_part(append_msg, part)

    def _attach_launch_index(self, msg):
        header_idx = msg.get('Launch-Index', None)
        payload_idx = None
        if msg.get_content_type() in EXAMINE_FOR_LAUNCH_INDEX:
            try:
                # See if it has a launch-index field
                # that might affect the final header
                payload = util.load_yaml(msg.get_payload(decode=True))
                if payload:
                    payload_idx = payload.get('launch-index')
            except Exception:
                pass
        # Header overrides contents, for now (?) or the other way around?
        if header_idx is not None:
            payload_idx = header_idx
        # Nothing found in payload, use header (if anything there)
        if payload_idx is None:
            payload_idx = header_idx
        if payload_idx is not None:
            try:
                msg.add_header('Launch-Index', str(int(payload_idx)))
            except (ValueError, TypeError):
                pass

    def _get_include_once_filename(self, entry):
        entry_fn = util.hash_blob(entry, 'md5', 64)
        return os.path.join(self.paths.get_ipath_cur('data'),
                            'urlcache', entry_fn)

    def _process_before_attach(self, msg, attached_id):
        if not msg.get_filename():
            _set_filename(msg, PART_FN_TPL % (attached_id))
        self._attach_launch_index(msg)

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
                try:
                    resp = read_file_or_url(include_url,
                                            ssl_details=self.ssl_details)
                    if include_once_on and resp.ok():
                        util.write_file(include_once_fn, resp.contents,
                                        mode=0o600)
                    if resp.ok():
                        content = resp.contents
                    else:
                        LOG.warning(("Fetching from %s resulted in"
                                     " a invalid http code of %s"),
                                    include_url, resp.code)
                except UrlError as urle:
                    message = str(urle)
                    # Older versions of requests.exceptions.HTTPError may not
                    # include the errant url. Append it for clarity in logs.
                    if include_url not in message:
                        message += ' for url: {0}'.format(include_url)
                    LOG.warning(message)
                except IOError as ioe:
                    LOG.warning("Fetching from %s resulted in %s",
                                include_url, ioe)

            if content is not None:
                new_msg = convert_string(content)
                self._process_msg(new_msg, append_msg)

    def _explode_archive(self, archive, append_msg):
        entries = util.load_yaml(archive, default=[], allowed=(list, set))
        for ent in entries:
            # ent can be one of:
            #  dict { 'filename' : 'value', 'content' :
            #       'value', 'type' : 'value' }
            #    filename and type not be present
            # or
            #  scalar(payload)
            if isinstance(ent, six.string_types):
                ent = {'content': ent}
            if not isinstance(ent, (dict)):
                # TODO(harlowja) raise?
                continue

            content = ent.get('content', '')
            mtype = ent.get('type')
            if not mtype:
                default = ARCHIVE_UNDEF_TYPE
                if isinstance(content, six.binary_type):
                    default = ARCHIVE_UNDEF_BINARY_TYPE
                mtype = handlers.type_from_starts_with(content, default)

            maintype, subtype = mtype.split('/', 1)
            if maintype == "text":
                if isinstance(content, six.binary_type):
                    content = content.decode()
                msg = MIMEText(content, _subtype=subtype)
            else:
                msg = MIMEBase(maintype, subtype)
                msg.set_payload(content)

            if 'filename' in ent:
                _set_filename(msg, ent['filename'])
            if 'launch-index' in ent:
                msg.add_header('Launch-Index', str(ent['launch-index']))

            for header in list(ent.keys()):
                if header.lower() in ('content', 'filename', 'type',
                                      'launch-index', 'content-disposition',
                                      ATTACHMENT_FIELD.lower(),
                                      CONTENT_TYPE.lower()):
                    continue
                msg.add_header(header, ent[header])

            self._attach_part(append_msg, msg)

    def _multi_part_count(self, outer_msg, new_count=None):
        """
        Return the number of attachments to this MIMEMultipart by looking
        at its 'Number-Attachments' header.
        """
        if ATTACHMENT_FIELD not in outer_msg:
            outer_msg[ATTACHMENT_FIELD] = '0'

        if new_count is not None:
            _replace_header(outer_msg, ATTACHMENT_FIELD, str(new_count))

        fetched_count = 0
        try:
            fetched_count = int(outer_msg.get(ATTACHMENT_FIELD))
        except (ValueError, TypeError):
            _replace_header(outer_msg, ATTACHMENT_FIELD, str(fetched_count))
        return fetched_count

    def _attach_part(self, outer_msg, part):
        """
        Attach a message to an outer message. outermsg must be a MIMEMultipart.
        Modifies a header in the outer message to keep track of number of
        attachments.
        """
        part_count = self._multi_part_count(outer_msg)
        self._process_before_attach(part, part_count + 1)
        outer_msg.attach(part)
        self._multi_part_count(outer_msg, part_count + 1)


def is_skippable(part):
    # multipart/* are just containers
    part_maintype = part.get_content_maintype() or ''
    if part_maintype.lower() == 'multipart':
        return True
    return False


# Coverts a raw string into a mime message
def convert_string(raw_data, content_type=NOT_MULTIPART_TYPE):
    """convert a string (more likely bytes) or a message into
    a mime message."""
    if not raw_data:
        raw_data = b''

    def create_binmsg(data, content_type):
        maintype, subtype = content_type.split("/", 1)
        msg = MIMEBase(maintype, subtype)
        msg.set_payload(data)
        return msg

    if isinstance(raw_data, six.text_type):
        bdata = raw_data.encode('utf-8')
    else:
        bdata = raw_data
    bdata = util.decomp_gzip(bdata, decode=False)
    if b"mime-version:" in bdata[0:4096].lower():
        msg = util.message_from_string(bdata.decode('utf-8'))
    else:
        msg = create_binmsg(bdata, content_type)

    return msg


# vi: ts=4 expandtab

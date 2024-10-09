# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import email
import logging
import os
import pathlib
from email.message import Message
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.nonmultipart import MIMENonMultipart
from email.mime.text import MIMEText
from typing import Union

from cloudinit import features, gpg, handlers, subp, util
from cloudinit.settings import KEY_DIR
from cloudinit.url_helper import UrlError, read_file_or_url

LOG = logging.getLogger(__name__)

# Constants copied in from the handler module
NOT_MULTIPART_TYPE = handlers.NOT_MULTIPART_TYPE
PART_FN_TPL = handlers.PART_FN_TPL
OCTET_TYPE = handlers.OCTET_TYPE

# Saves typing errors
CONTENT_TYPE = "Content-Type"

# Various special content types that cause special actions
TYPE_NEEDED = ["text/plain", "text/x-not-multipart"]
INCLUDE_TYPES = ["text/x-include-url", "text/x-include-once-url"]
ARCHIVE_TYPES = ["text/cloud-config-archive"]
UNDEF_TYPE = "text/plain"
ARCHIVE_UNDEF_TYPE = "text/cloud-config"
ARCHIVE_UNDEF_BINARY_TYPE = "application/octet-stream"

# This seems to hit most of the gzip possible content types.
ENCRYPT_TYPE = "text/x-pgp-armored"
DECOMP_TYPES = [
    "application/gzip",
    "application/gzip-compressed",
    "application/gzipped",
    "application/x-compress",
    "application/x-compressed",
    "application/x-gunzip",
    "application/x-gzip",
    "application/x-gzip-compressed",
]
TRANSFORM_TYPES = [ENCRYPT_TYPE] + DECOMP_TYPES

# Msg header used to track attachments
ATTACHMENT_FIELD = "Number-Attachments"

# Only the following content types can have their launch index examined
# in their payload, every other content type can still provide a header
EXAMINE_FOR_LAUNCH_INDEX = ["text/cloud-config"]


def _replace_header(msg, key, value):
    del msg[key]
    msg[key] = value


def _set_filename(msg, filename):
    del msg["Content-Disposition"]
    msg.add_header("Content-Disposition", "attachment", filename=str(filename))


def _handle_error(error_message, source_exception=None):
    if features.ERROR_ON_USER_DATA_FAILURE:
        raise RuntimeError(error_message) from source_exception
    else:
        LOG.warning(error_message)


class UserDataProcessor:
    def __init__(self, paths):
        self.paths = paths
        self.ssl_details = util.fetch_ssl_details(paths)

    def process(self, blob, require_signature=False):
        accumulating_msg = MIMEMultipart()
        if isinstance(blob, list):
            for b in blob:
                self._process_msg(
                    convert_string(b), accumulating_msg, require_signature
                )
        else:
            self._process_msg(
                convert_string(blob), accumulating_msg, require_signature
            )
        return accumulating_msg

    def _process_msg(
        self, base_msg: Message, append_msg, require_signature=False
    ):
        def find_ctype(payload):
            return handlers.type_from_starts_with(payload)

        for part in base_msg.walk():
            if is_skippable(part):
                continue

            payload = util.fully_decoded_payload(part)

            ctype = part.get_content_type()

            # There are known cases where mime-type text/x-shellscript included
            # non shell-script content that was user-data instead.  It is safe
            # to check the true MIME type for x-shellscript type since all
            # shellscript payloads must have a #! header.  The other MIME types
            # that cloud-init supports do not have the same guarantee.
            if ctype in TYPE_NEEDED + ["text/x-shellscript"]:
                ctype = find_ctype(payload) or ctype

            if require_signature and ctype != ENCRYPT_TYPE:
                error_message = (
                    "'require_signature' was set true in cloud-init's base "
                    f"configuration, but content type is {ctype}."
                )
                raise RuntimeError(error_message)

            was_transformed = False

            # When the message states it is transformed ensure
            # that we attempt to decode said payload so that the transformed
            # data can be examined.
            parent_ctype = None
            if ctype in TRANSFORM_TYPES:
                if ctype in DECOMP_TYPES:
                    try:
                        payload = util.decomp_gzip(payload, quiet=False)
                    except util.DecompressionError as e:
                        error_message = (
                            "Failed decompressing payload from {} of"
                            " length {} due to: {}".format(
                                ctype, len(payload), e
                            )
                        )
                        _handle_error(error_message, e)
                        continue
                elif ctype == ENCRYPT_TYPE and isinstance(payload, str):
                    with gpg.GPG() as gpg_context:
                        # Import all keys from the /etc/cloud/keys directory
                        keys_dir = pathlib.Path(KEY_DIR)
                        if keys_dir.is_dir():
                            for key_path in keys_dir.iterdir():
                                gpg_context.import_key(key_path)
                        try:
                            payload = gpg_context.decrypt(
                                payload, require_signature=require_signature
                            )
                        except subp.ProcessExecutionError as e:
                            raise RuntimeError(
                                "Failed decrypting user data payload of type "
                                f"{ctype}. Ensure any necessary keys are "
                                f"present in {KEY_DIR}."
                            ) from e
                else:
                    error_message = (
                        f"Unknown content type {ctype} that"
                        " is marked as transformed"
                    )
                    _handle_error(error_message)
                    continue
                was_transformed = True
                parent_ctype = ctype
                ctype = find_ctype(payload) or parent_ctype

            # In the case where the data was compressed, we want to make sure
            # that we create a new message that contains the found content
            # type with the uncompressed content since later traversals of the
            # messages will expect a part not compressed.
            if was_transformed:
                maintype, subtype = ctype.split("/", 1)
                n_part = MIMENonMultipart(maintype, subtype)
                n_part.set_payload(payload)
                # Copy various headers from the old part to the new one,
                # but don't include all the headers since some are not useful
                # after decoding and decompression.
                if part.get_filename():
                    _set_filename(n_part, part.get_filename())
                if "Launch-Index" in part:
                    _replace_header(
                        n_part, "Launch-Index", str(part["Launch-Index"])
                    )
                part = n_part

            if ctype != parent_ctype:
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
        header_idx = msg.get("Launch-Index", None)
        payload_idx = None
        if msg.get_content_type() in EXAMINE_FOR_LAUNCH_INDEX:
            try:
                # See if it has a launch-index field
                # that might affect the final header
                payload = util.load_yaml(msg.get_payload(decode=True))
                if payload:
                    payload_idx = payload.get("launch-index")
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
                msg.add_header("Launch-Index", str(int(payload_idx)))
            except (ValueError, TypeError):
                pass

    def _get_include_once_filename(self, entry):
        entry_fn = util.hash_blob(entry, "md5", 64)
        return os.path.join(
            self.paths.get_ipath_cur("data"), "urlcache", entry_fn
        )

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
                line = line[len("#include-once") :].lstrip()
                # Every following include will now
                # not be refetched.... but will be
                # re-read from a local urlcache (if it worked)
                include_once_on = True
            elif lc_line.startswith("#include"):
                line = line[len("#include") :].lstrip()
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
                content = util.load_text_file(include_once_fn)
            else:
                try:
                    resp = read_file_or_url(
                        include_url,
                        timeout=5,
                        retries=10,
                        ssl_details=self.ssl_details,
                    )
                    if include_once_on and resp.ok():
                        util.write_file(
                            include_once_fn, resp.contents, mode=0o600
                        )
                    if resp.ok():
                        content = resp.contents
                    else:
                        error_message = (
                            "Fetching from {} resulted in"
                            " a invalid http code of {}".format(
                                include_url, resp.code
                            )
                        )
                        _handle_error(error_message)
                except UrlError as urle:
                    message = str(urle)
                    # Older versions of requests.exceptions.HTTPError may not
                    # include the errant url. Append it for clarity in logs.
                    if include_url not in message:
                        message += " for url: {0}".format(include_url)
                    _handle_error(message, urle)
                except IOError as ioe:
                    error_message = "Fetching from {} resulted in {}".format(
                        include_url, ioe
                    )
                    _handle_error(error_message, ioe)

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
            if isinstance(ent, str):
                ent = {"content": ent}
            if not isinstance(ent, (dict)):
                # TODO(harlowja) raise?
                continue

            content = ent.get("content", "")
            mtype = ent.get("type")
            if not mtype:
                default = ARCHIVE_UNDEF_TYPE
                if isinstance(content, bytes):
                    default = ARCHIVE_UNDEF_BINARY_TYPE
                mtype = handlers.type_from_starts_with(content, default)

            maintype, subtype = mtype.split("/", 1)
            if maintype == "text":
                if isinstance(content, bytes):
                    content = content.decode()
                msg = MIMEText(content, _subtype=subtype)
            else:
                msg = MIMEBase(maintype, subtype)
                msg.set_payload(content)

            if "filename" in ent:
                _set_filename(msg, ent["filename"])
            if "launch-index" in ent:
                msg.add_header("Launch-Index", str(ent["launch-index"]))

            for header in list(ent.keys()):
                if header.lower() in (
                    "content",
                    "filename",
                    "type",
                    "launch-index",
                    "content-disposition",
                    ATTACHMENT_FIELD.lower(),
                    CONTENT_TYPE.lower(),
                ):
                    continue
                msg.add_header(header, ent[header])

            self._attach_part(append_msg, msg)

    def _multi_part_count(self, outer_msg, new_count=None):
        """
        Return the number of attachments to this MIMEMultipart by looking
        at its 'Number-Attachments' header.
        """
        if ATTACHMENT_FIELD not in outer_msg:
            outer_msg[ATTACHMENT_FIELD] = "0"

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
    part_maintype = part.get_content_maintype() or ""
    if part_maintype.lower() == "multipart":
        return True
    return False


def convert_string(
    raw_data: Union[str, bytes], content_type=NOT_MULTIPART_TYPE
) -> Message:
    """Convert the raw data into a mime message.

    'raw_data' is the data as it was received from the user-data source.
    It could be a string, bytes, or a gzip compressed version of either.
    """
    if not raw_data:
        raw_data = b""

    def create_binmsg(data, content_type):
        maintype, subtype = content_type.split("/", 1)
        msg = MIMEBase(maintype, subtype)
        msg.set_payload(data)
        return msg

    if isinstance(raw_data, str):
        bdata = raw_data.encode("utf-8")
    else:
        bdata = raw_data
    bdata = util.decomp_gzip(bdata, decode=False)
    if b"mime-version:" in bdata[0:4096].lower():
        msg = email.message_from_string(bdata.decode("utf-8"))
    else:
        msg = create_binmsg(bdata, content_type)

    return msg

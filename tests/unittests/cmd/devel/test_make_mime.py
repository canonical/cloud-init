# This file is part of cloud-init. See LICENSE file for license information.

from email import message_from_string
from io import StringIO

import pytest

from cloudinit.cmd.devel.make_mime import create_mime_message
from cloudinit.user_data import UserDataProcessor


@pytest.mark.parametrize(
    "filename",
    [
        "config.yaml",
        "my config.yaml",
        'config"prod.yaml',
        "config\\prod.yaml",
        "café.yaml",
        "إعداد.yaml",
    ],
)
@pytest.mark.parametrize("process_user_data", [False, True])
def test_attachment_filename_round_trip(
    filename: str, process_user_data: bool, ud_proc: UserDataProcessor
) -> None:
    """Preserve attachment filenames when parsing generated MIME user-data."""
    contents = "#cloud-config\nhostname: example\n"
    message, errors = create_mime_message(
        [(StringIO(contents), filename, "cloud-config")]
    )
    assert errors == []

    serialized = message.as_string()
    if process_user_data:
        parsed = ud_proc.process(serialized)
    else:
        parsed = message_from_string(serialized)

    [attachment] = parsed.get_payload()
    assert attachment.get_filename() == filename
    assert attachment.get_content_type() == "text/cloud-config"
    assert attachment.get_payload(decode=True) == contents.encode("utf-8")

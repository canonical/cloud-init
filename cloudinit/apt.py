# Copyright (C) 2021 Canonical Ltd.
#
# Author: Brett Holman <brett.holman@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""apt.py - Collection of apt related functions"""

import os

from cloudinit import log as logging
from cloudinit import gpg
from cloudinit import util

LOCAL_KEYS='/etc/apt/trusted.gpg'
KEY_DIR='/etc/apt/trusted.gpg.d/'

LOG = logging.getLogger(__name__)


def key(command, input_file=None, output_file=None, data=None):
    """apt-key commands implemented: 'add', 'list', 'finger'

    @param input_file: '-' or file name to read from
    @param output_file: name of output gpg file (without .gpg or .asc)
    @param data: key contents
    """

    def _get_key_files():
        """return all apt keys

        /etc/apt/trusted.gpg (if it exists) and all keyfiles (and symlinks to
        keyfiles) in /etc/apt/trusted.gpg.d/ are returned
        """
        key_files = [LOCAL_KEYS] if not os.path.isfile(LOCAL_KEYS) else []

        for file in os.listdir(KEY_DIR):
            if file.endswith('.gpg') or file.endswith('.asc'):
                key_files.append(file)
        return key_files

    def add(input_file, output_file, data):
        """apt-key add <file>
        """
        if input_file == '-':
            stdout = gpg.dearmor(data)
            util.write_file(KEY_DIR + '{}.gpg'.format(output_file), stdout)
        else:
            raise NotImplementedError

    def list():
        """apt-key list
        """
        for key_file in _get_key_files():
            gpg.list(key_file)

    if command == 'add':
        add(input_file, output_file, data)
    elif command == 'finger' or command == 'list':
        list()
    else:
        raise NotImplementedError

# This file is part of cloud-init. See LICENSE file for license information.

import logging
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TESTCASES_DIR = os.path.join(BASE_DIR, 'testcases')
TEST_CONF_DIR = os.path.join(BASE_DIR, 'configs')


def _initialize_logging():
    """
    configure logging for cloud_tests
    """
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG)
    console.setFormatter(formatter)

    logger.addHandler(console)

    return logger


LOG = _initialize_logging()

# vi: ts=4 expandtab

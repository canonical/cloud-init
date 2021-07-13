import logging
import multiprocessing
import os
import time
from contextlib import contextmanager
from collections import namedtuple
from pathlib import Path


log = logging.getLogger('integration_testing')
key_pair = namedtuple('key_pair', 'public_key private_key')

ASSETS_DIR = Path('tests/integration_tests/assets')
KEY_PATH = ASSETS_DIR / 'keys'


def verify_ordered_items_in_text(to_verify: list, text: str):
    """Assert all items in list appear in order in text.

    Examples:
      verify_ordered_items_in_text(['a', '1'], 'ab1')  # passes
      verify_ordered_items_in_text(['1', 'a'], 'ab1')  # raises AssertionError
    """
    index = 0
    for item in to_verify:
        index = text[index:].find(item)
        assert index > -1, "Expected item not found: '{}'".format(item)


@contextmanager
def emit_dots_on_travis():
    """emit a dot every 60 seconds if running on Travis.

    Travis will kill jobs that don't emit output for a certain amount of time.
    This context manager spins up a background process which will emit a dot to
    stdout every 60 seconds to avoid being killed.

    It should be wrapped selectively around operations that are known to take a
    long time.
    """
    if os.environ.get('TRAVIS') != "true":
        # If we aren't on Travis, don't do anything.
        yield
        return

    def emit_dots():
        while True:
            log.info(".")
            time.sleep(60)

    dot_process = multiprocessing.Process(target=emit_dots)
    dot_process.start()
    try:
        yield
    finally:
        dot_process.terminate()


def get_test_rsa_keypair(key_name: str = 'test1') -> key_pair:
    private_key_path = KEY_PATH / 'id_rsa.{}'.format(key_name)
    public_key_path = KEY_PATH / 'id_rsa.{}.pub'.format(key_name)
    with public_key_path.open() as public_file:
        public_key = public_file.read()
    with private_key_path.open() as private_file:
        private_key = private_file.read()
    return key_pair(public_key, private_key)

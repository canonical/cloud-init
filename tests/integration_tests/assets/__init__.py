import os
from collections import namedtuple
from pathlib import Path

ASSET_DIR = Path(os.path.dirname(os.path.realpath(__file__)))
PRIVATE_RSA_KEY_PATH = ASSET_DIR / 'test_id_rsa'
PUBLIC_RSA_KEY_PATH = ASSET_DIR / 'test_id_rsa.pub'


def get_test_rsa_keypair():
    with PUBLIC_RSA_KEY_PATH.open() as public_file:
        public_key = public_file.read()
    with PRIVATE_RSA_KEY_PATH.open() as private_file:
        private_key = private_file.read()
    KeyPair = namedtuple('KeyPair', 'public_rsa_key private_rsa_key')
    return KeyPair(public_key, private_key)

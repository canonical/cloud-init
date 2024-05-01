# This file is part of cloud-init. See LICENSE file for license information.
from contextlib import suppress


def _not_available(secret: str, salt: str):
    """Raise when called so that importing this module doesn't throw
    ImportError when ds_detect() returns false. In this case, crypt
    and passlib are not needed.
    """
    raise ImportError("crypt/passlib not found, missing dependency")


encrypt_pass = _not_available
_passlib_crypt = _not_available
_deprecated_crypt = _not_available


# lowest priority: external python dependency with an uncertain future
with suppress(ImportError, AttributeError):
    import passlib.hash

    def _passlib_crypt(secret: str, salt: str):
        """crypt.crypt() interface based on passlib"""
        return passlib.hash.sha512_crypt.hash(secret, salt=salt, rounds=5000)

    encrypt_pass = _passlib_crypt

# higher priority: savor while it lasts
with suppress(ImportError, AttributeError):
    import crypt

    def _deprecated_crypt(secret: str, salt: str):
        """crypt.crypt() from the deprecated library crypt"""
        return crypt.crypt(secret, salt=f"$6${salt}")

    encrypt_pass = _deprecated_crypt

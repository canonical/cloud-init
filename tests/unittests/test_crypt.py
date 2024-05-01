# This file is part of cloud-init. See LICENSE file for license information.
import logging

import pytest

from cloudinit import crypt, util

LOG = logging.getLogger(__name__)

RAND = util.rand_str(strlen=16)


class TestSubp:
    @pytest.mark.parametrize(
        "password, salt, expected",
        [
            (
                "thankee",
                "danke",
                "$6$danke$YV5PUooeXRfA/Lo2pYfXUTWIG6yonctF"
                "txKIpaA1JXX6vfEA5ANdiRrdrFP7fp7lztIC.fFj/jvBsHgXTnoru/",
            ),
            # the following test requires that the unittest environment
            # provide at least one of the required dependencies: crypt or
            # passlib
            (
                "allshouldmatchthis",
                RAND,
                crypt.encrypt_pass("allshouldmatchthis", RAND),
            ),
        ],
    )
    @pytest.mark.parametrize(
        "name, function",
        [
            ("crypt:passlib", crypt._passlib_crypt),
            ("crypt:deprecated_crypt", crypt._deprecated_crypt),
        ],
    )
    def test_passwords(self, password, salt, expected, name, function):
        """verify that the crypt.crypt() replacement implementation behaviors
        match and provide expected behavior
        """
        try:
            assert expected == function(password, salt)
        except ImportError:
            LOG.info("%s implementation not available, not testing it", name)

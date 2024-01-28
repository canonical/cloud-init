# This file is part of cloud-init. See LICENSE file for license information.

#    Copyright (C) 2013 Hewlett-Packard Development Company, L.P.
#
#    Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
#    Based on test_handler_set_hostname.py
#
#    This file is part of cloud-init. See LICENSE file for license information.
import gzip
import logging
import tempfile
from io import BytesIO

import pytest

from cloudinit import atomic_helper, subp, util
from cloudinit.config import cc_seed_random
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import TestCase, skipUnlessJsonSchema
from tests.unittests.util import get_cloud

LOG = logging.getLogger(__name__)


class TestRandomSeed(TestCase):
    def setUp(self):
        super(TestRandomSeed, self).setUp()
        self._seed_file = tempfile.mktemp()
        self.unapply = []

        # by default 'which' has nothing in its path
        self.apply_patches([(subp, "which", self._which)])
        self.apply_patches([(subp, "subp", self._subp)])
        self.subp_called = []
        self.whichdata = {}

    def tearDown(self):
        apply_patches([i for i in reversed(self.unapply)])
        util.del_file(self._seed_file)

    def apply_patches(self, patches):
        ret = apply_patches(patches)
        self.unapply += ret

    def _which(self, program):
        return self.whichdata.get(program)

    def _subp(self, *args, **kwargs):
        # supports subp calling with cmd as args or kwargs
        if "args" not in kwargs:
            kwargs["args"] = args[0]
        self.subp_called.append(kwargs)
        return

    def _compress(self, text):
        contents = BytesIO()
        gz_fh = gzip.GzipFile(mode="wb", fileobj=contents)
        gz_fh.write(text)
        gz_fh.close()
        return contents.getvalue()

    def test_append_random(self):
        cfg = {
            "random_seed": {
                "file": self._seed_file,
                "data": "tiny-tim-was-here",
            }
        }
        cc_seed_random.handle("test", cfg, get_cloud("ubuntu"), [])
        contents = util.load_file(self._seed_file)
        self.assertEqual("tiny-tim-was-here", contents)

    def test_append_random_unknown_encoding(self):
        data = self._compress(b"tiny-toe")
        cfg = {
            "random_seed": {
                "file": self._seed_file,
                "data": data,
                "encoding": "special_encoding",
            }
        }
        self.assertRaises(
            IOError,
            cc_seed_random.handle,
            "test",
            cfg,
            get_cloud("ubuntu"),
            [],
        )

    def test_append_random_gzip(self):
        data = self._compress(b"tiny-toe")
        cfg = {
            "random_seed": {
                "file": self._seed_file,
                "data": data,
                "encoding": "gzip",
            }
        }
        cc_seed_random.handle("test", cfg, get_cloud("ubuntu"), [])
        contents = util.load_file(self._seed_file)
        self.assertEqual("tiny-toe", contents)

    def test_append_random_gz(self):
        data = self._compress(b"big-toe")
        cfg = {
            "random_seed": {
                "file": self._seed_file,
                "data": data,
                "encoding": "gz",
            }
        }
        cc_seed_random.handle("test", cfg, get_cloud("ubuntu"), [])
        contents = util.load_file(self._seed_file)
        self.assertEqual("big-toe", contents)

    def test_append_random_base64(self):
        data = atomic_helper.b64e("bubbles")
        cfg = {
            "random_seed": {
                "file": self._seed_file,
                "data": data,
                "encoding": "base64",
            }
        }
        cc_seed_random.handle("test", cfg, get_cloud("ubuntu"), [])
        contents = util.load_file(self._seed_file)
        self.assertEqual("bubbles", contents)

    def test_append_random_b64(self):
        data = atomic_helper.b64e("kit-kat")
        cfg = {
            "random_seed": {
                "file": self._seed_file,
                "data": data,
                "encoding": "b64",
            }
        }
        cc_seed_random.handle("test", cfg, get_cloud("ubuntu"), [])
        contents = util.load_file(self._seed_file)
        self.assertEqual("kit-kat", contents)

    def test_append_random_metadata(self):
        cfg = {
            "random_seed": {
                "file": self._seed_file,
                "data": "tiny-tim-was-here",
            }
        }
        c = get_cloud("ubuntu", metadata={"random_seed": "-so-was-josh"})
        cc_seed_random.handle("test", cfg, c, [])
        contents = util.load_file(self._seed_file)
        self.assertEqual("tiny-tim-was-here-so-was-josh", contents)

    def test_seed_command_provided_and_available(self):
        c = get_cloud("ubuntu")
        self.whichdata = {"pollinate": "/usr/bin/pollinate"}
        cfg = {"random_seed": {"command": ["pollinate", "-q"]}}
        cc_seed_random.handle("test", cfg, c, [])

        subp_args = [f["args"] for f in self.subp_called]
        self.assertIn(["pollinate", "-q"], subp_args)

    def test_seed_command_not_provided(self):
        c = get_cloud("ubuntu")
        self.whichdata = {}
        cc_seed_random.handle("test", {}, c, [])

        # subp should not have been called as which would say not available
        self.assertFalse(self.subp_called)

    def test_unavailable_seed_command_and_required_raises_error(self):
        c = get_cloud("ubuntu")
        self.whichdata = {}
        cfg = {
            "random_seed": {
                "command": ["THIS_NO_COMMAND"],
                "command_required": True,
            }
        }
        self.assertRaises(
            ValueError, cc_seed_random.handle, "test", cfg, c, []
        )

    def test_seed_command_and_required(self):
        c = get_cloud("ubuntu")
        self.whichdata = {"foo": "foo"}
        cfg = {"random_seed": {"command_required": True, "command": ["foo"]}}
        cc_seed_random.handle("test", cfg, c, [])

        self.assertIn(["foo"], [f["args"] for f in self.subp_called])

    def test_file_in_environment_for_command(self):
        c = get_cloud("ubuntu")
        self.whichdata = {"foo": "foo"}
        cfg = {
            "random_seed": {
                "command_required": True,
                "command": ["foo"],
                "file": self._seed_file,
            }
        }
        cc_seed_random.handle("test", cfg, c, [])

        # this just instists that the first time subp was called,
        # RANDOM_SEED_FILE was in the environment set up correctly
        subp_env = [f["update_env"] for f in self.subp_called]
        self.assertEqual(subp_env[0].get("RANDOM_SEED_FILE"), self._seed_file)


def apply_patches(patches):
    ret = []
    for (ref, name, replace) in patches:
        if replace is None:
            continue
        orig = getattr(ref, name)
        setattr(ref, name, replace)
        ret.append((ref, name, orig))
    return ret


class TestSeedRandomSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        [
            (
                {"random_seed": {"encoding": "bad"}},
                "'bad' is not one of "
                r"\['raw', 'base64', 'b64', 'gzip', 'gz'\]",
            ),
            (
                {"random_seed": {"command": "foo"}},
                "'foo' is not of type 'array'",
            ),
            (
                {"random_seed": {"command_required": "true"}},
                "'true' is not of type 'boolean'",
            ),
            (
                {"random_seed": {"bad": "key"}},
                "Additional properties are not allowed",
            ),
        ],
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        if error_msg is None:
            validate_cloudconfig_schema(config, get_schema(), strict=True)
        else:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, get_schema(), strict=True)

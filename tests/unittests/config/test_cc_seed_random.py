# This file is part of cloud-init. See LICENSE file for license information.

#    Copyright (C) 2013 Hewlett-Packard Development Company, L.P.
#
#    Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
#    Based on test_handler_set_hostname.py
#
#    This file is part of cloud-init. See LICENSE file for license information.
# pylint: disable=attribute-defined-outside-init
import gzip
import logging
import tempfile
from io import BytesIO
from unittest import mock

import pytest

from cloudinit import atomic_helper, subp, util
from cloudinit.config import cc_seed_random
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import skipUnlessJsonSchema
from tests.unittests.util import get_cloud

LOG = logging.getLogger(__name__)


class TestRandomSeed:
    def setup_method(self):
        self._seed_file = tempfile.mktemp()
        self.unapply = []

        # by default 'which' has nothing in its path
        self.apply_patches([(subp, "which", self._which)])
        self.subp_called = []
        self.whichdata = {}

    def teardown_method(self):
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
        contents = util.load_text_file(self._seed_file)
        assert "tiny-tim-was-here" == contents

    def test_append_random_unknown_encoding(self):
        data = self._compress(b"tiny-toe")
        cfg = {
            "random_seed": {
                "file": self._seed_file,
                "data": data,
                "encoding": "special_encoding",
            }
        }
        pytest.raises(
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
        contents = util.load_text_file(self._seed_file)
        assert "tiny-toe" == contents

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
        contents = util.load_text_file(self._seed_file)
        assert "big-toe" == contents

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
        contents = util.load_text_file(self._seed_file)
        assert "bubbles" == contents

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
        contents = util.load_text_file(self._seed_file)
        assert "kit-kat" == contents

    def test_append_random_metadata(self):
        cfg = {
            "random_seed": {
                "file": self._seed_file,
                "data": "tiny-tim-was-here",
            }
        }
        c = get_cloud("ubuntu", metadata={"random_seed": "-so-was-josh"})
        cc_seed_random.handle("test", cfg, c, [])
        contents = util.load_text_file(self._seed_file)
        assert "tiny-tim-was-here-so-was-josh" == contents

    def test_seed_command_provided_and_available(self):
        c = get_cloud("ubuntu")
        self.whichdata = {"pollinate": "/usr/bin/pollinate"}
        cfg = {"random_seed": {"command": ["pollinate", "-q"]}}
        with mock.patch.object(cc_seed_random.subp, "subp") as subp:
            cc_seed_random.handle("test", cfg, c, [])

        assert (
            mock.call(
                ["pollinate", "-q"],
                update_env={"RANDOM_SEED_FILE": "/dev/urandom"},
                capture=False,
            )
            in subp.call_args_list
        )

    def test_seed_command_not_provided(self):
        c = get_cloud("ubuntu")
        self.whichdata = {}
        cc_seed_random.handle("test", {}, c, [])

        # subp should not have been called as which would say not available
        assert not self.subp_called

    def test_unavailable_seed_command_and_required_raises_error(self):
        c = get_cloud("ubuntu")
        self.whichdata = {}
        cfg = {
            "random_seed": {
                "command": ["THIS_NO_COMMAND"],
                "command_required": True,
            }
        }
        pytest.raises(ValueError, cc_seed_random.handle, "test", cfg, c, [])

    def test_seed_command_and_required(self):
        c = get_cloud("ubuntu")
        self.whichdata = {"foo": "foo"}
        cfg = {"random_seed": {"command_required": True, "command": ["foo"]}}
        with mock.patch.object(cc_seed_random.subp, "subp") as m_subp:
            cc_seed_random.handle("test", cfg, c, [])
        assert (
            mock.call(["foo"], update_env=mock.ANY, capture=mock.ANY)
            == m_subp.call_args
        )

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
        with mock.patch.object(cc_seed_random.subp, "subp") as m_subp:
            cc_seed_random.handle("test", cfg, c, [])

        # this just insists that the first time subp was called,
        # RANDOM_SEED_FILE was in the environment set up correctly
        assert m_subp.call_args == mock.call(
            ["foo"], update_env={"RANDOM_SEED_FILE": mock.ANY}, capture=False
        )


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

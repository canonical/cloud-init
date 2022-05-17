# This file is part of cloud-init. See LICENSE file for license information.

from collections import namedtuple
from io import StringIO

from cloudinit.cmd.devel import render
from cloudinit.helpers import Paths
from cloudinit.sources import INSTANCE_JSON_FILE, INSTANCE_JSON_SENSITIVE_FILE
from cloudinit.util import ensure_dir, write_file
from tests.unittests.helpers import mock, skipUnlessJinja

M_PATH = "cloudinit.cmd.devel.render."


class TestRender:

    Args = namedtuple("Args", "user_data instance_data debug")

    def test_handle_args_error_on_missing_user_data(self, caplog, tmpdir):
        """When user_data file path does not exist, log an error."""
        absent_file = tmpdir.join("user-data")
        instance_data = tmpdir.join("instance-data")
        write_file(instance_data, "{}")
        args = self.Args(
            user_data=absent_file, instance_data=instance_data, debug=False
        )
        with mock.patch("sys.stderr", new_callable=StringIO):
            assert render.handle_args("anyname", args) == 1
        assert "Missing user-data file: %s" % absent_file in caplog.text

    def test_handle_args_error_on_missing_instance_data(self, caplog, tmpdir):
        """When instance_data file path does not exist, log an error."""
        user_data = tmpdir.join("user-data")
        absent_file = tmpdir.join("instance-data")
        args = self.Args(
            user_data=user_data, instance_data=absent_file, debug=False
        )
        with mock.patch("sys.stderr", new_callable=StringIO):
            assert render.handle_args("anyname", args) == 1
        assert (
            "Missing instance-data.json file: %s" % absent_file in caplog.text
        )

    @mock.patch(M_PATH + "read_cfg_paths")
    def test_handle_args_defaults_instance_data(self, m_paths, caplog, tmpdir):
        """When no instance_data argument, default to configured run_dir."""
        user_data = tmpdir.join("user-data")
        run_dir = tmpdir.join("run_dir")
        ensure_dir(run_dir)
        m_paths.return_value = Paths({"run_dir": run_dir})
        args = self.Args(user_data=user_data, instance_data=None, debug=False)
        with mock.patch("sys.stderr", new_callable=StringIO):
            assert render.handle_args("anyname", args) == 1
        json_file = run_dir.join(INSTANCE_JSON_FILE)
        msg = "Missing instance-data.json file: %s" % json_file
        assert msg in caplog.text

    @mock.patch(M_PATH + "read_cfg_paths")
    def test_handle_args_root_fallback_from_sensitive_instance_data(
        self, m_paths, caplog, tmpdir
    ):
        """When root user defaults to sensitive.json."""
        user_data = tmpdir.join("user-data")
        run_dir = tmpdir.join("run_dir")
        ensure_dir(run_dir)
        m_paths.return_value = Paths({"run_dir": run_dir})
        args = self.Args(user_data=user_data, instance_data=None, debug=False)
        with mock.patch("sys.stderr", new_callable=StringIO):
            with mock.patch("os.getuid") as m_getuid:
                m_getuid.return_value = 0
                assert render.handle_args("anyname", args) == 1
        json_file = run_dir.join(INSTANCE_JSON_FILE)
        json_sensitive = run_dir.join(INSTANCE_JSON_SENSITIVE_FILE)
        assert (
            "Missing root-readable %s. Using redacted %s"
            % (json_sensitive, json_file)
            in caplog.text
        )
        assert "Missing instance-data.json file: %s" % json_file in caplog.text

    @mock.patch(M_PATH + "read_cfg_paths")
    def test_handle_args_root_uses_sensitive_instance_data(
        self, m_paths, tmpdir
    ):
        """When root user, and no instance-data arg, use sensitive.json."""
        user_data = tmpdir.join("user-data")
        write_file(user_data, "##template: jinja\nrendering: {{ my_var }}")
        run_dir = tmpdir.join("run_dir")
        ensure_dir(run_dir)
        json_sensitive = run_dir.join(INSTANCE_JSON_SENSITIVE_FILE)
        write_file(json_sensitive, '{"my-var": "jinja worked"}')
        m_paths.return_value = Paths({"run_dir": run_dir})
        args = self.Args(user_data=user_data, instance_data=None, debug=False)
        with mock.patch("sys.stdout", new_callable=StringIO) as m_stdout:
            with mock.patch("os.getuid") as m_getuid:
                m_getuid.return_value = 0
                assert render.handle_args("anyname", args) == 0
        assert "rendering: jinja worked" in m_stdout.getvalue()

    @skipUnlessJinja()
    def test_handle_args_renders_instance_data_vars_in_template(
        self, caplog, tmpdir
    ):
        """If user_data file is a jinja template render instance-data vars."""
        user_data = tmpdir.join("user-data")
        write_file(user_data, "##template: jinja\nrendering: {{ my_var }}")
        instance_data = tmpdir.join("instance-data")
        write_file(instance_data, '{"my-var": "jinja worked"}')
        args = self.Args(
            user_data=user_data, instance_data=instance_data, debug=True
        )
        with mock.patch("sys.stderr", new_callable=StringIO):
            with mock.patch("sys.stdout", new_callable=StringIO) as m_stdout:
                assert render.handle_args("anyname", args) == 0
        assert "Converted jinja variables\n{" in caplog.text
        # TODO enable after pytest>=3.4
        # more info: https://docs.pytest.org/en/stable/how-to/logging.html
        # assert "Converted jinja variables\n{" in m_stderr.getvalue()
        assert "rendering: jinja worked" == m_stdout.getvalue()

    @skipUnlessJinja()
    def test_handle_args_warns_and_gives_up_on_invalid_jinja_operation(
        self, caplog, tmpdir
    ):
        """If user_data file has invalid jinja operations log warnings."""
        user_data = tmpdir.join("user-data")
        write_file(user_data, "##template: jinja\nrendering: {{ my-var }}")
        instance_data = tmpdir.join("instance-data")
        write_file(instance_data, '{"my-var": "jinja worked"}')
        args = self.Args(
            user_data=user_data, instance_data=instance_data, debug=True
        )
        with mock.patch("sys.stderr", new_callable=StringIO):
            assert render.handle_args("anyname", args) == 1
        assert (
            "Ignoring jinja template for %s: Undefined jinja"
            ' variable: "my-var". Jinja tried subtraction. Perhaps you meant'
            ' "my_var"?' % user_data
        ) in caplog.text


# vi: ts=4 expandtab

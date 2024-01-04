# This file is part of cloud-init. See LICENSE file for license information.

from io import StringIO

import pytest

from cloudinit.cmd.devel import render
from cloudinit.helpers import Paths
from cloudinit.templater import JinjaSyntaxParsingException
from cloudinit.util import ensure_dir, write_file
from tests.unittests.helpers import mock, skipUnlessJinja

M_PATH = "cloudinit.cmd.devel.render."


class TestRender:
    @pytest.fixture(autouse=True)
    def mocks(self, mocker):
        mocker.patch("sys.stderr", new_callable=StringIO)

    def test_error_on_missing_user_data(self, caplog, tmpdir):
        """When user_data file path does not exist, log an error."""
        absent_file = tmpdir.join("user-data")
        instance_data = tmpdir.join("instance-data")
        write_file(instance_data, "{}")
        assert render.render_template(absent_file, instance_data, False) == 1
        assert f"Missing user-data file: {absent_file}" in caplog.text

    def test_error_on_missing_instance_data(self, caplog, tmpdir):
        """When instance_data file path does not exist, log an error."""
        user_data = tmpdir.join("user-data")
        absent_file = tmpdir.join("instance-data")
        assert render.render_template(user_data, absent_file, False) == 1
        assert f"Missing instance-data.json file: {absent_file}" in caplog.text

    @mock.patch(f"{M_PATH}read_cfg_paths")
    def test_default_instance_data(self, m_paths, caplog, tmpdir):
        """When no instance_data argument, default to configured run_dir."""
        user_data = tmpdir.join("user-data")
        run_dir = tmpdir.join("run_dir")
        ensure_dir(run_dir)
        paths = Paths({"run_dir": run_dir})
        m_paths.return_value = paths
        assert render.render_template(user_data, None, False) == 1
        json_file = paths.get_runpath("instance_data")
        msg = f"Missing instance-data.json file: {json_file}"
        assert msg in caplog.text

    @mock.patch(f"{M_PATH}read_cfg_paths")
    def test_root_fallback_from_sensitive_instance_data(
        self, m_paths, caplog, tmpdir
    ):
        """When root user defaults to sensitive.json."""
        user_data = tmpdir.join("user-data")
        run_dir = tmpdir.join("run_dir")
        ensure_dir(run_dir)
        paths = Paths({"run_dir": run_dir})
        m_paths.return_value = paths
        with mock.patch("os.getuid") as m_getuid:
            m_getuid.return_value = 0
            assert render.render_template(user_data, None, False) == 1
        json_file = paths.get_runpath("instance_data")
        json_sensitive = paths.get_runpath("instance_data_sensitive")
        assert (
            f"Missing root-readable {json_sensitive}. "
            f"Using redacted {json_file}" in caplog.text
        )

        assert f"Missing instance-data.json file: {json_file}" in caplog.text

    @mock.patch(f"{M_PATH}read_cfg_paths")
    def test_root_uses_sensitive_instance_data(self, m_paths, tmpdir):
        """When root user, and no instance-data arg, use sensitive.json."""
        user_data = tmpdir.join("user-data")
        write_file(user_data, "##template: jinja\nrendering: {{ my_var }}")
        run_dir = tmpdir.join("run_dir")
        json_sensitive = Paths({"run_dir": run_dir}).get_runpath(
            "instance_data_sensitive"
        )

        ensure_dir(run_dir)
        write_file(json_sensitive, '{"my-var": "jinja worked"}')
        m_paths.return_value = Paths({"run_dir": run_dir})
        with mock.patch("sys.stdout", new_callable=StringIO) as m_stdout:
            with mock.patch("os.getuid") as m_getuid:
                m_getuid.return_value = 0
                assert render.render_template(user_data, None, False) == 0
        assert "rendering: jinja worked" in m_stdout.getvalue()

    @skipUnlessJinja()
    def test_renders_instance_data_vars_in_template(self, caplog, tmpdir):
        """If user_data file is a jinja template render instance-data vars."""
        user_data = tmpdir.join("user-data")
        write_file(user_data, "##template: jinja\nrendering: {{ my_var }}")
        instance_data = tmpdir.join("instance-data")
        write_file(instance_data, '{"my-var": "jinja worked"}')
        with mock.patch("sys.stdout", new_callable=StringIO) as m_stdout:
            assert render.render_template(user_data, instance_data, True) == 0
        # Make sure the log is correctly captured. There is an issue
        # with this fixture in pytest==4.6.9 (focal):
        assert (
            "Converted jinja variables\n{" in caplog.records[-1].getMessage()
        )
        assert "rendering: jinja worked" == m_stdout.getvalue()

    @skipUnlessJinja()
    def test_render_warns_and_gives_up_on_invalid_jinja_operation(
        self, caplog, tmpdir
    ):
        """If user_data file has invalid jinja operations log warnings."""
        user_data = tmpdir.join("user-data")
        write_file(user_data, "##template: jinja\nrendering: {{ my-var }}")
        instance_data = tmpdir.join("instance-data")
        write_file(instance_data, '{"my-var": "jinja worked"}')
        assert render.render_template(user_data, instance_data, True) == 1
        assert (
            "Ignoring jinja template for %s: Undefined jinja"
            ' variable: "my-var". Jinja tried subtraction. Perhaps you meant'
            ' "my_var"?' % user_data
        ) in caplog.text

    @skipUnlessJinja()
    def test_jinja_load_error(self, caplog, tmpdir):
        user_data = tmpdir.join("user-data")
        write_file(user_data, "##template: jinja\nrendering: {{ my-var }}")
        instance_data = tmpdir.join("instance-data")
        write_file(instance_data, '{"my-var": "jinja failed"')
        render.render_template(user_data, instance_data, False)
        assert (
            "Cannot render from instance data due to exception" in caplog.text
        )

    @skipUnlessJinja()
    def test_not_jinja_error(self, caplog, tmpdir):
        user_data = tmpdir.join("user-data")
        write_file(user_data, "{{ my-var }}")
        instance_data = tmpdir.join("instance-data")
        write_file(instance_data, '{"my-var": "jinja worked"}')
        render.render_template(user_data, instance_data, False)
        assert (
            "Cannot render from instance data due to exception" in caplog.text
        )

    @skipUnlessJinja()
    def test_no_user_data(self, caplog, tmpdir):
        user_data = tmpdir.join("user-data")
        write_file(user_data, "##template: jinja")
        instance_data = tmpdir.join("instance-data")
        write_file(instance_data, '{"my-var": "jinja worked"}')
        render.render_template(user_data, instance_data, False)
        assert "Unable to render user-data file" in caplog.text

    @skipUnlessJinja()
    def test_invalid_jinja_syntax(self, caplog, tmpdir):
        user_data = tmpdir.join("user-data")
        write_file(user_data, "##template: jinja\nrendering: {{ my_var } }")
        instance_data = tmpdir.join("instance-data")
        write_file(instance_data, '{"my-var": "jinja worked"}')
        assert render.render_template(user_data, instance_data, True) == 1
        assert (
            JinjaSyntaxParsingException.format_error_message(
                syntax_error="unexpected '}'",
                line_number=2,
                line_content="rendering: {{ my_var } }",
            )
            in caplog.text
        )

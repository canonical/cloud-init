# This file is part of cloud-init. See LICENSE file for license information.
import datetime
import functools
import logging
import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from tarfile import TarFile
from typing import Dict, Generator, Iterator, List, Type

import pytest
from pycloudlib.lxd.instance import LXDInstance

from tests.integration_tests import integration_settings
from tests.integration_tests.clouds import (
    AzureCloud,
    Ec2Cloud,
    GceCloud,
    IbmCloud,
    IntegrationCloud,
    LxdContainerCloud,
    LxdVmCloud,
    OciCloud,
    OpenstackCloud,
    QemuCloud,
    _LxdIntegrationCloud,
)
from tests.integration_tests.instances import (
    CloudInitSource,
    IntegrationInstance,
)

log = logging.getLogger("integration_testing")
log.addHandler(logging.StreamHandler(sys.stdout))
log.setLevel(logging.INFO)

platforms: Dict[str, Type[IntegrationCloud]] = {
    "ec2": Ec2Cloud,
    "gce": GceCloud,
    "azure": AzureCloud,
    "oci": OciCloud,
    "ibm": IbmCloud,
    "lxd_container": LxdContainerCloud,
    "lxd_vm": LxdVmCloud,
    "qemu": QemuCloud,
    "openstack": OpenstackCloud,
}
os_list = ["ubuntu"]

session_start_time = datetime.datetime.now().strftime("%y%m%d%H%M%S")


def pytest_runtest_setup(item):
    """Skip tests on unsupported clouds.

    A test can take any number of marks to specify the platforms it can
    run on. If a platform(s) is specified and we're not running on that
    platform, then skip the test. If platform specific marks are not
    specified, then we assume the test can be run anywhere.
    """
    test_marks = [mark.name for mark in item.iter_markers()]
    if "unstable" in test_marks and not integration_settings.RUN_UNSTABLE:
        pytest.skip("Test marked unstable. Manually remove mark to run it")


# disable_subp_usage is defined at a higher level, but we don't
# want it applied here
@pytest.fixture()
def disable_subp_usage(request):
    pass


@pytest.fixture(scope="session")
def session_cloud() -> Generator[IntegrationCloud, None, None]:
    if integration_settings.PLATFORM not in platforms.keys():
        raise ValueError(
            f"{integration_settings.PLATFORM} is an invalid PLATFORM "
            f"specified in settings. Must be one of {list(platforms.keys())}"
        )

    cloud = platforms[integration_settings.PLATFORM]()
    cloud.emit_settings_to_log()
    yield cloud
    cloud.destroy()


def get_validated_source(
    session_cloud: IntegrationCloud,
    source=integration_settings.CLOUD_INIT_SOURCE,
) -> CloudInitSource:
    if source == "NONE":
        return CloudInitSource.NONE
    elif source == "IN_PLACE":
        if session_cloud.datasource not in ["lxd_container", "lxd_vm"]:
            raise ValueError(
                "IN_PLACE as CLOUD_INIT_SOURCE only works for LXD"
            )
        return CloudInitSource.IN_PLACE
    elif source == "PROPOSED":
        return CloudInitSource.PROPOSED
    elif source.startswith("ppa:"):
        return CloudInitSource.PPA
    elif os.path.isfile(str(source)):
        return CloudInitSource.DEB_PACKAGE
    elif source == "UPGRADE":
        return CloudInitSource.UPGRADE
    raise ValueError(f"Invalid value for CLOUD_INIT_SOURCE setting: {source}")


@pytest.fixture(scope="session")
def setup_image(session_cloud: IntegrationCloud, request):
    """Setup the target environment with the correct version of cloud-init.

    So we can launch instances / run tests with the correct image
    """
    source = get_validated_source(session_cloud)
    if not (
        source.installs_new_version()
        or integration_settings.INCLUDE_COVERAGE
        or integration_settings.INCLUDE_PROFILE
    ):
        return
    log.info("Setting up source image")
    client = session_cloud.launch()
    if source.installs_new_version():
        log.info("Installing cloud-init from %s", source.name)
        client.install_new_cloud_init(source)
    if (
        integration_settings.INCLUDE_PROFILE
        and integration_settings.INCLUDE_COVERAGE
    ):
        log.error(
            "Invalid configuration, cannot enable both profile and coverage."
        )
        raise ValueError()
    if integration_settings.INCLUDE_COVERAGE:
        log.info("Installing coverage")
        client.install_coverage()
    elif integration_settings.INCLUDE_PROFILE:
        log.info("Installing profiler")
        client.install_profile()
    # All done customizing the image, so snapshot it and make it global
    snapshot_id = client.snapshot()
    client.cloud.snapshot_id = snapshot_id
    # Even if we're keeping instances, we don't want to keep this
    # one around as it was just for image creation
    client.destroy()
    log.info("Done with environment setup")

    # For some reason a yield here raises a
    # ValueError: setup_image did not yield a value
    # during setup so use a finalizer instead.
    request.addfinalizer(session_cloud.delete_snapshot)


def _collect_logs(instance: IntegrationInstance, log_dir: Path):
    instance.execute(
        "cloud-init collect-logs -u -t /var/tmp/cloud-init.tar.gz"
    )
    log.info("Writing logs to %s", log_dir)

    tarball_path = log_dir / "cloud-init.tar.gz"
    try:
        instance.pull_file("/var/tmp/cloud-init.tar.gz", tarball_path)
    except Exception as e:
        log.error("Failed to pull logs: %s", e)
        return

    tarball = TarFile.open(str(tarball_path))
    tarball.extractall(path=str(log_dir))
    tarball_path.unlink()


def _collect_coverage(instance: IntegrationInstance, log_dir: Path):
    log.info("Writing coverage report to %s", log_dir)
    try:
        instance.pull_file("/.coverage", log_dir / ".coverage")
    except Exception as e:
        log.error("Failed to pull coverage for: %s", e)


def _collect_profile(instance: IntegrationInstance, log_dir: Path):
    log.info("Writing profile to %s", log_dir)
    try:
        (log_dir / "profile").mkdir(parents=True)
        instance.pull_file(
            "/var/log/cloud-init-local.service.stats",
            log_dir / "profile" / "local.stats",
        )
        instance.pull_file(
            "/var/log/cloud-init.service.stats",
            log_dir / "profile" / "network.stats",
        )
        instance.pull_file(
            "/var/log/cloud-config.service.stats",
            log_dir / "profile" / "config.stats",
        )
        instance.pull_file(
            "/var/log/cloud-final.service.stats",
            log_dir / "profile" / "final.stats",
        )
    except Exception as e:
        log.error("Failed to pull profile for: %s", e)


def _setup_artifact_paths(node_id: str):
    parent_dir = Path(integration_settings.LOCAL_LOG_PATH, session_start_time)

    node_id_path = Path(
        node_id.replace(
            ".py", ""
        )  # Having a directory with '.py' would be weird
        .replace("::", os.path.sep)  # Turn classes/tests into paths
        .replace("[", "-")  # For parametrized names
        .replace("]", "")  # For parameterized names
    )
    log_dir = parent_dir / node_id_path

    # Create log dir if not exists
    if not log_dir.exists():
        log_dir.mkdir(parents=True)

    # Add a symlink to the latest log output directory
    last_symlink = Path(integration_settings.LOCAL_LOG_PATH) / "last"
    if os.path.islink(last_symlink):
        os.unlink(last_symlink)
    os.symlink(parent_dir, last_symlink)
    return log_dir


def _collect_artifacts(
    instance: IntegrationInstance, node_id: str, test_failed: bool
):
    """Collect artifacts from remote instance.

    Args:
        instance: The current IntegrationInstance to collect artifacts from
        node_id: The pytest representation of this test, E.g.:
            tests/integration_tests/test_example.py::TestExample.test_example
        test_failed: If test failed or not
    """
    should_collect_logs = integration_settings.COLLECT_LOGS == "ALWAYS" or (
        integration_settings.COLLECT_LOGS == "ON_ERROR" and test_failed
    )
    should_collect_coverage = integration_settings.INCLUDE_COVERAGE
    should_collect_profile = integration_settings.INCLUDE_PROFILE
    if not (
        should_collect_logs
        or should_collect_coverage
        or should_collect_profile
    ):
        return

    log_dir = _setup_artifact_paths(node_id)

    if should_collect_logs:
        _collect_logs(instance, log_dir)

    if should_collect_coverage:
        _collect_coverage(instance, log_dir)

    elif should_collect_profile:
        _collect_profile(instance, log_dir)


@contextmanager
def _client(
    request, fixture_utils, session_cloud: IntegrationCloud
) -> Iterator[IntegrationInstance]:
    """Fixture implementation for the client fixtures.

    Launch the dynamic IntegrationClient instance using any provided
    userdata, yield to the test, then cleanup
    """
    getter = functools.partial(
        fixture_utils.closest_marker_first_arg_or, request, default=None
    )
    user_data = getter("user_data")
    name = getter("instance_name")
    lxd_config_dict = getter("lxd_config_dict")
    lxd_setup = getter("lxd_setup")
    lxd_use_exec = fixture_utils.closest_marker_args_or(
        request, "lxd_use_exec", None
    )
    launch_kwargs = {}
    if name is not None:
        launch_kwargs["name"] = name
    if lxd_config_dict is not None:
        if not isinstance(session_cloud, _LxdIntegrationCloud):
            pytest.skip("lxd_config_dict requires LXD")
        launch_kwargs["config_dict"] = lxd_config_dict
    if lxd_use_exec is not None:
        if not isinstance(session_cloud, _LxdIntegrationCloud):
            pytest.skip("lxd_use_exec requires LXD")
        launch_kwargs["execute_via_ssh"] = False
    local_launch_kwargs = {}
    if lxd_setup is not None:
        if not isinstance(session_cloud, _LxdIntegrationCloud):
            pytest.skip("lxd_setup requires LXD")
        local_launch_kwargs["lxd_setup"] = lxd_setup

    with session_cloud.launch(
        user_data=user_data, launch_kwargs=launch_kwargs, **local_launch_kwargs
    ) as instance:
        if lxd_use_exec is not None and isinstance(
            instance.instance, LXDInstance
        ):
            # Existing instances are not affected by the launch kwargs, so
            # ensure it here; we still need the launch kwarg so waiting works
            instance.instance.execute_via_ssh = False
        previous_failures = request.session.testsfailed
        yield instance
        test_failed = request.session.testsfailed - previous_failures > 0
        _collect_artifacts(instance, request.node.nodeid, test_failed)


@pytest.fixture
def client(  # pylint: disable=W0135
    request, fixture_utils, session_cloud, setup_image
) -> Iterator[IntegrationInstance]:
    """Provide a client that runs for every test."""
    with _client(request, fixture_utils, session_cloud) as client:
        yield client


@pytest.fixture(scope="module")
def module_client(  # pylint: disable=W0135
    request, fixture_utils, session_cloud, setup_image
) -> Iterator[IntegrationInstance]:
    """Provide a client that runs once per module."""
    with _client(request, fixture_utils, session_cloud) as client:
        yield client


@pytest.fixture(scope="class")
def class_client(  # pylint: disable=W0135
    request, fixture_utils, session_cloud, setup_image
) -> Iterator[IntegrationInstance]:
    """Provide a client that runs once per class."""
    with _client(request, fixture_utils, session_cloud) as client:
        yield client


def pytest_assertrepr_compare(op, left, right):
    """Custom integration test assertion explanations.

    See
    https://docs.pytest.org/en/stable/assert.html#defining-your-own-explanation-for-failed-assertions
    for pytest's documentation.
    """
    if op == "not in" and isinstance(left, str) and isinstance(right, str):
        # This stanza emits an improved assertion message if we're testing for
        # the presence of a string within a cloud-init log: it will report only
        # the specific lines containing the string (instead of the full log,
        # the default behaviour).
        potential_log_lines = right.splitlines()
        first_line = potential_log_lines[0]
        if "DEBUG" in first_line and "Cloud-init" in first_line:
            # We are looking at a cloud-init log, so just pick out the relevant
            # lines
            found_lines = [
                line for line in potential_log_lines if left in line
            ]
            return [
                '"{}" not in cloud-init.log string; unexpectedly found on'
                " these lines:".format(left)
            ] + found_lines


def pytest_configure(config):
    """Perform initial configuration, before the test runs start.

    This hook is only called if integration tests are being executed, so we can
    use it to configure defaults for integration testing that differ from the
    rest of the tests in the codebase.

    See
    https://docs.pytest.org/en/latest/reference.html#_pytest.hookspec.pytest_configure
    for pytest's documentation.
    """
    if "log_cli_level" in config.option and not config.option.log_cli_level:
        # If log_cli_level is available in this version of pytest and not set
        # to anything, set it to INFO.
        config.option.log_cli_level = "INFO"


def _copy_coverage_files(parent_dir: Path) -> List[Path]:
    combined_files = []
    for dirpath in parent_dir.rglob("*"):
        if (dirpath / ".coverage").exists():
            # Construct the new filename
            relative_dir = dirpath.relative_to(parent_dir)
            new_filename = ".coverage." + str(relative_dir).replace(
                os.sep, "-"
            )
            new_filepath = parent_dir / new_filename

            # Copy the file
            shutil.copy(dirpath / ".coverage", new_filepath)
            combined_files.append(new_filepath)
    return combined_files


def _generate_coverage_report() -> None:
    log.info("Generating coverage report")
    parent_dir = Path(integration_settings.LOCAL_LOG_PATH, session_start_time)
    coverage_files = _copy_coverage_files(parent_dir)
    subprocess.run(
        ["coverage", "combine"] + [str(f) for f in coverage_files],
        check=True,
        cwd=str(parent_dir),
        stdout=subprocess.DEVNULL,
    )
    html_dir = parent_dir / "html"
    html_dir.mkdir()
    subprocess.run(
        [
            "coverage",
            "html",
            f"--data-file={parent_dir / '.coverage'}",
            f"--directory={html_dir}",
            "--ignore-errors",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    log.info("Coverage report generated")


def _generate_profile_report() -> None:
    log.info("Profile reports generated, run the following to view:")
    command = (
        "python3 -m snakeviz /tmp/cloud_init_test_logs/"
        "last/tests/integration_tests/*/*/*/profile/%s"
    )
    log.info(command, "local.stats")
    log.info(command, "network.stats")
    log.info(command, "config.stats")
    log.info(command, "final.stats")


def pytest_sessionfinish(session, exitstatus) -> None:
    if integration_settings.INCLUDE_COVERAGE:
        _generate_coverage_report()
    elif integration_settings.INCLUDE_PROFILE:
        _generate_profile_report()

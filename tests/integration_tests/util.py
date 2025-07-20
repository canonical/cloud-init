import json
import logging
import multiprocessing
import os
import re
import time
from collections import namedtuple
from contextlib import contextmanager
from datetime import datetime
from functools import lru_cache
from itertools import chain
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Set, Union

import pytest

from cloudinit.subp import subp
from tests.integration_tests.decorators import retry
from tests.integration_tests.integration_settings import (
    OS_IMAGE_TYPE,
    PLATFORM,
)
from tests.integration_tests.releases import CURRENT_RELEASE, NOBLE

LOG = logging.getLogger("integration_testing.util")

if TYPE_CHECKING:
    # instances.py has imports util.py, so avoid circular import
    from tests.integration_tests.instances import IntegrationInstance

log = logging.getLogger("integration_testing")
key_pair = namedtuple("key_pair", "public_key private_key")

ASSETS_DIR = Path("tests/integration_tests/assets")
KEY_PATH = ASSETS_DIR / "keys"

HAS_CONSOLE_LOG = PLATFORM in (
    "ec2",
    "lxd_container",
    "oci",
    "openstack",
    "qemu",
)


def verify_ordered_items_in_text(to_verify: list, text: str):
    """Assert all items in list appear in order in text.

    Examples:
      verify_ordered_items_in_text(['a', '1'], 'ab1')  # passes
      verify_ordered_items_in_text(['1', 'a'], 'ab1')  # raises AssertionError
    """
    index = 0
    for item in to_verify:
        try:
            matched = re.search(item, text[index:])
        except re.error:
            matched = re.search(re.escape(item), text[index:])
        assert matched, "Expected item not found: '{}'".format(item)
        index = matched.start()


def _format_found(header: str, items: list) -> str:
    """Helper function to format assertion message"""

    # do nothing, allows this formatter to be "stackable"
    if not items:
        return ""

    # if only one error put the header and the error message on a single line
    if 1 == len(items):
        return f"\n{header}: {items.pop(0)}"

    # otherwise make a list after header
    else:
        return f"\n{header}:\n\t- " + "\n\t- ".join(items)


def verify_clean_boot(
    instance: "IntegrationInstance",
    *,
    ignore_deprecations: Optional[Union[List[str], bool]] = None,
    ignore_warnings: Optional[Union[List[str], bool]] = None,
    ignore_errors: Optional[Union[List[str], bool]] = None,
    ignore_tracebacks: Optional[Union[List[str], bool]] = None,
    require_deprecations: Optional[list] = None,
    require_warnings: Optional[list] = None,
    require_errors: Optional[list] = None,
    verify_schema: Optional[bool] = True,
):
    """Raise exception if the client experienced unexpected conditions.

    Fail when a required error, warning, or deprecation isn't found.

    Platform-specific conditions are defined in this function.

    This function is similar to verify_clean_log, hence the similar name.

    differences from verify_clean_log:

    - more expressive syntax
    - extensible (can be easily extended for other log levels)
    - less resource intensive (no log copying required)
    - nice error formatting

    :param instance: test instance
    :param ignored_deprecations: list of deprecation messages to ignore, or
        true to ignore all
    :param ignored_warnings: list of expected warnings to ignore, or true to
        ignore all
    :param ignored_errors: list of expected errors to ignore, or true to ignore
        all
    :param require_deprecations: list of expected deprecation messages to
        require
    :param require_warnings: list of expected warning messages to require
    :param require_errors: list of expected error messages to require
    :param verify_schema: bool set True to validate cloud-init schema --system
    """

    def append_or_create_list(
        maybe_list: Optional[Union[List[str], bool]], value: str
    ) -> Optional[Union[List[str], bool]]:
        """handle multiple types"""
        if isinstance(maybe_list, list):
            maybe_list.append(value)
        elif maybe_list is True:
            return True  # Ignoring all texts, so no need to append.
        elif maybe_list in (None, False):
            maybe_list = [value]
        return maybe_list

    if ignore_tracebacks is None:
        ignore_tracebacks = []
    # Define exceptions by matrix of platform and Ubuntu release
    if "azure" == PLATFORM:
        # Consistently on all Azure launches:
        ignore_warnings = append_or_create_list(
            ignore_warnings, "No lease found; using default endpoint"
        )
    elif "lxd_vm" == PLATFORM:
        # Ubuntu lxd storage
        ignore_warnings = append_or_create_list(
            ignore_warnings, "thinpool by default on Ubuntu due to LP #1982780"
        )
        ignore_warnings = append_or_create_list(
            ignore_warnings,
            "Could not match supplied host pattern, ignoring:",
        )
    elif "oci" == PLATFORM:
        # LP: #1842752
        ignore_errors = append_or_create_list(
            ignore_warnings, "Stderr: RTNETLINK answers: File exists"
        )
        if isinstance(ignore_tracebacks, list):
            ignore_tracebacks.append("Stderr: RTNETLINK answers: File exists")
        # Ubuntu lxd storage
        ignore_warnings = append_or_create_list(
            ignore_warnings, "thinpool by default on Ubuntu due to LP #1982780"
        )
        # LP: #1833446
        ignore_warnings = append_or_create_list(
            ignore_warnings,
            "UrlError: 404 Client Error: Not Found for url: "
            "http://169.254.169.254/latest/meta-data/",
        )
        if isinstance(ignore_tracebacks, list):
            ignore_tracebacks.append(
                "UrlError: 404 Client Error: Not Found for url: "
                "http://169.254.169.254/latest/meta-data/"
            )
        # Oracle has a file in /etc/cloud/cloud.cfg.d that contains
        # users:
        # - default
        # - name: opc
        #   ssh_redirect_user: true
        # This can trigger a warning about opc having no public key
        ignore_warnings = append_or_create_list(
            ignore_warnings,
            "Unable to disable SSH logins for opc given ssh_redirect_user",
        )
    # Preserve platform-specific tracebacks expected
    _verify_clean_boot(
        instance,
        ignore_deprecations=ignore_deprecations,
        ignore_warnings=ignore_warnings,
        ignore_errors=ignore_errors,
        ignore_tracebacks=ignore_tracebacks,
        require_deprecations=require_deprecations,
        require_warnings=require_warnings,
        require_errors=require_errors,
        verify_schema=verify_schema,
    )


def _verify_clean_boot(
    instance: "IntegrationInstance",
    ignore_deprecations: Optional[Union[List[str], bool]] = None,
    ignore_warnings: Optional[Union[List[str], bool]] = None,
    ignore_errors: Optional[Union[List[str], bool]] = None,
    ignore_tracebacks: Optional[Union[List[str], bool]] = None,
    require_deprecations: Optional[list] = None,
    require_warnings: Optional[list] = None,
    require_errors: Optional[list] = None,
    verify_schema: Optional[bool] = True,
):
    ignore_deprecations = ignore_deprecations or []
    ignore_errors = ignore_errors or []
    ignore_warnings = ignore_warnings or []
    require_deprecations = require_deprecations or []
    require_errors = require_errors or []
    require_warnings = require_warnings or []
    status = json.loads(instance.execute("cloud-init status --format=json"))

    unexpected_deprecations = set()
    unexpected_errors = set()
    unexpected_warnings = set()

    required_deprecations_found = set()
    required_warnings_found = set()
    required_errors_found = set()

    for current_error in status["errors"]:

        # check for required errors
        for expected in require_errors:
            if expected in current_error:
                required_errors_found.add(expected)

        if ignore_errors is True:
            continue
        # check for unexpected errors
        for expected in [*ignore_errors, *require_errors]:
            if expected in current_error:
                break
        else:
            unexpected_errors.add(current_error)

    # check for unexpected warnings
    for current_warning in status["recoverable_errors"].get("WARNING", []):

        # check for required warnings
        for expected in require_warnings:
            if expected in current_warning:
                required_warnings_found.add(expected)

        if ignore_warnings is True:
            continue
        # check for unexpected warnings
        for expected in [*ignore_warnings, *require_warnings]:
            if expected in current_warning:
                break
        else:
            unexpected_warnings.add(current_warning)

    # check for unexpected deprecations
    for current_deprecation in status["recoverable_errors"].get(
        "DEPRECATED", []
    ):

        # check for required deprecations
        for expected in require_deprecations:
            if expected in current_deprecation:
                required_deprecations_found.add(expected)

        if ignore_deprecations is True:
            continue
        # check for unexpected deprecations
        for expected in [*ignore_deprecations, *require_deprecations]:
            if expected in current_deprecation:
                break
        else:
            unexpected_deprecations.add(current_deprecation)

    required_errors_not_found = set(require_errors) - required_errors_found
    required_warnings_not_found = (
        set(require_warnings) - required_warnings_found
    )
    required_deprecations_not_found = (
        set(require_deprecations) - required_deprecations_found
    )

    # ordered from most severe to least severe
    # this allows the first message printed to be the most significant
    errors = [
        *unexpected_errors,
        *required_errors_not_found,
        *unexpected_warnings,
        *required_warnings_not_found,
        *unexpected_deprecations,
        *required_deprecations_not_found,
    ]
    if errors:
        message = ""
        # if there is only one message, don't include the generic header
        # so that the user can read the exact message in the pytest summary
        if len(errors) > 1:
            # more than one error, so include a generic message
            message += "Unexpected warnings or errors found"

        # errors are probably more important, order them first
        message += _format_found(
            "Found unexpected errors", list(unexpected_errors)
        )
        message += _format_found(
            "Required errors not found", list(required_errors_not_found)
        )
        message += _format_found(
            "Found unexpected warnings", list(unexpected_warnings)
        )
        message += _format_found(
            "Required warnings not found", list(required_warnings_not_found)
        )
        message += _format_found(
            "Found unexpected deprecations", list(unexpected_deprecations)
        )
        message += _format_found(
            "Required deprecations not found",
            list(required_deprecations_not_found),
        )
        assert not errors, message

    # assert no unexpected Tracebacks
    if ignore_tracebacks is not True:
        expected_traceback_count = 0
        traceback_count = int(
            instance.execute(
                "grep --count Traceback /var/log/cloud-init.log"
            ).stdout.strip()
        )
        if ignore_tracebacks:
            for expected_traceback in ignore_tracebacks:
                expected_traceback_count += int(
                    instance.execute(
                        f"grep --count '{expected_traceback}'"
                        " /var/log/cloud-init.log"
                    ).stdout.strip()
                )
        assert expected_traceback_count == traceback_count, (
            f"{traceback_count - expected_traceback_count} unexpected "
            "traceback(s) found in /var/log/cloud-init.log"
        )

    # check that the return code of cloud-init status is expected
    if not any(
        [
            ignore_deprecations,
            ignore_warnings,
            ignore_errors,
            ignore_tracebacks,
            require_deprecations,
            require_warnings,
            require_errors,
        ]
    ):
        # make sure that return code is 0 when all was good
        out = instance.execute("cloud-init status --long")
        assert out.ok, (
            "Unexpected non-zero return code from "
            f"`cloud-init status`: {out.return_code}\nstdout: "
            f"{out.stdout}\nstderr: {out.stderr}"
        )
    elif any(
        [
            ignore_deprecations,
            ignore_warnings,
            ignore_errors,
            ignore_tracebacks,
        ]
    ):
        # Ignore is optional, so we can't be sure whether we will got a return
        # code of 0 or 2. This makes this function more useful when writing
        # tests that run on series with different behavior. In this case we
        # cannot be sure whether it will return 0 or 2, but we never want to
        # see a return code of 1, so assert that it isn't 1.
        out = instance.execute("cloud-init status --long")
        assert 1 != out.return_code, (
            f"Unexpected return code from `cloud-init status`. Expected rc=0 "
            f"or rc=2, received rc={out.return_code}\nstdout:\n"
            f"{out.stdout}\nstderr:\n{out.stderr}"
        )
    else:
        # Look at the commit history before making changes here.
        # Behavior on Jenkins, GH CI, and local runs must be considered
        # for all series.
        out = instance.execute("cloud-init status --long")
        rc = 2
        if CURRENT_RELEASE < NOBLE:
            rc = 0
        assert rc == out.return_code, (
            f"Unexpected return code from `cloud-init status`. "
            f"Expected rc={rc}, received rc={out.return_code}\nstdout: "
            f"{out.stdout}\nstderr: {out.stderr}"
        )
    if not verify_schema:
        return
    schema = instance.execute("cloud-init schema --system --annotate")
    if "ibm" == PLATFORM:
        # IBM provides invalid vendor-data resulting in schema errors
        assert "Invalid schema: vendor-data" in schema.stderr
        assert not schema.ok, (
            f"Expected IBM schema validation errors due to vendor-data, did "
            f"IBM images resolve this?\nstdout: {schema.stdout}\n"
            f"stderr:\n{schema.stderr}"
        )
    else:
        assert schema.ok, (
            f"Schema validation failed\nstdout:{schema.stdout}"
            f"\nstderr:\n{schema.stderr}"
        )


def verify_clean_log(log: str, ignore_deprecations: bool = True):
    """Assert no unexpected tracebacks or warnings in logs"""
    if ignore_deprecations:
        is_deprecated = re.compile("deprecat", flags=re.IGNORECASE)
        log_lines = log.split("\n")
        log_lines = list(
            filter(lambda line: not is_deprecated.search(line), log_lines)
        )
        log = "\n".join(log_lines)

    error_logs = re.findall("CRITICAL.*", log) + re.findall("ERROR.*", log)
    if error_logs:
        raise AssertionError(
            "Found unexpected errors: %s" % "\n".join(error_logs)
        )
    if re.findall("Cloud-init.*received SIG", log):
        raise AssertionError(
            "Found unexpected signal termination: %s" % "\n".join(error_logs)
        )

    warning_count = log.count("[WARNING]")
    expected_warnings = 0
    traceback_count = log.count("Traceback")
    expected_tracebacks = 0

    warning_texts = [
        # Consistently on all Azure launches:
        # azure.py[WARNING]: No lease found; using default endpoint
        "No lease found; using default endpoint",
        # Ubuntu lxd storage
        "thinpool by default on Ubuntu due to LP #1982780",
        "WARNING]: Could not match supplied host pattern, ignoring:",
    ]
    traceback_texts = []
    if "install canonical-livepatch" in log:
        # Ubuntu Pro Client emits a warning in between installing livepatch
        # and enabling it
        warning_texts.append(
            "canonical-livepatch returned error when checking status"
        )
    if "found network data from DataSourceNone" in log:
        warning_texts.append("Used fallback datasource")
    if "oracle" in log:
        # LP: #1842752
        lease_exists_text = "Stderr: RTNETLINK answers: File exists"
        warning_texts.append(lease_exists_text)
        traceback_texts.append(lease_exists_text)
        # LP: #1833446
        fetch_error_text = (
            "UrlError: 404 Client Error: Not Found for url: "
            "http://169.254.169.254/latest/meta-data/"
        )
        warning_texts.append(fetch_error_text)
        traceback_texts.append(fetch_error_text)
        # Oracle has a file in /etc/cloud/cloud.cfg.d that contains
        # users:
        # - default
        # - name: opc
        #   ssh_redirect_user: true
        # This can trigger a warning about opc having no public key
        warning_texts.append(
            "Unable to disable SSH logins for opc given ssh_redirect_user"
        )

    for warning_text in warning_texts:
        expected_warnings += log.count(warning_text)
    for traceback_text in traceback_texts:
        expected_tracebacks += log.count(traceback_text)

    assert warning_count <= expected_warnings, (
        f"Unexpected warning count != {expected_warnings}. Found: "
        f"{re.findall('WARNING.*', log)}"
    )
    assert traceback_count == expected_tracebacks


def get_inactive_modules(log: str) -> Set[str]:
    matches = re.findall(
        r"Skipping modules '(.*)' because no applicable config is provided.",
        log,
    )
    return set(
        map(
            lambda module: module.strip(),
            chain(*map(lambda match: match.split(","), matches)),
        )
    )


@contextmanager
def emit_dots_on_travis():
    """emit a dot every 60 seconds if running on Travis.

    Travis will kill jobs that don't emit output for a certain amount of time.
    This context manager spins up a background process which will emit a dot to
    stdout every 60 seconds to avoid being killed.

    It should be wrapped selectively around operations that are known to take a
    long time.
    """
    if os.environ.get("TRAVIS") != "true":
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


def get_test_rsa_keypair(key_name: str = "test1") -> key_pair:
    private_key_path = KEY_PATH / "id_rsa.{}".format(key_name)
    public_key_path = KEY_PATH / "id_rsa.{}.pub".format(key_name)
    with public_key_path.open() as public_file:
        public_key = public_file.read()
    with private_key_path.open() as private_file:
        private_key = private_file.read()
    return key_pair(public_key, private_key)


# We're implementing our own here in case cloud-init status --wait
# isn't working correctly (LP: #1966085)
def wait_for_cloud_init(client: "IntegrationInstance", num_retries: int = 30):
    last_exception = None
    for _ in range(num_retries):
        try:
            result = client.execute("cloud-init status")
            if result.return_code in (0, 2) and (
                "running" not in result or "not started" not in result
            ):
                return result
        except Exception as e:
            last_exception = e
        time.sleep(1)
    raise Exception(  # pylint: disable=W0719
        "cloud-init status did not return successfully."
    ) from last_exception


def get_console_log(client: "IntegrationInstance"):
    try:
        console_log = client.instance.console_log()
    except NotImplementedError:
        pytest.skip("NotImplementedError when requesting console log")
    except RuntimeError as e:
        if "open : no such file or directory" in str(e):
            if hasattr(client, "lxc_log"):
                return client.lxc_log
        raise e
    if console_log is None:
        pytest.skip("Console log has not been setup")
    if console_log.lower().startswith("no console output"):
        pytest.fail("no console output")
    if PLATFORM in ("lxd_vm", "lxd_container"):
        # Preserve non empty console log on lxc platforms because
        # lxc console --show-log can be called once and the log is flushed.
        # Multiple calls to --show-log error on "no such file or directory".
        client.lxc_log = console_log  # type: ignore[attr-defined]
    return console_log


@retry(tries=5, delay=1)  # Retry on get_console_log failures
def get_syslog_or_console(client: "IntegrationInstance") -> str:
    """minimal OS_IMAGE_TYPE does not contain rsyslog"""
    if OS_IMAGE_TYPE == "minimal" and HAS_CONSOLE_LOG:
        return get_console_log(client)
    else:
        return client.read_from_file("/var/log/syslog")


@lru_cache()
def lxd_has_nocloud(client: "IntegrationInstance") -> bool:
    # Bionic or Focal may be detected as NoCloud rather than LXD
    lxd_image_metadata = subp(
        ["lxc", "config", "metadata", "show", client.instance.name]
    )
    return "/var/lib/cloud/seed/nocloud" in lxd_image_metadata.stdout


def get_feature_flag_value(client: "IntegrationInstance", key):
    value = client.execute(
        'python3 -c "from cloudinit import features; '
        f'print(features.{key})"'
    ).strip()
    if "NameError" in value:
        raise NameError(f"name '{key}' is not defined")
    return value


def has_netplanlib(client: "IntegrationInstance") -> bool:
    """Return True if netplan python3 pkg is installed on the instance."""
    return client.execute("dpkg-query -W python3-netplan").ok


def override_kernel_command_line(ds_str: str, instance: "IntegrationInstance"):
    """set the kernel command line and reboot, return after boot done

    This will not work with containers. This is only tested with lxd vms
    but in theory should work on any virtual machine using grub.

    ds_str: the string that will be inserted into /proc/cmdline
    instance: instance to set kernel command line for
    """

    # The final output in /etc/default/grub should be:
    #
    # GRUB_CMDLINE_LINUX="'ds=nocloud;s=http://my-url/'"
    #
    # That ensures that the kernel command line passed into
    # /boot/efi/EFI/ubuntu/grub.cfg will be properly single-quoted
    #
    # Example:
    #
    # linux /boot/vmlinuz-5.15.0-1030-kvm ro 'ds=nocloud;s=http://my-url/'
    #
    # Not doing this will result in a semicolon-delimited ds argument
    # terminating the kernel arguments prematurely.
    assert instance.execute(
        'printf "GRUB_CMDLINE_LINUX=\\"" >> /etc/default/grub'
    ).ok
    assert instance.execute('printf "\'" >> /etc/default/grub').ok
    assert instance.execute(f"printf '{ds_str}' >> /etc/default/grub").ok
    assert instance.execute('printf "\'\\"" >> /etc/default/grub').ok

    # We should probably include non-systemd distros at some point. This should
    # most likely be as simple as updating the output path for grub-mkconfig
    assert instance.execute(
        "grub-mkconfig -o /boot/efi/EFI/ubuntu/grub.cfg"
    ).ok
    assert instance.execute("cloud-init clean --logs").ok
    instance.restart()


def push_and_enable_systemd_unit(
    client: "IntegrationInstance", unit_name: str, content: str
) -> None:
    service_filename = f"/etc/systemd/system/{unit_name}"
    client.write_to_file(service_filename, content)
    client.execute(f"chmod 0644 {service_filename}", use_sudo=True)
    client.execute(f"systemctl enable {unit_name}", use_sudo=True)


def network_wait_logged(log: str) -> bool:
    return (
        "Running command "
        "['systemctl', 'start', 'systemd-networkd-wait-online.service']"
    ) in log


def get_datetime_from_string(
    str, regex, datetime_strformat="%Y-%m-%d %H:%M:%S.%f%z"
):
    """
    Extract datetime from a given line in a string
    """
    matched = re.search(regex, str, re.M)
    assert matched, (
        f"Unable to find the datetime using the regex {regex}",
        f"inside the string {str}",
    )

    try:
        converted_datetime = datetime.strptime(
            matched.group(1), datetime_strformat
        )
    except ValueError:
        pytest.fail(
            " ".join(
                (
                    f"Unable to parse the datetime {matched.group(1)}",
                    f"using the format {datetime_strformat}",
                )
            )
        )
    return converted_datetime

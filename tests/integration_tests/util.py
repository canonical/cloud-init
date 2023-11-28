import logging
import multiprocessing
import os
import re
import time
from collections import namedtuple
from contextlib import contextmanager
from functools import lru_cache
from itertools import chain
from pathlib import Path
from typing import Set

import pytest

from cloudinit.subp import subp
from tests.integration_tests.instances import IntegrationInstance

log = logging.getLogger("integration_testing")
key_pair = namedtuple("key_pair", "public_key private_key")

ASSETS_DIR = Path("tests/integration_tests/assets")
KEY_PATH = ASSETS_DIR / "keys"


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
        warning_texts.append(
            "Falling back to a hard restart of systemd-networkd.service"
        )
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

    assert warning_count == expected_warnings, (
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
def wait_for_cloud_init(client: IntegrationInstance, num_retries: int = 30):
    last_exception = None
    for _ in range(num_retries):
        try:
            result = client.execute("cloud-init status")
            if (
                result
                and result.ok
                and ("running" not in result or "not run" not in result)
            ):
                return result
        except Exception as e:
            last_exception = e
        time.sleep(1)
    raise Exception(
        "cloud-init status did not return successfully."
    ) from last_exception


def get_console_log(client: IntegrationInstance):
    try:
        console_log = client.instance.console_log()
    except NotImplementedError:
        pytest.skip("NotImplementedError when requesting console log")
    if console_log.lower().startswith("no console output"):
        pytest.fail("no console output")
    return console_log


@lru_cache()
def lxd_has_nocloud(client: IntegrationInstance) -> bool:
    # Bionic or Focal may be detected as NoCloud rather than LXD
    lxd_image_metadata = subp(
        ["lxc", "config", "metadata", "show", client.instance.name]
    )
    return "/var/lib/cloud/seed/nocloud" in lxd_image_metadata.stdout


def get_feature_flag_value(client: IntegrationInstance, key):
    value = client.execute(
        'python3 -c "from cloudinit import features; '
        f'print(features.{key})"'
    ).strip()
    if "NameError" in value:
        raise NameError(f"name '{key}' is not defined")
    return value

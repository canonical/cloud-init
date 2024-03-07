# Copyright (C) 2016 Canonical Ltd.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Christian Ehrhardt <christian.ehrhardt@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""gpg.py - Collection of gpg key related functions"""

import logging
import os
import re
import signal
import time
from tempfile import TemporaryDirectory
from typing import Optional

from cloudinit import subp

LOG = logging.getLogger(__name__)

HOME = "GNUPGHOME"


class GPG:
    def __init__(self):
        self.temp_dir = None
        self.gpg_started = False
        self._env = {}

    def __enter__(self):
        self.temp_dir = None
        self.gpg_started = False
        self._env = {}
        return self

    @property
    def env(self):
        if self._env:
            return self._env
        self.temp_dir = TemporaryDirectory()
        self._env = {HOME: self.temp_dir.name}
        return self._env

    def __exit__(self, exc_typ, exc_value, traceback):
        self.kill_gpg()

    def export_armour(self, key) -> Optional[str]:
        """Export gpg key, armoured key gets returned"""
        try:
            self.gpg_started = True
            return subp.subp(
                ["gpg", "--export", "--armour", key],
                capture=True,
                update_env=self.env,
            ).stdout
        except subp.ProcessExecutionError as error:
            # debug, since it happens for any key not on the system initially
            LOG.debug('Failed to export armoured key "%s": %s', key, error)
        return None

    def dearmor(self, key) -> str:
        """Dearmor gpg key, dearmored key gets returned

        note: man gpg(1) makes no mention of an --armour spelling, only --armor
        """
        self.gpg_started = True
        return subp.subp(
            ["gpg", "--dearmor"], data=key, decode=False, update_env=self.env
        ).stdout

    def list_keys(self, key_file, human_output=False) -> str:
        """List keys from a keyring with fingerprints. Default to a
        stable machine parseable format.

        @param key_file: a string containing a filepath to a key
        @param human_output: return output intended for human parsing
        """
        self.gpg_started = True
        cmd = [
            "gpg",
            "--no-options",
            "--with-fingerprint",
            "--no-default-keyring",
            "--list-keys",
            "--keyring",
        ]
        if not human_output:
            cmd.append("--with-colons")

        cmd.append(key_file)
        stdout, stderr = subp.subp(cmd, update_env=self.env, capture=True)
        if stderr:
            LOG.warning(
                'Failed to export armoured key "%s": %s', key_file, stderr
            )
        return stdout

    def recv_key(self, key, keyserver, retries=(1, 1)) -> None:
        """Receive gpg key from the specified keyserver.

        Retries are done by default because keyservers can be unreliable.
        Additionally, there is no way to determine the difference between
        a non-existent key and a failure.  In both cases gpg (at least 2.2.4)
        exits with status 2 and stderr: "keyserver receive failed: No data"
        It is assumed that a key provided to cloud-init exists on the keyserver
        so re-trying makes better sense than failing.

        @param key: a string key fingerprint (as passed to gpg --recv-keys).
        @param keyserver: the keyserver to request keys from.
        @param retries: an iterable of sleep lengths for retries.
                        Use None to indicate no retries."""
        LOG.debug("Importing key '%s' from keyserver '%s'", key, keyserver)
        self.gpg_started = True
        trynum = 0
        error = None
        sleeps = iter(retries or [])
        while True:
            trynum += 1
            try:
                subp.subp(
                    [
                        "gpg",
                        "--no-tty",
                        "--keyserver=%s" % keyserver,
                        "--recv-keys",
                        key,
                    ],
                    capture=True,
                    update_env=self.env,
                )
                LOG.debug(
                    "Imported key '%s' from keyserver '%s' on try %d",
                    key,
                    keyserver,
                    trynum,
                )
                return
            except subp.ProcessExecutionError as e:
                error = e
            try:
                naplen = next(sleeps)
                LOG.debug(
                    "Import failed with exit code %d, will try again in %ss",
                    error.exit_code,
                    naplen,
                )
                time.sleep(naplen)
            except StopIteration as e:
                raise ValueError(
                    "Failed to import key '%s' from keyserver '%s' "
                    "after %d tries: %s" % (key, keyserver, trynum, error)
                ) from e

    def delete_key(self, key: str) -> None:
        """Delete the specified key from the local gpg ring"""
        try:
            self.gpg_started = True
            subp.subp(
                ["gpg", "--batch", "--yes", "--delete-keys", key],
                capture=True,
                update_env=self.env,
            )
        except subp.ProcessExecutionError as error:
            LOG.warning('Failed delete key "%s": %s', key, error)

    def getkeybyid(
        self, keyid: str, keyserver: str = "keyserver.ubuntu.com"
    ) -> Optional[str]:
        """get gpg keyid from keyserver"""
        armour = self.export_armour(keyid)
        if not armour:
            try:
                self.gpg_started = True
                self.recv_key(keyid, keyserver=keyserver)
                armour = self.export_armour(keyid)
            except ValueError:
                LOG.exception("Failed to obtain gpg key %s", keyid)
                raise
            finally:
                # delete just imported key to leave environment as it
                # was before
                self.delete_key(keyid)
        return armour

    def kill_gpg(self) -> None:
        """killing with gpgconf is best practice, but when it isn't available
        failover is possible

        GH: 4344 - stop gpg-agent/dirmgr daemons spawned by gpg
        key imports. Daemons spawned by cloud-config.service on systemd
        v253 report (running)
        """
        try:
            if not self.gpg_started:
                return
            if subp.which("gpgconf"):
                gpg_process_out = subp.subp(
                    ["gpgconf", "--kill", "all"],
                    capture=True,
                    update_env=self.env,
                ).stdout
            else:
                gpg_process_out = subp.subp(
                    [
                        "ps",
                        "-o",
                        "ppid,pid",
                        "-C",
                        "keyboxd",
                        "-C",
                        "dirmngr",
                        "-C",
                        "gpg-agent",
                    ],
                    capture=True,
                    rcs=[0, 1],
                ).stdout
                gpg_pids = re.findall(
                    r"(?P<ppid>\d+)\s+(?P<pid>\d+)", gpg_process_out
                )
                root_gpg_pids = [
                    int(pid[1]) for pid in gpg_pids if pid[0] == "1"
                ]
                if root_gpg_pids:
                    LOG.debug(
                        "Killing gpg-agent and dirmngr pids: %s", root_gpg_pids
                    )
                for gpg_pid in root_gpg_pids:
                    os.kill(gpg_pid, signal.SIGKILL)
        except subp.ProcessExecutionError as e:
            LOG.warning("Failed to clean up gpg process: %s", e)
        finally:
            if self.temp_dir:
                os.rmdir(self.temp_dir.name)

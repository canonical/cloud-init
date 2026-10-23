#!/usr/bin/python3
"""Exercise obsolete logrotate conffile cleanup with disposable dpkg roots."""

import hashlib
import os
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
OLD_PATH = Path("etc/logrotate.d/cloud-init")
NEW_PATH = Path("etc/logrotate.d/cloud-init-base")
ORIGINAL = b"/var/log/cloud-init*.log {\n    missingok\n    rotate 6\n}\n"
OLD_VERSION = "26.1-0ubuntu3~26.04.1"
FIXED_VERSION = "26.2-0ubuntu3"


class TestLogrotateConffile(unittest.TestCase):
    """Run real dpkg upgrades against disposable package databases."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)
        self.root = self.work / "root"
        (self.root / "var/lib/dpkg").mkdir(parents=True)
        self.old = self.root / OLD_PATH
        self.new = self.root / NEW_PATH
        # Match an already upgraded installation: cloud-init retains the old
        # obsolete conffile, while cloud-init-base owns the active new file.
        self.old.parent.mkdir(parents=True)
        self.old.write_bytes(ORIGINAL)
        self.new.write_bytes(ORIGINAL)
        digest = hashlib.md5(ORIGINAL, usedforsecurity=False).hexdigest()
        status = ""
        for package, path in (
            ("cloud-init", OLD_PATH),
            ("cloud-init-base", NEW_PATH),
        ):
            obsolete = " obsolete" if package == "cloud-init" else ""
            status += (
                f"Package: {package}\nStatus: install ok installed\n"
                f"Architecture: all\nVersion: {OLD_VERSION}\n"
                "Maintainer: Test <test@example.invalid>\n"
                "Description: disposable migration fixture\nConffiles:\n"
                f" /{path} {digest}{obsolete}\n\n"
            )
            info = self.root / "var/lib/dpkg/info"
            info.mkdir(exist_ok=True)
            (info / f"{package}.list").write_text(f"/{path}\n")
        self.status = self.root / "var/lib/dpkg/status"
        self.status.write_text(status)

    def command(self, *args):
        return subprocess.run(
            args, check=True, capture_output=True, text=True, timeout=20
        )

    def migration_lines(self):
        path = SOURCE / "cloud-init.maintscript"
        if not path.exists():
            return []
        return [
            shlex.split(line)
            for line in path.read_text().splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]

    def package(self, version):
        package = self.work / f"package-{version}"
        control = package / "DEBIAN"
        control.mkdir(parents=True)
        (control / "control").write_text(
            "Package: cloud-init\n"
            f"Version: {version}\nArchitecture: all\n"
            "Maintainer: Test <test@example.invalid>\n"
            "Description: disposable migration fixture\n"
        )
        # Exercise the real helper in the three maintainer-script phases.
        # Read the packaging declaration, not a duplicate migration rule.
        # This tests its behavior, not dh_installdeb's script generation.
        for script in ("preinst", "postinst", "postrm"):
            commands = ["#!/bin/sh", "set -e"]
            commands.extend(
                "dpkg-maintscript-helper " + shlex.join(line) + ' -- "$@"'
                for line in self.migration_lines()
            )
            target = control / script
            target.write_text("\n".join(commands) + "\n")
            target.chmod(0o755)
        archive = self.work / f"cloud-init_{version}_all.deb"
        self.command(
            "dpkg-deb",
            "--build",
            "--root-owner-group",
            str(package),
            str(archive),
        )
        return archive

    def upgrade(self, version=FIXED_VERSION):
        archive = self.package(version)
        return self.command(
            "dpkg",
            f"--root={self.root}",
            "--force-not-root",
            "--force-script-chrootless",
            "--install",
            str(archive),
        )

    def assert_active_config(self):
        self.assertFalse(
            self.old.exists(), "obsolete logrotate entry remains active"
        )
        self.assertEqual(ORIGINAL, self.new.read_bytes())

    def test_upgrade_removes_unmodified_obsolete_conffile(self):
        self.upgrade()
        self.assert_active_config()
        self.assertFalse(Path(str(self.old) + ".dpkg-bak").exists())

    def test_upgrade_preserves_modified_conffile_as_backup(self):
        modified = ORIGINAL + b"# administrator customization\n"
        self.old.write_bytes(modified)
        self.upgrade()
        self.assert_active_config()
        self.assertEqual(
            modified, Path(str(self.old) + ".dpkg-bak").read_bytes()
        )

    def test_upgrade_preserves_administrator_removal(self):
        self.old.unlink()
        self.upgrade()
        self.assert_active_config()
        self.assertFalse(Path(str(self.old) + ".dpkg-bak").exists())

    def test_upgrade_from_last_unfixed_packaging_version(self):
        self.status.write_text(
            self.status.read_text().replace(OLD_VERSION, "26.2-0ubuntu2")
        )
        self.upgrade()
        self.assert_active_config()

    def test_fresh_install_does_not_remove_an_unowned_file(self):
        self.status.write_text(self.status.read_text().split("\n\n", 1)[1])
        (self.root / "var/lib/dpkg/info/cloud-init.list").unlink()
        self.upgrade()
        self.assertEqual(ORIGINAL, self.old.read_bytes())
        self.assertEqual(ORIGINAL, self.new.read_bytes())

    def test_later_upgrade_does_not_remove_a_recreated_file(self):
        self.upgrade()
        self.assert_active_config()
        recreated = b"# file created after the migration\n"
        self.old.write_bytes(recreated)
        self.upgrade("26.2-0ubuntu4")
        self.assertEqual(recreated, self.old.read_bytes())
        self.assertEqual(ORIGINAL, self.new.read_bytes())

    def test_aborted_upgrade_restores_original_conffile(self):
        env = dict(
            os.environ,
            DPKG_ROOT=str(self.root),
            DPKG_ADMINDIR=str(self.root / "var/lib/dpkg"),
            DPKG_MAINTSCRIPT_PACKAGE="cloud-init",
        )
        for script, arguments in (
            ("preinst", ["upgrade", OLD_VERSION]),
            ("postrm", ["abort-upgrade", OLD_VERSION]),
        ):
            env["DPKG_MAINTSCRIPT_NAME"] = script
            for line in self.migration_lines():
                subprocess.run(
                    ["dpkg-maintscript-helper", *line, "--", *arguments],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=20,
                    env=env,
                )
            if script == "preinst":
                self.assertFalse(
                    self.old.exists(), "migration did not prepare removal"
                )
        self.assertEqual(ORIGINAL, self.old.read_bytes())
        self.assertEqual(ORIGINAL, self.new.read_bytes())


if __name__ == "__main__":
    unittest.main()

# This file is part of cloud-init. See LICENSE file for license information.

"""Tests for cloudinit.log """

import datetime
import io
import logging
import time

from cloudinit import log, util
from cloudinit.analyze.dump import CLOUD_INIT_ASCTIME_FMT
from tests.unittests.helpers import CiTestCase


class TestCloudInitLogger(CiTestCase):
    def setUp(self):
        # set up a logger like cloud-init does in setup_logging, but instead
        # of sys.stderr, we'll plug in a StringIO() object so we can see
        # what gets logged
        logging.Formatter.converter = time.gmtime
        self.ci_logs = io.StringIO()
        self.ci_root = logging.getLogger()
        console = logging.StreamHandler(self.ci_logs)
        console.setFormatter(logging.Formatter(log.DEFAULT_LOG_FORMAT))
        console.setLevel(logging.DEBUG)
        self.ci_root.addHandler(console)
        self.ci_root.setLevel(logging.DEBUG)
        self.LOG = logging.getLogger("test_cloudinit_logger")

    def test_logger_uses_gmtime(self):
        """Test that log message have timestamp in UTC (gmtime)"""

        # Log a message, extract the timestamp from the log entry
        # convert to datetime, and compare to a utc timestamp before
        # and after the logged message.

        # Due to loss of precision in the LOG timestamp, subtract and add
        # time to the utc stamps for comparison
        #
        # utc_before: 2017-08-23 14:19:42.569299
        # parsed dt : 2017-08-23 14:19:43.069000
        # utc_after : 2017-08-23 14:19:43.570064

        utc_before = datetime.datetime.utcnow() - datetime.timedelta(0, 0.5)
        self.LOG.error("Test message")
        utc_after = datetime.datetime.utcnow() + datetime.timedelta(0, 0.5)

        # extract timestamp from log:
        # 2017-08-23 14:19:43,069 - test_log.py[ERROR]: Test message
        logstr = self.ci_logs.getvalue().splitlines()[0]
        timestampstr = logstr.split(" - ")[0]
        parsed_dt = datetime.datetime.strptime(
            timestampstr, CLOUD_INIT_ASCTIME_FMT
        )

        self.assertLess(utc_before, parsed_dt)
        self.assertLess(parsed_dt, utc_after)
        self.assertLess(utc_before, utc_after)
        self.assertGreater(utc_after, parsed_dt)


class TestDeprecatedLogs:
    def test_deprecated_log_level(self, caplog):
        logger = logging.getLogger()
        log.setup_logging()
        logger.deprecated("deprecated message")
        assert "DEPRECATED" == caplog.records[0].levelname
        assert "deprecated message" in caplog.text

    def test_log_deduplication(self, caplog):
        log.define_deprecation_logger()
        util.deprecate(
            deprecated="stuff",
            deprecated_version="19.1",
            extra_message=":)",
        )
        util.deprecate(
            deprecated="stuff",
            deprecated_version="19.1",
            extra_message=":)",
        )
        util.deprecate(
            deprecated="stuff",
            deprecated_version="19.1",
            extra_message=":)",
            schedule=6,
        )
        assert 2 == len(caplog.records)

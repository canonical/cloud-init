# This file is part of cloud-init. See LICENSE file for license information.

"""Tests for cloudinit.log """

from cloudinit.analyze.dump import CLOUD_INIT_ASCTIME_FMT
from cloudinit import log as ci_logging
from cloudinit.tests.helpers import CiTestCase
import datetime
import logging
import six
import time


class TestCloudInitLogger(CiTestCase):

    def setUp(self):
        # set up a logger like cloud-init does in setupLogging, but instead
        # of sys.stderr, we'll plug in a StringIO() object so we can see
        # what gets logged
        logging.Formatter.converter = time.gmtime
        self.ci_logs = six.StringIO()
        self.ci_root = logging.getLogger()
        console = logging.StreamHandler(self.ci_logs)
        console.setFormatter(logging.Formatter(ci_logging.DEF_CON_FORMAT))
        console.setLevel(ci_logging.DEBUG)
        self.ci_root.addHandler(console)
        self.ci_root.setLevel(ci_logging.DEBUG)
        self.LOG = logging.getLogger('test_cloudinit_logger')

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
        self.LOG.error('Test message')
        utc_after = datetime.datetime.utcnow() + datetime.timedelta(0, 0.5)

        # extract timestamp from log:
        # 2017-08-23 14:19:43,069 - test_log.py[ERROR]: Test message
        logstr = self.ci_logs.getvalue().splitlines()[0]
        timestampstr = logstr.split(' - ')[0]
        parsed_dt = datetime.datetime.strptime(timestampstr,
                                               CLOUD_INIT_ASCTIME_FMT)

        self.assertLess(utc_before, parsed_dt)
        self.assertLess(parsed_dt, utc_after)
        self.assertLess(utc_before, utc_after)
        self.assertGreater(utc_after, parsed_dt)

# This file is part of cloud-init. See LICENSE file for license information.

import warnings
from contextlib import suppress
from datetime import datetime, timezone
from textwrap import dedent

import pytest

from cloudinit.analyze.dump import (
    dump_events,
    has_gnu_date,
    parse_ci_logline,
    parse_timestamp,
)
from cloudinit.util import write_file
from tests.unittests.helpers import mock


class TestParseTimestamp:
    def test_parse_timestamp_handles_cloud_init_default_format(self):
        """Logs with cloud-init detailed formats will be properly parsed."""
        trusty_fmt = "%Y-%m-%d %H:%M:%S,%f"
        trusty_stamp = "2016-09-12 14:39:20,839"
        dt = datetime.strptime(trusty_stamp, trusty_fmt).replace(
            tzinfo=timezone.utc
        )
        assert dt.timestamp() == parse_timestamp(trusty_stamp)

    def test_parse_timestamp_handles_syslog_adding_year(self):
        """Syslog timestamps lack a year. Add year and properly parse."""
        syslog_fmt = "%b %d %H:%M:%S %Y"
        syslog_stamp = "Aug 08 15:12:51"

        # convert stamp ourselves by adding the missing year value
        year = datetime.now().year
        dt = datetime.strptime(
            syslog_stamp + " " + str(year), syslog_fmt
        ).replace(tzinfo=timezone.utc)
        assert dt.timestamp() == parse_timestamp(syslog_stamp)

    def test_parse_timestamp_handles_journalctl_format_adding_year(self):
        """Journalctl precise timestamps lack a year. Add year and parse."""
        journal_fmt = "%b %d %H:%M:%S.%f %Y"
        journal_stamp = "Aug 08 17:15:50.606811"

        # convert stamp ourselves by adding the missing year value
        year = datetime.now().year
        dt = datetime.strptime(
            journal_stamp + " " + str(year), journal_fmt
        ).replace(tzinfo=timezone.utc)
        assert dt.timestamp() == parse_timestamp(journal_stamp)

    @pytest.mark.allow_subp_for("date", "gdate")
    def test_parse_unexpected_timestamp_format_with_date_command(self):
        """Dump sends unexpected timestamp formats to date for processing."""
        new_fmt = "%H:%M %m/%d %Y"
        new_stamp = "17:15 08/08"
        # convert stamp ourselves by adding the missing year value
        year = datetime.now().year
        dt = datetime.strptime(new_stamp + " " + str(year), new_fmt).replace(
            tzinfo=timezone.utc
        )

        if has_gnu_date():
            assert dt.timestamp() == parse_timestamp(new_stamp)
        else:
            with pytest.raises(ValueError):
                parse_timestamp(new_stamp)

    @pytest.mark.allow_subp_for("date", "gdate")
    def test_parse_timestamp_round_trip(self):
        """Ensure that timezone doesn't affect the returned timestamp.

        Depending on the format of the timestamp, we use different methods
        to parse it. In all cases, the timestamp should be returned the
        same, regardless of timezone.
        """
        times = [
            "Sep 12 14:39:00",
            "Sep 12 14:39:00.839452",
            "14:39 09/12",
            "2020-09-12 14:39:00,839",
            "2020-09-12 14:39:00.839452+00:00",
        ]

        timestamps = []
        for f in times:
            with suppress(ValueError):
                timestamps.append(parse_timestamp(f))

        new_times = [
            datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            for ts in timestamps
        ]
        assert all(t.endswith("-09-12 14:39:00") for t in new_times)

    @pytest.mark.allow_subp_for("date", "gdate")
    def test_parse_timestamp_handles_explicit_timezone(self):
        """Explicitly provided timezones are parsed and properly offset."""
        if not has_gnu_date():
            pytest.skip("GNU date is required for this test")

        original_ts = "2020-09-12 14:39:20.839452+02:00"
        parsed_ts = parse_timestamp(original_ts)
        assert (
            datetime.fromtimestamp(parsed_ts, tz=timezone.utc).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            == "2020-09-12 12:39:20"
        )


class TestParseCILogLine:
    def test_parse_logline_returns_none_without_separators(self):
        """When no separators are found, parse_ci_logline returns None."""
        expected_parse_ignores = [
            "",
            "-",
            "adsf-asdf",
            "2017-05-22 18:02:01,088",
            "CLOUDINIT",
        ]
        for parse_ignores in expected_parse_ignores:
            assert None is parse_ci_logline(parse_ignores)

    def test_parse_logline_returns_event_for_cloud_init_logs(self):
        """parse_ci_logline returns an event parse from cloud-init format."""
        line = (
            "2017-08-08 20:05:07,147 - util.py[DEBUG]: Cloud-init v. 0.7.9"
            " running 'init-local' at Tue, 08 Aug 2017 20:05:07 +0000. Up"
            " 6.26 seconds."
        )
        dt = datetime.strptime(
            "2017-08-08 20:05:07,147", "%Y-%m-%d %H:%M:%S,%f"
        ).replace(tzinfo=timezone.utc)
        timestamp = dt.timestamp()
        expected = {
            "description": "starting search for local datasources",
            "event_type": "start",
            "name": "init-local",
            "origin": "cloudinit",
            "timestamp": timestamp,
        }
        assert expected == parse_ci_logline(line)

    def test_parse_logline_returns_event_for_journalctl_logs(self):
        """parse_ci_logline returns an event parse from journalctl format."""
        line = (
            "Nov 03 06:51:06.074410 x2 cloud-init[106]: [CLOUDINIT]"
            " util.py[DEBUG]: Cloud-init v. 0.7.8 running 'init-local' at"
            "  Thu, 03 Nov 2016 06:51:06 +0000. Up 1.0 seconds."
        )
        year = datetime.now().year
        dt = datetime.strptime(
            "Nov 03 06:51:06.074410 %d" % year, "%b %d %H:%M:%S.%f %Y"
        ).replace(tzinfo=timezone.utc)
        timestamp = dt.timestamp()
        expected = {
            "description": "starting search for local datasources",
            "event_type": "start",
            "name": "init-local",
            "origin": "cloudinit",
            "timestamp": timestamp,
        }
        assert expected == parse_ci_logline(line)

    @mock.patch("cloudinit.analyze.dump.parse_timestamp_from_date")
    def test_parse_logline_returns_event_for_finish_events(
        self, m_parse_from_date
    ):
        """parse_ci_logline returns a finish event for a parsed log line."""
        line = (
            "2016-08-30 21:53:25.972325+00:00 y1 [CLOUDINIT]"
            " handlers.py[DEBUG]: finish: modules-final: SUCCESS: running"
            " modules for final"
        )
        expected = {
            "description": "running modules for final",
            "event_type": "finish",
            "name": "modules-final",
            "origin": "cloudinit",
            "result": "SUCCESS",
            "timestamp": 1472594005.972,
        }
        m_parse_from_date.return_value = "1472594005.972"
        assert expected == parse_ci_logline(line)
        m_parse_from_date.assert_has_calls(
            [mock.call("2016-08-30 21:53:25.972325+00:00")]
        )

    def test_parse_logline_returns_event_for_amazon_linux_2_line(self):
        line = (
            "Apr 30 19:39:11 cloud-init[2673]: handlers.py[DEBUG]: start:"
            " init-local/check-cache: attempting to read from cache [check]"
        )

        # Python deprecated parsing dates without a year due to ambiguous
        # leap year behavior. Parsing dates without leap years is something
        # that cloud-init analyze attempts to support.
        #
        # This test will start to fail in a future version of Python if
        # the deprecated behavior changes in a breaking way.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=DeprecationWarning)
            # Generate the expected value using `datetime`, so that TZ
            # determination is consistent with the code under test.
            date = datetime.strptime("Apr 30 19:39:11", "%b %d %H:%M:%S")

        timestamp_dt = date.replace(year=datetime.now().year).replace(
            tzinfo=timezone.utc
        )
        expected = {
            "description": "attempting to read from cache [check]",
            "event_type": "start",
            "name": "init-local/check-cache",
            "origin": "cloudinit",
            "timestamp": timestamp_dt.timestamp(),
        }
        assert expected == parse_ci_logline(line)


SAMPLE_LOGS = dedent(
    """\
Nov 03 06:51:06.074410 x2 cloud-init[106]: [CLOUDINIT] util.py[DEBUG]:\
 Cloud-init v. 0.7.8 running 'init-local' at Thu, 03 Nov 2016\
 06:51:06 +0000. Up 1.0 seconds.
2016-08-30 21:53:25.972325+00:00 y1 [CLOUDINIT] handlers.py[DEBUG]: finish:\
 modules-final: SUCCESS: running modules for final
"""
)


class TestDumpEvents:
    maxDiff = None

    @mock.patch("cloudinit.analyze.dump.parse_timestamp_from_date")
    def test_dump_events_with_rawdata(self, m_parse_from_date):
        """Rawdata is split and parsed into a tuple of events and data"""
        m_parse_from_date.return_value = "1472594005.972"
        events, data = dump_events(rawdata=SAMPLE_LOGS)
        expected_data = SAMPLE_LOGS.splitlines()
        assert [
            mock.call("2016-08-30 21:53:25.972325+00:00")
        ] == m_parse_from_date.call_args_list
        assert expected_data == data
        year = datetime.now().year
        dt1 = datetime.strptime(
            "Nov 03 06:51:06.074410 %d" % year, "%b %d %H:%M:%S.%f %Y"
        ).replace(tzinfo=timezone.utc)
        timestamp1 = dt1.timestamp()
        expected_events = [
            {
                "description": "starting search for local datasources",
                "event_type": "start",
                "name": "init-local",
                "origin": "cloudinit",
                "timestamp": timestamp1,
            },
            {
                "description": "running modules for final",
                "event_type": "finish",
                "name": "modules-final",
                "origin": "cloudinit",
                "result": "SUCCESS",
                "timestamp": 1472594005.972,
            },
        ]
        assert expected_events == events

    @mock.patch("cloudinit.analyze.dump.parse_timestamp_from_date")
    def test_dump_events_with_cisource(self, m_parse_from_date, tmpdir):
        """Cisource file is read and parsed into a tuple of events and data."""
        tmpfile = str(tmpdir.join(("logfile")))
        write_file(tmpfile, SAMPLE_LOGS)
        m_parse_from_date.return_value = 1472594005.972
        with open(tmpfile) as file:
            events, data = dump_events(cisource=file)
        year = datetime.now().year
        dt1 = datetime.strptime(
            "Nov 03 06:51:06.074410 %d" % year, "%b %d %H:%M:%S.%f %Y"
        ).replace(tzinfo=timezone.utc)
        timestamp1 = dt1.timestamp()
        expected_events = [
            {
                "description": "starting search for local datasources",
                "event_type": "start",
                "name": "init-local",
                "origin": "cloudinit",
                "timestamp": timestamp1,
            },
            {
                "description": "running modules for final",
                "event_type": "finish",
                "name": "modules-final",
                "origin": "cloudinit",
                "result": "SUCCESS",
                "timestamp": 1472594005.972,
            },
        ]
        assert expected_events == events
        assert SAMPLE_LOGS.splitlines() == [d.strip() for d in data]
        m_parse_from_date.assert_has_calls(
            [mock.call("2016-08-30 21:53:25.972325+00:00")]
        )

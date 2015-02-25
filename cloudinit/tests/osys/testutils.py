# Copyright (C) 2015 Canonical Ltd.
# Copyright 2015 Cloudbase Solutions Srl
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import logging

__all__ = (
    'LogSnatcher',
)

# This is similar with unittest.TestCase.assertLogs from Python 3.4.
class SnatchHandler(logging.Handler):
    def __init__(self, *args, **kwargs):
        super(SnatchHandler, self).__init__(*args, **kwargs)
        self.output = []

    def emit(self, record):
        msg = self.format(record)
        self.output.append(msg)


class LogSnatcher(object):
    """A context manager to capture emitted logged messages.

    The class can be used as following::

        with LogSnatcher('plugins.windows.createuser') as snatcher:
            LOG.info("doing stuff")
            LOG.info("doing stuff %s", 1)
            LOG.warn("doing other stuff")
            ...
        self.assertEqual(snatcher.output,
                         ['INFO:unknown:doing stuff',
                          'INFO:unknown:doing stuff 1',
                          'WARN:unknown:doing other stuff'])
    """

    @property
    def output(self):
        return self._snatch_handler.output

    def __init__(self, logger_name):
        self._logger_name = logger_name
        self._snatch_handler = SnatchHandler()
        self._logger = logging.getLogger(self._logger_name)
        self._previous_level = self._logger.logger.getEffectiveLevel()

    def __enter__(self):
        self._logger.logger.setLevel(logging.DEBUG)
        self._logger.handlers.append(self._snatch_handler)
        return self

    def __exit__(self, *args):
        self._logger.handlers.remove(self._snatch_handler)
        self._logger.logger.setLevel(self._previous_level)

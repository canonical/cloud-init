# vi: ts=4 expandtab
#
#    Copyright (C) 2015 Canonical Ltd.
#    Copyright (C) 2015 VMware Inc.
#
#    Author: Sankar Tanguturi <stanguturi@vmware.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License version 3, as
#    published by the Free Software Foundation.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging

try:
    import configparser
except ImportError:
    import ConfigParser as configparser

from .config_source import ConfigSource

logger = logging.getLogger(__name__)


class ConfigFile(ConfigSource, dict):
    """ConfigFile module to load the content from a specified source."""

    def __init__(self):
        pass

    def _insertKey(self, key, val):
        """
        Inserts a Key Value pair.

        Keyword arguments:
        key -- The key to insert
        val -- The value to insert for the key

        """
        key = key.strip()
        val = val.strip()

        if key.startswith('-') or '|-' in key:
            canLog = 0
        else:
            canLog = 1

        # "sensitive" settings shall not be logged
        if canLog:
            logger.debug("ADDED KEY-VAL :: '%s' = '%s'" % (key, val))
        else:
            logger.debug("ADDED KEY-VAL :: '%s' = '*****************'" % key)

        self[key] = val

    def size(self):
        """Return the number of properties present."""
        return len(self)

    def loadConfigFile(self, filename):
        """
        Parses properties from the specified config file.

        Any previously available properties will be removed.
        Sensitive data will not be logged in case the key starts
        from '-'.

        Keyword arguments:
        filename - The full path to the config file.
        """
        logger.info('Parsing the config file %s.' % filename)

        config = configparser.ConfigParser()
        config.optionxform = str
        config.read(filename)

        self.clear()

        for category in config.sections():
            logger.debug("FOUND CATEGORY = '%s'" % category)

            for (key, value) in config.items(category):
                # "sensitive" settings shall not be logged
                if key.startswith('-'):
                    canLog = 0
                else:
                    canLog = 1

                if canLog:
                    logger.debug("Processing key, value: '%s':'%s'" %
                                 (key, value))
                else:
                    logger.debug("Processing key, value : "
                                 "'*********************'")

                self._insertKey(category + '|' + key, value)

    def keep_current_value(self, key):
        """
        Determines whether a value for a property must be kept.

        If the propery is missing, it is treated as it should be not
        changed by the engine.

        Keyword arguments:
        key -- The key to search for.
        """
        # helps to distinguish from "empty" value which is used to indicate
        # "removal"
        return not key in self

    def remove_current_value(self, key):
        """
        Determines whether a value for the property must be removed.

        If the specified key is empty, it is treated as it should be
        removed by the engine.

        Return true if the value can be removed, false otherwise.

        Keyword arguments:
        key -- The key to search for.
        """
        # helps to distinguish from "missing" value which is used to indicate
        # "keeping unchanged"
        if key in self:
            return not bool(self[key])
        else:
            return False

    def get_count(self, prefix):
        """
        Return the total number of keys that start with the
        specified prefix.

        Keyword arguments:
        prefix -- prefix of the key
        """
        res = 0
        for key in self.keys():
            if key.startswith(prefix):
                res += 1

        return res

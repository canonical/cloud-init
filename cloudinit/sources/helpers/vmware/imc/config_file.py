# Copyright (C) 2015 Canonical Ltd.
# Copyright (C) 2015 VMware Inc.
#
# Author: Sankar Tanguturi <stanguturi@vmware.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import configparser
import logging

from cloudinit.sources.helpers.vmware.imc.config_source import ConfigSource

logger = logging.getLogger(__name__)


class ConfigFile(ConfigSource, dict):
    """ConfigFile module to load the content from a specified source."""

    def __init__(self, filename):
        self._loadConfigFile(filename)

    def _insertKey(self, key, val):
        """
        Inserts a Key Value pair.

        Keyword arguments:
        key -- The key to insert
        val -- The value to insert for the key

        """
        key = key.strip()
        val = val.strip()

        if key.startswith("-") or "|-" in key:
            canLog = False
        else:
            canLog = True

        # "sensitive" settings shall not be logged
        if canLog:
            logger.debug("ADDED KEY-VAL :: '%s' = '%s'", key, val)
        else:
            logger.debug("ADDED KEY-VAL :: '%s' = '*****************'", key)

        self[key] = val

    def _loadConfigFile(self, filename):
        """
        Parses properties from the specified config file.

        Any previously available properties will be removed.
        Sensitive data will not be logged in case the key starts
        from '-'.

        Keyword arguments:
        filename - The full path to the config file.
        """
        logger.info("Parsing the config file %s.", filename)

        config = configparser.ConfigParser()
        config.optionxform = str
        config.read(filename)

        self.clear()

        for category in config.sections():
            logger.debug("FOUND CATEGORY = '%s'", category)

            for key, value in config.items(category):
                self._insertKey(category + "|" + key, value)

    def get_count_with_prefix(self, prefix):
        """
        Return the total count of keys that start with the specified prefix.

        Keyword arguments:
        prefix -- prefix of the key
        """
        return len([key for key in self if key.startswith(prefix)])

import logging
import re

from cloudinit.sources.helpers.vmware.imc.config_source import ConfigSource

logger = logging.getLogger(__name__)


class ConfigFile(ConfigSource):
    def __init__(self):
        self._configData = {}

    def __getitem__(self, key):
        return self._configData[key]

    def get(self, key, default=None):
        return self._configData.get(key, default)

    # Removes all the properties.
    #
    # Args:
    #   None
    # Results:
    #   None
    # Throws:
    #   None
    def clear(self):
        self._configData.clear()

    # Inserts k/v pair.
    #
    # Does not do any key/cross-key validation.
    #
    # Args:
    #   key: string: key
    #   val: string: value
    # Results:
    #   None
    # Throws:
    #   None
    def _insertKey(self, key, val):
        # cleaning up on all "input" path

        # remove end char \n (chomp)
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

        self._configData[key] = val

    # Determines properties count.
    #
    # Args:
    #   None
    # Results:
    #   integer: properties count
    # Throws:
    #   None
    def size(self):
        return len(self._configData)

    # Parses properties from a .cfg file content.
    #
    # Any previously available properties will be removed.
    #
    # Sensitive data will not be logged in case key starts from '-'.
    #
    # Args:
    #   content: string: e.g. content of config/cust.cfg
    # Results:
    #   None
    # Throws:
    #   None
    def loadConfigContent(self, content):
        self.clear()

        # remove end char \n (chomp)
        for line in content.split('\n'):
            # TODO validate against allowed characters (not done in Perl)

            # spaces at the end are not allowed, things like passwords must be
            # at least base64-encoded
            line = line.strip()

            # "sensitive" settings shall not be logged
            if line.startswith('-'):
                canLog = 0
            else:
                canLog = 1

            if canLog:
                logger.debug("Processing line: '%s'" % line)
            else:
                logger.debug("Processing line: '***********************'")

            if not line:
                logger.debug("Empty line. Ignored.")
                continue

            if line.startswith('#'):
                logger.debug("Comment found. Line ignored.")
                continue

            matchObj = re.match(r'\[(.+)\]', line)
            if matchObj:
                category = matchObj.group(1)
                logger.debug("FOUND CATEGORY = '%s'" % category)
            else:
                # POSIX.2 regex doesn't support non-greedy like in (.+?)=(.*)
                # key value pair (non-eager '=' for base64)
                matchObj = re.match(r'([^=]+)=(.*)', line)
                if matchObj:
                    # cleaning up on all "input" paths
                    key = category + "|" + matchObj.group(1).strip()
                    val = matchObj.group(2).strip()

                    self._insertKey(key, val)
                else:
                    # TODO document
                    raise Exception("Unrecognizable line: '%s'" % line)

        self.validate()

    # Parses properties from a .cfg file
    #
    # Any previously available properties will be removed.
    #
    # Sensitive data will not be logged in case key starts from '-'.
    #
    # Args:
    #   filename: string: full path to a .cfg file
    # Results:
    #   None
    # Throws:
    #   None
    def loadConfigFile(self, filename):
        logger.info("Opening file name %s." % filename)
        # TODO what throws?
        with open(filename, "r") as myfile:
            self.loadConfigContent(myfile.read())

    # Determines whether a property with a given key exists.
    #
    # Args:
    #   key: string: key
    # Results:
    #   boolean: True if such property exists, otherwise - False.
    # Throws:
    #   None
    def hasKey(self, key):
        return key in self._configData

    # Determines whether a value for a property must be kept.
    #
    # If the property is missing, it's treated as it should be not changed by
    # the engine.
    #
    # Args:
    #   key: string: key
    # Results:
    #   boolean: True if property must be kept, otherwise - False.
    # Throws:
    #   None
    def keepCurrentValue(self, key):
        # helps to distinguish from "empty" value which is used to indicate
        # "removal"
        return not self.hasKey(key)

    # Determines whether a value for a property must be removed.
    #
    # If the property is empty, it's treated as it should be removed by the
    # engine.
    #
    # Args:
    #   key: string: key
    # Results:
    #   boolean: True if property must be removed, otherwise - False.
    # Throws:
    #   None
    def removeCurrentValue(self, key):
        # helps to distinguish from "missing" value which is used to indicate
        # "keeping unchanged"
        if self.hasKey(key):
            return not bool(self._configData[key])
        else:
            return False

    # TODO
    def getCnt(self, prefix):
        res = 0
        for key in self._configData.keys():
            if key.startswith(prefix):
                res += 1

        return res

    # TODO
    # TODO pass base64
    # Throws:
    #   Dies in case timezone is present but empty.
    #   Dies in case password is present but empty.
    #   Dies in case hostname is present but empty or greater than 63 chars.
    #   Dies in case UTC is present, but is not yes/YES or no/NO.
    #   Dies in case NICS is not present.
    def validate(self):
        # TODO must log all the errors
        keyValidators = {'NIC1|IPv6GATEWAY|': None}
        crossValidators = {}

        for key in self._configData.keys():
            pass

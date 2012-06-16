# vi: ts=4 expandtab
#
#    Copyright (C) 2012 Yahoo! Inc.
#
#    Author: Joshua Harlow <harlowja@yahoo-inc.com>
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

import io

from ConfigParser import (NoSectionError, NoOptionError, RawConfigParser)

# This config parser will not throw when sections don't exist
# and you are setting values on those sections which is useful
# when writing to new options that may not have corresponding
# sections. Also it can default other values when doing gets
# so that if those sections/options do not exist you will
# get a default instead of an error. Another useful case where
# you can avoid catching exceptions that you typically don't
# care about...

class DefaultingConfigParser(RawConfigParser):
    DEF_INT = 0
    DEF_FLOAT = 0.0
    DEF_BOOLEAN = False
    DEF_BASE = None

    def get(self, section, option):
        value = self.DEF_BASE
        try:
            value = RawConfigParser.get(self, section, option)
        except NoSectionError:
            pass
        except NoOptionError:
            pass
        return value

    def set(self, section, option, value):
        if not self.has_section(section) and section.lower() != 'default':
            self.add_section(section)
        RawConfigParser.set(self, section, option, value)

    def remove_option(self, section, option):
        if self.has_option(section, option):
            RawConfigParser.remove_option(self, section, option)

    def getboolean(self, section, option):
        if not self.has_option(section, option):
            return self.DEF_BOOLEAN
        return RawConfigParser.getboolean(self, section, option)

    def getfloat(self, section, option):
        if not self.has_option(section, option):
            return self.DEF_FLOAT
        return RawConfigParser.getfloat(self, section, option)

    def getint(self, section, option):
        if not self.has_option(section, option):
            return self.DEF_INT
        return RawConfigParser.getint(self, section, option)

    def stringify(self, header=None):
        contents = ''
        with io.BytesIO() as outputstream:
            self.write(outputstream)
            outputstream.flush()
            contents = outputstream.getvalue()
            if header:
                contents = "\n".join([header, contents])
        return contents

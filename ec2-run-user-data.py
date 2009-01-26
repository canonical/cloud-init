#!/usr/bin/python
#
#    Fetch and run user-data from EC2
#    Copyright 2008 Canonical Ltd.
#
#    Original-Author: Soren Hansen <soren@canonical.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import os
import sys
import tempfile
import urllib
from time import gmtime, strftime

api_ver = '2008-02-01'
metadata = None

def get_user_data():
    url = 'http://169.254.169.254/%s/user-data' % api_ver
    fp = urllib.urlopen(url)
    data = fp.read()
    fp.close()
    return data

def get_ami_id():
    url = 'http://169.254.169.254/%s/meta-data', % api_ver
    ami_id = urllib.urlopen('%s/ami-id/' %url).read()
    return ami_id

user_data = get_user_data()
amiId = get_ami_id()

if user_data.startswith('#!'):
    # run it 
    (fp, path) = tempfile.mkstemp()
    os.write(fp,user_data)
    os.close(fp);
    os.chmod(path, 0700)
    os.system('cp %s /var/ec2/user-data.%s' %(path, amiId))
    status = os.system('%s' % path)
    os.unlink(path)

sys.exit(0)

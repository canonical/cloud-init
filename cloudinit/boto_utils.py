# The contents of this file are taken from boto 1.9b's boto/utils.py
#
# Copyright (c) 2006,2007 Mitch Garnaat http://garnaat.org/
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish, dis-
# tribute, sublicense, and/or sell copies of the Software, and to permit
# persons to whom the Software is furnished to do so, subject to the fol-
# lowing conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
# OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABIL-
# ITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT
# SHALL THE AUTHOR BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, 
# WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.

#
# Parts of this code were copied or derived from sample code supplied by AWS.
# The following notice applies to that code.
#
#  This software code is made available "AS IS" without warranties of any
#  kind.  You may copy, display, modify and redistribute the software
#  code either by itself or as incorporated into your code; provided that
#  you do not remove any proprietary notices.  Your use of this software
#  code is at your own risk and you waive any claim against Amazon
#  Digital Services, Inc. or its affiliates with respect to your use of
#  this software code. (c) 2006 Amazon Digital Services, Inc. or its
#  affiliates.
import urllib2
import sys
import time

def retry_url(url, retry_on_404=True):
    for i in range(0, 10):
        try:
            req = urllib2.Request(url)
            resp = urllib2.urlopen(req)
            return resp.read()
        except urllib2.HTTPError, e:
            # in 2.6 you use getcode(), in 2.5 and earlier you use code
            if hasattr(e, 'getcode'):
                code = e.getcode()
            else:
                code = e.code
            if code == 404 and not retry_on_404:
                return ''
        except:
            pass
        #boto.log.exception('Caught exception reading instance data')
        sys.stderr.write('Caught exception reading instance data: %s\n' % url)
        time.sleep(2**i)
    #boto.log.error('Unable to read instance data, giving up')
    sys.stderr.write('Caught exception reading instance data, giving up\n')
    return ''

def get_instance_metadata(version='latest'):
    """
    Returns the instance metadata as a nested Python dictionary.
    Simple values (e.g. local_hostname, hostname, etc.) will be
    stored as string values.  Values such as ancestor-ami-ids will
    be stored in the dict as a list of string values.  More complex
    fields such as public-keys and will be stored as nested dicts.
    """
    url = 'http://169.254.169.254/%s/meta-data/' % version
    return _get_instance_metadata(url)

def get_instance_userdata(version='latest', sep=None):
    url = 'http://169.254.169.254/%s/user-data' % version
    user_data = retry_url(url, retry_on_404=False)
    if user_data:
        if sep:
            l = user_data.split(sep)
            user_data = {}
            for nvpair in l:
                t = nvpair.split('=')
                user_data[t[0].strip()] = t[1].strip()
    return user_data


def _get_instance_metadata(url):
    d = {}
    data = retry_url(url)
    if data:
        fields = data.split('\n')
        for field in fields:
            if field.endswith('/'):
                d[field[0:-1]] = _get_instance_metadata(url + field)
            else:
                p = field.find('=')
                if p > 0:
                    key = field[p+1:]
                    resource = field[0:p] + '/openssh-key'
                else:
                    key = resource = field
                val = retry_url(url + resource)
                p = val.find('\n')
                if p > 0:
                    val = val.split('\n')
                d[key] = val
    return d

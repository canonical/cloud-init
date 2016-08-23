# vi: ts=4 expandtab
#
#    Copyright (C) 2009-2010 Canonical Ltd.
#
#    Author: Scott Moser <scott.moser@canonical.com>
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

import DataSource

from cloudinit import seeddir, log  # pylint: disable=W0611
import cloudinit.util as util
import socket
import urllib2
import time
import boto.utils as boto_utils
import os.path

class DataSourceEc2(DataSource.DataSource):
    api_ver  = '2009-04-04'
    seeddir = seeddir + '/ec2'
    metadata_address = "http://169.254.169.254"

    def __str__(self):
        return("DataSourceEc2")

    def get_data(self):
        seedret={ }
        if util.read_optional_seed(seedret,base=self.seeddir+ "/"):
            self.userdata_raw = seedret['user-data']
            self.metadata = seedret['meta-data']
            log.debug("using seeded ec2 data in %s" % self.seeddir)
            return True
        
        try:
            if not self.wait_for_metadata_service():
                return False
            start = time.time()
            self.userdata_raw = boto_utils.get_instance_userdata(self.api_ver, None, self.metadata_address)
            self.metadata = boto_utils.get_instance_metadata(self.api_ver, self.metadata_address)
            log.debug("crawl of metadata service took %ds" % (time.time()-start))
            return True
        except Exception as e:
            print e
            return False

    def get_instance_id(self):
        return(self.metadata['instance-id'])

    def get_availability_zone(self):
        return(self.metadata['placement']['availability-zone'])

    def get_local_mirror(self):
        return(self.get_mirror_from_availability_zone())

    def get_mirror_from_availability_zone(self, availability_zone = None):
        # availability is like 'us-west-1b' or 'eu-west-1a'
        if availability_zone == None:
            availability_zone = self.get_availability_zone()

        fallback = None

        if self.is_vpc():
            return fallback

        try:
            host="%s.ec2.archive.ubuntu.com" % availability_zone[:-1]
            socket.getaddrinfo(host, None, 0, socket.SOCK_STREAM)
            return 'http://%s/ubuntu/' % host
        except:
            return fallback

    def wait_for_metadata_service(self):
        mcfg = self.ds_cfg

        if not hasattr(mcfg, "get"):
            mcfg =  {}

        max_wait = 120
        try:
            max_wait = int(mcfg.get("max_wait",max_wait))
        except Exception:
            util.logexc(log)
            log.warn("Failed to get max wait. using %s" % max_wait)

        if max_wait == 0:
            return False

        timeout = 50
        try:
            timeout = int(mcfg.get("timeout",timeout))
        except Exception:
            util.logexc(log)
            log.warn("Failed to get timeout, using %s" % timeout)

        def_mdurls = ["http://169.254.169.254", "http://instance-data:8773"]
        mdurls = mcfg.get("metadata_urls", def_mdurls)

        # Remove addresses from the list that wont resolve.
        filtered = [x for x in mdurls if util.is_resolvable_url(x)]

        if set(filtered) != set(mdurls):
            log.debug("removed the following from metadata urls: %s" %
                list((set(mdurls) - set(filtered))))

        if len(filtered):
            mdurls = filtered
        else:
            log.warn("Empty metadata url list! using default list")
            mdurls = def_mdurls

        urls = [ ]
        url2base = { False: False }
        for url in mdurls:
            cur = "%s/%s/meta-data/instance-id" % (url, self.api_ver)
            urls.append(cur)
            url2base[cur] = url

        starttime = time.time()
        url = wait_for_metadata_service(urls=urls, max_wait=max_wait,
                  timeout=timeout, status_cb=log.warn)

        if url:
            log.debug("Using metadata source: '%s'" % url2base[url])
        else:
            log.critical("giving up on md after %i seconds\n" %
                         int(time.time()-starttime))

        self.metadata_address = url2base[url]
        return (bool(url))

    def device_name_to_device(self, name):
        # consult metadata service, that has
        #  ephemeral0: sdb
        # and return 'sdb' for input 'ephemeral0'
        if not self.metadata.has_key('block-device-mapping'):
            return(None)

        found = None
        for entname, device in self.metadata['block-device-mapping'].items():
            if entname == name:
                found = device
                break
            # LP: #513842 mapping in Euca has 'ephemeral' not 'ephemeral0'
            if entname == "ephemeral" and name == "ephemeral0":
                found = device
        if found == None:
            log.debug("unable to convert %s to a device" % name)
            return None

        # LP: #611137
        # the metadata service may believe that devices are named 'sda'
        # when the kernel named them 'vda' or 'xvda'
        # we want to return the correct value for what will actually
        # exist in this instance
        mappings = { "sd": ("vd", "xvd") }
        ofound = found
        short = os.path.basename(found)
        
        if not found.startswith("/"):
            found="/dev/%s" % found

        if os.path.exists(found):
            return(found)

        for nfrom, tlist in mappings.items():
            if not short.startswith(nfrom): continue
            for nto in tlist:
                cand = "/dev/%s%s" % (nto, short[len(nfrom):])
                if os.path.exists(cand):
                    log.debug("remapped device name %s => %s" % (found,cand))
                    return(cand)

        # on t1.micro, ephemeral0 will appear in block-device-mapping from
        # metadata, but it will not exist on disk (and never will)
        # at this pint, we've verified that the path did not exist
        # in the special case of 'ephemeral0' return None to avoid bogus
        # fstab entry (LP: #744019)
        if name == "ephemeral0":
            return None
        return ofound

    def is_vpc(self):
        # per comment in LP: #615545
        ph="public-hostname"; p4="public-ipv4"
        if ((ph not in self.metadata or self.metadata[ph] == "") and
            (p4 not in self.metadata or self.metadata[p4] == "")):
            return True
        return False


def wait_for_metadata_service(urls, max_wait=None, timeout=None, status_cb=None):
    """
    urls:      a list of urls to try
    max_wait:  roughly the maximum time to wait before giving up
               The max time is *actually* len(urls)*timeout as each url will
               be tried once and given the timeout provided.
    timeout:   the timeout provided to urllib2.urlopen
    status_cb: call method with string message when a url is not available
      
    the idea of this routine is to wait for the EC2 metdata service to
    come up.  On both Eucalyptus and EC2 we have seen the case where
    the instance hit the MD before the MD service was up.  EC2 seems
    to have permenantely fixed this, though.

    In openstack, the metadata service might be painfully slow, and
    unable to avoid hitting a timeout of even up to 10 seconds or more
    (LP: #894279) for a simple GET.

    Offset those needs with the need to not hang forever (and block boot)
    on a system where cloud-init is configured to look for EC2 Metadata
    service but is not going to find one.  It is possible that the instance
    data host (169.254.169.254) may be firewalled off Entirely for a sytem,
    meaning that the connection will block forever unless a timeout is set.
    """
    starttime = time.time()

    sleeptime = 1

    if status_cb == None:
        def status_cb(msg): return

    def timeup(max_wait, starttime):
        return((max_wait <= 0 or max_wait == None) or
               (time.time()-starttime > max_wait))

    loop_n = 0
    while True:
        sleeptime=int(loop_n/5)+1
        for url in urls:
            now = time.time()
            if loop_n != 0:
                if timeup(max_wait, starttime):
                    break
                if timeout and (now + timeout > (starttime + max_wait)):
                    # shorten timeout to not run way over max_time
                    timeout = int((starttime + max_wait) - now)

            reason = ""
            try:
                req = urllib2.Request(url)
                resp = urllib2.urlopen(req, timeout=timeout)
                if resp.read() != "":
                    return url
                reason = "empty data [%s]" % resp.getcode()
            except urllib2.HTTPError as e:
                reason = "http error [%s]" % e.code
            except urllib2.URLError as e:
                reason = "url error [%s]" % e.reason
            except socket.timeout as e:
                reason = "socket timeout [%s]" % e
            except Exception as e:
                reason = "unexpected error [%s]" % e

            if log:
                status_cb("'%s' failed [%s/%ss]: %s" %
                          (url, int(time.time()-starttime), max_wait, reason))

        if timeup(max_wait, starttime):
            break

        loop_n = loop_n + 1
        time.sleep(sleeptime)

    return False


datasources = [ 
  ( DataSourceEc2, ( DataSource.DEP_FILESYSTEM , DataSource.DEP_NETWORK ) ),
]

# return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return(DataSource.list_from_depends(depends, datasources))

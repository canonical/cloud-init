#!/usr/bin/python
#
#    Fetch the information about an AMI instance.
#    Copyright (C) 2008-2009 Canonical Ltd.
#
#    Author: Chuck Short <chuck.short@canonical.com>
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
#

from  optparse import OptionParser
import urllib

ec2Data = ['ami-id',
           'ami-launch-index',
           'ami-manifest-path',
           'ancestor-ami-id',
           'block-device-mapping',
           'instance-id',
           'instance-type',
           'local-hostname',
           'local-ipv4',
           'kernel-id',
           'product-codes',
           'public-hostname',
           'public-ipv4',
           'ramdisk-id',
           'reservation-id',
           'security-groups']

def ec2Version():
    print file("/etc/ec2_version").read()

def getData(ec2data):
    api_ver = '2008-02-01'
    base_url = 'http://169.254.169.254/%s/meta-data' % api_ver
    print "%s: %s" %(ec2data,urllib.urlopen('%s/%s' %(base_url,ec2data)).read())

def getAllData(ec2Data):
    for x in ec2Data:
        getData(x)

def main():
    usage = "usage: %prog [options]"

    parser = OptionParser(prog='ec2-get-info', usage=usage)
    parser.add_option('--ami-id', dest='amiid', action='store_true', help='Display the ami-id.')
    parser.add_option('--launch-index', dest='launch', action='store_true', help='Display the AMI launch index.')
    parser.add_option('--manifest', dest='manifest', action='store_true', help='Display the AMI manifest path.')
    parser.add_option('--ancestor-id', dest='ancestor', action='store_true', help='Display the AMI ancestor id.')
    parser.add_option('--block-device', dest='block', action='store_true', help='Display the block device id.')
    parser.add_option('--instance-id', dest='id', action='store_true', help='Display the instance id.')
    parser.add_option('--instance-type', dest='type', action='store_true', help='Display the instance type.')
        parser.add_option('--local-hostname', dest='lhostname', action='store_true', help='Display the local hostname.')
    parser.add_option('--local-ipv4', dest='lipv4', action='store_true', help='Display the local ipv4 IP address.')
    parser.add_option('--kernel-id', dest='aki', action='store_true', help='List the AKI.')
    parser.add_option('--product-codes', dest='code', action='store_true', help='List the product codes associated with thsi AMI.')
    parser.add_option('--public-hostname', dest='phostname', action='store_true', help='Show the public hostname.')
    parser.add_option('--public_ipv4', dest='pipv4', action='store_true', help='Show the public IPV4 IP address.')
    parser.add_option('--ramdisk-id', dest='ari', action='store_true', help='Display the ARI.')
    parser.add_option('--reservation-id', dest='rid', action='store_true', help='Display the reservation id.')
    parser.add_option('--security-groups', dest='security', action='store_true', help='Display the security groups.')
    parser.add_option('--ec2-version', dest='ec2', action='store_true', help='Display the current Ubuntu EC2 version')
    parser.add_option('--all',dest='all', action='store_true', help='Display all informantion.')

    options, args = parser.parse_args()

    if options.amiid:
        getData(ec2Data[0])
    if options.launch:
        getData(ec2Data[1])
    if options.manifest:
        getData(ec2Data[2])
    if options.ancestor:
        getData(ec2Data[3])
    if options.block:
        getData(ec2Data[4])
    if options.id:
        getData(ec2Data[5])
    if options.type:
        getData(ec2Data[6])
    if options.lhostname:
        getData(ec2Data[7])
    if options.lipv4:
        getData(ec2Data[8])
    if options.aki:
        getData(ec2Data[9])
    if options.code:
        getData(ec2Data[10])
    if options.phostname:
        getData(ec2Data[11])
    if options.pipv4:
        getData(ec2Data[12])
    if options.ari:
        getData(ec2Data[13])
    if options.rid:
        getData(ec2Data[14])
    if options.security:
        getData(ec2Data[15])
    if options.ec2:
        ec2Version()
    if options.all:
        getAllData(ec2Data)

if __name__ == "__main__":
   main()

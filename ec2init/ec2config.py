#
#    Common code for the EC2 configuration files in Ubuntu
#    Copyright (C) 2008-2010 Canonical Ltd.
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
import yaml
import re

class EC2Config():
	def read_conf(self, ec2Config):
		#stream = file('/tmp/ec2.yaml')
		ec2Config = yaml.load(stream)
		stream.close()
		return ec2Config

	def check_for_updates(self):
		#stream = file('/tmp/ec2.yaml')
		ec2Config = yaml.load(stream)
		stream.close()

		value = ec2Config['apt_update']
		return value

	def check_for_upgrade(self):
		#stream = file('/tmp/ec2.yaml')
		ec2Config = yaml.load(stream)
		stream.close()

		value = ec2Config['apt_upgrade']
		return value
	
	def parse_ssh_keys(self):
		#stream = file('/tmp/ec2.yaml')
		ec2Config = yaml.load(stream)
		stream.close()

		disableRoot = ec2Config['disable_root']
		if disableRoot == 'true':
			value = 'disabled_root'
			return value
		else:
			ec2Key = ec2Config['ec2_fetch_key']
			if ec2Key != 'none':
				value = 'default_key'
				return value
			else:
				return ec2Key

	def add_ppa(self):
		stream = file('/tmp/ec2.yaml')
		ec2Config = yaml.load(stream)
		stream.close()

		value = ec2Config['apt_sources']
		for ent in ec2Config['apt_sources']:
			ppa = ent['source']
			where = ppa.find('ppa:')
			if where != -1:
			  return ppa

	def add_custom_repo(self):
		stream = file('/tmp/ec2.yaml')
		ec2Config = yaml.load(stream)
		stream.close()

		sources = []
		value = ec2Config['apt_sources']
		for ent in ec2Config['apt_sources']:
			if ent.has_key('keyserver'):
				keyserver = ent['keyserver']
			if ent.has_key('keyid'):
				keyid = ent['keyid']
			if ent.has_key('filename'):
				filename = ent['filename']
			source = ent['source']
			if source.startswith("deb"):
				sources.append(source)

		return (keyserver,sources,keyid,filename)

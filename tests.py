#!/usr/bin/python
#
#    Unit tests for EC2-init
#    Copyright (C) 2008-2009 Canonical Ltd.
#
#    Author: Soren Hansen <soren@canonical.com>
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

import re
import os
import unittest

class RunUserDataApplianceTestCase(unittest.TestCase):
    def handle_xml(self, xml):
        msg = self.ec2_run_user_data.parse_user_data(xml)
        self.ec2_run_user_data.handle_part(msg)

class RunUserDataApplianceConfigEBS(RunUserDataApplianceTestCase):
    def setUp(self):
        self.ec2_run_user_data = __import__('ec2-run-user-data')
        reload(self.ec2_run_user_data) 
        self.real_mount_ebs_volume = self.ec2_run_user_data.mount_ebs_volume
        self.ec2_run_user_data.mount_ebs_volume  = self.fake_mount_ebs_volume
    
    def fake_mount_ebs_volume(self, device, paths):
        self.assertEqual(device, '/dev/sdc')
        self.assertEqual(paths, ['/etc/alfresco', '/var/lib/mysql'])

    def testApplianceConfigEBS(self):
        os.environ['EBSMOUNT_DEBUG'] = 'yes, please'
        xml = '<appliance><storage device="/dev/sdc"><path>/etc/alfresco</path><path>/var/lib/mysql</path></storage></appliance>'
        self.handle_xml(xml)

    def testMountEBSVolume(self):
        output = self.real_mount_ebs_volume('/dev/sdh', ['/foo', '/bar'])
        lines = output.strip().split('\n')
        self.assertEqual(len(lines), 11)
        match = re.match('mount /dev/sdh (/var/run/ec2/tmp.[a-zA-Z0-9]+)', lines[0])
        self.assertNotEqual(match, None)
        tmpdir = match.group(1)
        for (i, s) in zip(range(10), ['mkdir %s/_foo', 'cp -a /foo %s/_foo', 'chown --reference /foo %s/_foo', 'chmod --reference /foo %s/_foo', 'mount --bind %s/_foo /foo', 'mkdir %s/_bar', 'cp -a /bar %s/_bar', 'chown --reference /bar %s/_bar', 'chmod --reference /bar %s/_bar', 'mount --bind %s/_bar /bar']):
            self.assertEqual(s % tmpdir, lines[i+1])

class RunUserDataApplianceConfigScript(RunUserDataApplianceTestCase):
    def setUp(self):
        self.ec2_run_user_data = __import__('ec2-run-user-data')
        self.fake_handle_shell_script_counter = 0
        self.expected_scripts = []
        # Override install_remove_package 
        self.ec2_run_user_data.content_type_handlers['text/x-shellscript'] = self.fake_handle_shell_script

    def fake_handle_shell_script(self, txt):
        self.fake_handle_shell_script_counter += 1
        self.assertEqual(self.expected_scripts.pop(0), txt)

    def handle_xml(self, xml):
        msg = self.ec2_run_user_data.parse_user_data(xml)
        self.ec2_run_user_data.handle_part(msg)

    def testApplianceConfigPackageScriptSingle(self):
        script = '''#!/bin/sh
echo hey'''
        xml = '<appliance><script>%s</script></appliance>' % script
        self.expected_scripts += [script]
        self.handle_xml(xml)
        self.assertEqual(self.fake_handle_shell_script_counter, 1) 

    def testApplianceConfigPackageScriptMultiple(self):
        script1 = '''#!/bin/sh
echo hey'''
        script2 = '''#!/usr/bin/python
print "hey"'''
        xml = '<appliance><script>%s</script><script>%s</script></appliance>' % (script1, script2)
        self.expected_scripts += [script1, script2]
        self.handle_xml(xml)
        self.assertEqual(self.fake_handle_shell_script_counter, 2) 

    def testApplianceConfigPackageScriptCDATA(self):
        script = '''#!/bin/sh
echo hey'''
        xml = '<appliance><script><![CDATA[%s]]></script></appliance>' % (script, )
        self.expected_scripts += [script]
        self.handle_xml(xml)
        self.assertEqual(self.fake_handle_shell_script_counter, 1) 

class RunUserDataApplianceConfigPackageHandling(RunUserDataApplianceTestCase):
    def setUp(self):
        self.fake_install_remove_package_counter = 0

        self.ec2_run_user_data = __import__('ec2-run-user-data')

        # Override install_remove_package 
        self.ec2_run_user_data.install_remove_package = self.fake_install_remove_package

    def fake_install_remove_package(self, package, action):
        self.fake_install_remove_package_counter += 1
        mapping = { 'foobarplus': 'install',
                    'foobarminus': 'remove' }
        self.assert_(package in mapping)
        self.assertEqual(action, mapping[package])

    def handle_xml(self, xml):
        msg = self.ec2_run_user_data.parse_user_data(xml)
        self.ec2_run_user_data.handle_part(msg)

    def testApplianceConfigPackageInstall(self):
        xml = '<appliance><package>foobarplus</package></appliance>'
        self.handle_xml(xml)
        self.assertEqual(self.fake_install_remove_package_counter, 1) 

    def testApplianceConfigPackageRemove(self):
        xml = '<appliance><package action="remove">foobarminus</package></appliance>'
        self.handle_xml(xml)
        self.assertEqual(self.fake_install_remove_package_counter, 1) 

    def testApplianceConfigPackageInstallAndRemove(self):
        xml = '<appliance><package>foobarplus</package><package action="remove">foobarminus</package></appliance>'
        self.handle_xml(xml)
        self.assertEqual(self.fake_install_remove_package_counter, 2) 

if __name__ == "__main__":
    unittest.main()  

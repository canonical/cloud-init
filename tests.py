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

import unittest

class RunUserDataApplianceConfigScript(unittest.TestCase):
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

class RunUserDataApplianceConfigPackageHandling(unittest.TestCase):
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

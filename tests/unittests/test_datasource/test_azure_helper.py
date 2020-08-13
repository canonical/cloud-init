# This file is part of cloud-init. See LICENSE file for license information.

import os
import re
import unittest
from textwrap import dedent
from xml.etree import ElementTree

from cloudinit.sources.helpers import azure as azure_helper
from cloudinit.tests.helpers import CiTestCase, ExitStack, mock, populate_dir

from cloudinit.util import load_file
from cloudinit.sources.helpers.azure import WALinuxAgentShim as wa_shim

GOAL_STATE_TEMPLATE = """\
<?xml version="1.0" encoding="utf-8"?>
<GoalState xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
 xsi:noNamespaceSchemaLocation="goalstate10.xsd">
  <Version>2012-11-30</Version>
  <Incarnation>{incarnation}</Incarnation>
  <Machine>
    <ExpectedState>Started</ExpectedState>
    <StopRolesDeadlineHint>300000</StopRolesDeadlineHint>
    <LBProbePorts>
      <Port>16001</Port>
    </LBProbePorts>
    <ExpectHealthReport>FALSE</ExpectHealthReport>
  </Machine>
  <Container>
    <ContainerId>{container_id}</ContainerId>
    <RoleInstanceList>
      <RoleInstance>
        <InstanceId>{instance_id}</InstanceId>
        <State>Started</State>
        <Configuration>
          <HostingEnvironmentConfig>
            http://100.86.192.70:80/...hostingEnvironmentConfig...
          </HostingEnvironmentConfig>
          <SharedConfig>http://100.86.192.70:80/..SharedConfig..</SharedConfig>
          <ExtensionsConfig>
            http://100.86.192.70:80/...extensionsConfig...
          </ExtensionsConfig>
          <FullConfig>http://100.86.192.70:80/...fullConfig...</FullConfig>
          <Certificates>{certificates_url}</Certificates>
          <ConfigName>68ce47.0.68ce47.0.utl-trusty--292258.1.xml</ConfigName>
        </Configuration>
      </RoleInstance>
    </RoleInstanceList>
  </Container>
</GoalState>
"""

HEALTH_REPORT_XML_TEMPLATE = '''\
<?xml version="1.0" encoding="utf-8"?>
<Health xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
 xmlns:xsd="http://www.w3.org/2001/XMLSchema">
  <GoalStateIncarnation>{incarnation}</GoalStateIncarnation>
  <Container>
    <ContainerId>{container_id}</ContainerId>
    <RoleInstanceList>
      <Role>
        <InstanceId>{instance_id}</InstanceId>
        <Health>
          <State>{health_status}</State>
          {health_detail_subsection}
        </Health>
      </Role>
    </RoleInstanceList>
  </Container>
</Health>
'''


class SentinelException(Exception):
    pass


class TestFindEndpoint(CiTestCase):

    def setUp(self):
        super(TestFindEndpoint, self).setUp()
        patches = ExitStack()
        self.addCleanup(patches.close)

        self.load_file = patches.enter_context(
            mock.patch.object(azure_helper.util, 'load_file'))

        self.dhcp_options = patches.enter_context(
            mock.patch.object(wa_shim, '_load_dhclient_json'))

        self.networkd_leases = patches.enter_context(
            mock.patch.object(wa_shim, '_networkd_get_value_from_leases'))
        self.networkd_leases.return_value = None

    def test_missing_file(self):
        """wa_shim find_endpoint uses default endpoint if leasefile not found
        """
        self.assertEqual(wa_shim.find_endpoint(), "168.63.129.16")

    def test_missing_special_azure_line(self):
        """wa_shim find_endpoint uses default endpoint if leasefile is found
        but does not contain DHCP Option 245 (whose value is the endpoint)
        """
        self.load_file.return_value = ''
        self.dhcp_options.return_value = {'eth0': {'key': 'value'}}
        self.assertEqual(wa_shim.find_endpoint(), "168.63.129.16")

    @staticmethod
    def _build_lease_content(encoded_address):
        endpoint = azure_helper._get_dhcp_endpoint_option_name()
        return '\n'.join([
            'lease {',
            ' interface "eth0";',
            ' option {0} {1};'.format(endpoint, encoded_address),
            '}'])

    def test_from_dhcp_client(self):
        self.dhcp_options.return_value = {"eth0": {"unknown_245": "5:4:3:2"}}
        self.assertEqual('5.4.3.2', wa_shim.find_endpoint(None))

    @mock.patch('cloudinit.sources.helpers.azure.util.is_FreeBSD')
    def test_latest_lease_used(self, m_is_freebsd):
        m_is_freebsd.return_value = False  # To avoid hitting load_file
        encoded_addresses = ['5:4:3:2', '4:3:2:1']
        file_content = '\n'.join([self._build_lease_content(encoded_address)
                                  for encoded_address in encoded_addresses])
        self.load_file.return_value = file_content
        self.assertEqual(encoded_addresses[-1].replace(':', '.'),
                         wa_shim.find_endpoint("foobar"))


class TestExtractIpAddressFromLeaseValue(CiTestCase):

    def test_hex_string(self):
        ip_address, encoded_address = '98.76.54.32', '62:4c:36:20'
        self.assertEqual(
            ip_address, wa_shim.get_ip_from_lease_value(encoded_address))

    def test_hex_string_with_single_character_part(self):
        ip_address, encoded_address = '4.3.2.1', '4:3:2:1'
        self.assertEqual(
            ip_address, wa_shim.get_ip_from_lease_value(encoded_address))

    def test_packed_string(self):
        ip_address, encoded_address = '98.76.54.32', 'bL6 '
        self.assertEqual(
            ip_address, wa_shim.get_ip_from_lease_value(encoded_address))

    def test_packed_string_with_escaped_quote(self):
        ip_address, encoded_address = '100.72.34.108', 'dH\\"l'
        self.assertEqual(
            ip_address, wa_shim.get_ip_from_lease_value(encoded_address))

    def test_packed_string_containing_a_colon(self):
        ip_address, encoded_address = '100.72.58.108', 'dH:l'
        self.assertEqual(
            ip_address, wa_shim.get_ip_from_lease_value(encoded_address))


class TestGoalStateParsing(CiTestCase):

    default_parameters = {
        'incarnation': 1,
        'container_id': 'MyContainerId',
        'instance_id': 'MyInstanceId',
        'certificates_url': 'MyCertificatesUrl',
    }

    def _get_formatted_goal_state_xml_string(self, **kwargs):
        parameters = self.default_parameters.copy()
        parameters.update(kwargs)
        xml = GOAL_STATE_TEMPLATE.format(**parameters)
        if parameters['certificates_url'] is None:
            new_xml_lines = []
            for line in xml.splitlines():
                if 'Certificates' in line:
                    continue
                new_xml_lines.append(line)
            xml = '\n'.join(new_xml_lines)
        return xml

    def _get_goal_state(self, m_azure_endpoint_client=None, **kwargs):
        if m_azure_endpoint_client is None:
            m_azure_endpoint_client = mock.MagicMock()
        xml = self._get_formatted_goal_state_xml_string(**kwargs)
        return azure_helper.GoalState(xml, m_azure_endpoint_client)

    def test_incarnation_parsed_correctly(self):
        incarnation = '123'
        goal_state = self._get_goal_state(incarnation=incarnation)
        self.assertEqual(incarnation, goal_state.incarnation)

    def test_container_id_parsed_correctly(self):
        container_id = 'TestContainerId'
        goal_state = self._get_goal_state(container_id=container_id)
        self.assertEqual(container_id, goal_state.container_id)

    def test_instance_id_parsed_correctly(self):
        instance_id = 'TestInstanceId'
        goal_state = self._get_goal_state(instance_id=instance_id)
        self.assertEqual(instance_id, goal_state.instance_id)

    def test_instance_id_byte_swap(self):
        """Return true when previous_iid is byteswapped current_iid"""
        previous_iid = "D0DF4C54-4ECB-4A4B-9954-5BDF3ED5C3B8"
        current_iid = "544CDFD0-CB4E-4B4A-9954-5BDF3ED5C3B8"
        self.assertTrue(
            azure_helper.is_byte_swapped(previous_iid, current_iid))

    def test_instance_id_no_byte_swap_same_instance_id(self):
        previous_iid = "D0DF4C54-4ECB-4A4B-9954-5BDF3ED5C3B8"
        current_iid = "D0DF4C54-4ECB-4A4B-9954-5BDF3ED5C3B8"
        self.assertFalse(
            azure_helper.is_byte_swapped(previous_iid, current_iid))

    def test_instance_id_no_byte_swap_diff_instance_id(self):
        previous_iid = "D0DF4C54-4ECB-4A4B-9954-5BDF3ED5C3B8"
        current_iid = "G0DF4C54-4ECB-4A4B-9954-5BDF3ED5C3B8"
        self.assertFalse(
            azure_helper.is_byte_swapped(previous_iid, current_iid))

    def test_certificates_xml_parsed_and_fetched_correctly(self):
        m_azure_endpoint_client = mock.MagicMock()
        certificates_url = 'TestCertificatesUrl'
        goal_state = self._get_goal_state(
            m_azure_endpoint_client=m_azure_endpoint_client,
            certificates_url=certificates_url)
        certificates_xml = goal_state.certificates_xml
        self.assertEqual(1, m_azure_endpoint_client.get.call_count)
        self.assertEqual(
            certificates_url,
            m_azure_endpoint_client.get.call_args[0][0])
        self.assertTrue(
            m_azure_endpoint_client.get.call_args[1].get(
                'secure', False))
        self.assertEqual(
            m_azure_endpoint_client.get.return_value.contents,
            certificates_xml)

    def test_missing_certificates_skips_http_get(self):
        m_azure_endpoint_client = mock.MagicMock()
        goal_state = self._get_goal_state(
            m_azure_endpoint_client=m_azure_endpoint_client,
            certificates_url=None)
        certificates_xml = goal_state.certificates_xml
        self.assertEqual(0, m_azure_endpoint_client.get.call_count)
        self.assertIsNone(certificates_xml)

    def test_invalid_goal_state_xml_raises_parse_error(self):
        xml = 'random non-xml data'
        with self.assertRaises(ElementTree.ParseError):
            azure_helper.GoalState(xml, mock.MagicMock())

    def test_missing_container_id_in_goal_state_xml_raises_exc(self):
        xml = self._get_formatted_goal_state_xml_string()
        xml = re.sub('<ContainerId>.*</ContainerId>', '', xml)
        with self.assertRaises(azure_helper.InvalidGoalStateXMLException):
            azure_helper.GoalState(xml, mock.MagicMock())

    def test_missing_instance_id_in_goal_state_xml_raises_exc(self):
        xml = self._get_formatted_goal_state_xml_string()
        xml = re.sub('<InstanceId>.*</InstanceId>', '', xml)
        with self.assertRaises(azure_helper.InvalidGoalStateXMLException):
            azure_helper.GoalState(xml, mock.MagicMock())

    def test_missing_incarnation_in_goal_state_xml_raises_exc(self):
        xml = self._get_formatted_goal_state_xml_string()
        xml = re.sub('<Incarnation>.*</Incarnation>', '', xml)
        with self.assertRaises(azure_helper.InvalidGoalStateXMLException):
            azure_helper.GoalState(xml, mock.MagicMock())


class TestAzureEndpointHttpClient(CiTestCase):

    regular_headers = {
        'x-ms-agent-name': 'WALinuxAgent',
        'x-ms-version': '2012-11-30',
    }

    def setUp(self):
        super(TestAzureEndpointHttpClient, self).setUp()
        patches = ExitStack()
        self.addCleanup(patches.close)

        self.readurl = patches.enter_context(
            mock.patch.object(azure_helper.url_helper, 'readurl'))
        patches.enter_context(
            mock.patch.object(azure_helper.time, 'sleep', mock.MagicMock()))

    def test_non_secure_get(self):
        client = azure_helper.AzureEndpointHttpClient(mock.MagicMock())
        url = 'MyTestUrl'
        response = client.get(url, secure=False)
        self.assertEqual(1, self.readurl.call_count)
        self.assertEqual(self.readurl.return_value, response)
        self.assertEqual(
            mock.call(url, headers=self.regular_headers,
                      timeout=5, retries=10, sec_between=5),
            self.readurl.call_args)

    def test_non_secure_get_raises_exception(self):
        client = azure_helper.AzureEndpointHttpClient(mock.MagicMock())
        self.readurl.side_effect = SentinelException
        url = 'MyTestUrl'
        with self.assertRaises(SentinelException):
            client.get(url, secure=False)

    def test_secure_get(self):
        url = 'MyTestUrl'
        m_certificate = mock.MagicMock()
        expected_headers = self.regular_headers.copy()
        expected_headers.update({
            "x-ms-cipher-name": "DES_EDE3_CBC",
            "x-ms-guest-agent-public-x509-cert": m_certificate,
        })
        client = azure_helper.AzureEndpointHttpClient(m_certificate)
        response = client.get(url, secure=True)
        self.assertEqual(1, self.readurl.call_count)
        self.assertEqual(self.readurl.return_value, response)
        self.assertEqual(
            mock.call(url, headers=expected_headers,
                      timeout=5, retries=10, sec_between=5),
            self.readurl.call_args)

    def test_secure_get_raises_exception(self):
        url = 'MyTestUrl'
        client = azure_helper.AzureEndpointHttpClient(mock.MagicMock())
        self.readurl.side_effect = SentinelException
        with self.assertRaises(SentinelException):
            client.get(url, secure=True)

    def test_post(self):
        m_data = mock.MagicMock()
        url = 'MyTestUrl'
        client = azure_helper.AzureEndpointHttpClient(mock.MagicMock())
        response = client.post(url, data=m_data)
        self.assertEqual(1, self.readurl.call_count)
        self.assertEqual(self.readurl.return_value, response)
        self.assertEqual(
            mock.call(url, data=m_data, headers=self.regular_headers,
                      timeout=5, retries=10, sec_between=5),
            self.readurl.call_args)

    def test_post_raises_exception(self):
        m_data = mock.MagicMock()
        url = 'MyTestUrl'
        client = azure_helper.AzureEndpointHttpClient(mock.MagicMock())
        self.readurl.side_effect = SentinelException
        with self.assertRaises(SentinelException):
            client.post(url, data=m_data)

    def test_post_with_extra_headers(self):
        url = 'MyTestUrl'
        client = azure_helper.AzureEndpointHttpClient(mock.MagicMock())
        extra_headers = {'test': 'header'}
        client.post(url, extra_headers=extra_headers)
        expected_headers = self.regular_headers.copy()
        expected_headers.update(extra_headers)
        self.assertEqual(1, self.readurl.call_count)
        self.assertEqual(
            mock.call(mock.ANY, data=mock.ANY, headers=expected_headers,
                      timeout=5, retries=10, sec_between=5),
            self.readurl.call_args)

    def test_post_with_sleep_with_extra_headers_raises_exception(self):
        m_data = mock.MagicMock()
        url = 'MyTestUrl'
        extra_headers = {'test': 'header'}
        client = azure_helper.AzureEndpointHttpClient(mock.MagicMock())
        self.readurl.side_effect = SentinelException
        with self.assertRaises(SentinelException):
            client.post(
                url, data=m_data, extra_headers=extra_headers)


class TestOpenSSLManager(CiTestCase):

    def setUp(self):
        super(TestOpenSSLManager, self).setUp()
        patches = ExitStack()
        self.addCleanup(patches.close)

        self.subp = patches.enter_context(
            mock.patch.object(azure_helper.subp, 'subp'))
        try:
            self.open = patches.enter_context(
                mock.patch('__builtin__.open'))
        except ImportError:
            self.open = patches.enter_context(
                mock.patch('builtins.open'))

    @mock.patch.object(azure_helper, 'cd', mock.MagicMock())
    @mock.patch.object(azure_helper.temp_utils, 'mkdtemp')
    def test_openssl_manager_creates_a_tmpdir(self, mkdtemp):
        manager = azure_helper.OpenSSLManager()
        self.assertEqual(mkdtemp.return_value, manager.tmpdir)

    def test_generate_certificate_uses_tmpdir(self):
        subp_directory = {}

        def capture_directory(*args, **kwargs):
            subp_directory['path'] = os.getcwd()

        self.subp.side_effect = capture_directory
        manager = azure_helper.OpenSSLManager()
        self.assertEqual(manager.tmpdir, subp_directory['path'])
        manager.clean_up()

    @mock.patch.object(azure_helper, 'cd', mock.MagicMock())
    @mock.patch.object(azure_helper.temp_utils, 'mkdtemp', mock.MagicMock())
    @mock.patch.object(azure_helper.util, 'del_dir')
    def test_clean_up(self, del_dir):
        manager = azure_helper.OpenSSLManager()
        manager.clean_up()
        self.assertEqual([mock.call(manager.tmpdir)], del_dir.call_args_list)


class TestOpenSSLManagerActions(CiTestCase):

    def setUp(self):
        super(TestOpenSSLManagerActions, self).setUp()

        self.allowed_subp = True

    def _data_file(self, name):
        path = 'tests/data/azure'
        return os.path.join(path, name)

    @unittest.skip("todo move to cloud_test")
    def test_pubkey_extract(self):
        cert = load_file(self._data_file('pubkey_extract_cert'))
        good_key = load_file(self._data_file('pubkey_extract_ssh_key'))
        sslmgr = azure_helper.OpenSSLManager()
        key = sslmgr._get_ssh_key_from_cert(cert)
        self.assertEqual(good_key, key)

        good_fingerprint = '073E19D14D1C799224C6A0FD8DDAB6A8BF27D473'
        fingerprint = sslmgr._get_fingerprint_from_cert(cert)
        self.assertEqual(good_fingerprint, fingerprint)

    @unittest.skip("todo move to cloud_test")
    @mock.patch.object(azure_helper.OpenSSLManager, '_decrypt_certs_from_xml')
    def test_parse_certificates(self, mock_decrypt_certs):
        """Azure control plane puts private keys as well as certificates
           into the Certificates XML object. Make sure only the public keys
           from certs are extracted and that fingerprints are converted to
           the form specified in the ovf-env.xml file.
        """
        cert_contents = load_file(self._data_file('parse_certificates_pem'))
        fingerprints = load_file(self._data_file(
            'parse_certificates_fingerprints')
        ).splitlines()
        mock_decrypt_certs.return_value = cert_contents
        sslmgr = azure_helper.OpenSSLManager()
        keys_by_fp = sslmgr.parse_certificates('')
        for fp in keys_by_fp.keys():
            self.assertIn(fp, fingerprints)
        for fp in fingerprints:
            self.assertIn(fp, keys_by_fp)


class TestGoalStateHealthReporter(CiTestCase):

    default_parameters = {
        'incarnation': 1634,
        'container_id': 'MyContainerId',
        'instance_id': 'MyInstanceId'
    }

    test_endpoint = 'TestEndpoint'
    test_url = 'http://{0}/machine?comp=health'.format(test_endpoint)
    test_default_headers = {'Content-Type': 'text/xml; charset=utf-8'}

    provisioning_success_status = 'Ready'

    def setUp(self):
        super(TestGoalStateHealthReporter, self).setUp()
        patches = ExitStack()
        self.addCleanup(patches.close)

        patches.enter_context(
            mock.patch.object(azure_helper.time, 'sleep', mock.MagicMock()))
        self.read_file_or_url = patches.enter_context(
            mock.patch.object(azure_helper.url_helper, 'read_file_or_url'))

        self.post = patches.enter_context(
            mock.patch.object(azure_helper.AzureEndpointHttpClient,
                              'post'))

        self.GoalState = patches.enter_context(
            mock.patch.object(azure_helper, 'GoalState'))
        self.GoalState.return_value.container_id = \
            self.default_parameters['container_id']
        self.GoalState.return_value.instance_id = \
            self.default_parameters['instance_id']
        self.GoalState.return_value.incarnation = \
            self.default_parameters['incarnation']

    def _get_formatted_health_report_xml_string(self, **kwargs):
        return HEALTH_REPORT_XML_TEMPLATE.format(**kwargs)

    def _get_report_ready_health_document(self):
        return self._get_formatted_health_report_xml_string(
            incarnation=self.default_parameters['incarnation'],
            container_id=self.default_parameters['container_id'],
            instance_id=self.default_parameters['instance_id'],
            health_status=self.provisioning_success_status,
            health_detail_subsection='')

    def test_send_ready_signal_sends_post_request(self):
        with mock.patch.object(
                azure_helper.GoalStateHealthReporter,
                'build_report') as m_build_report:
            client = azure_helper.AzureEndpointHttpClient(mock.MagicMock())
            reporter = azure_helper.GoalStateHealthReporter(
                azure_helper.GoalState(mock.MagicMock(), mock.MagicMock()),
                client, self.test_endpoint)
            reporter.send_ready_signal()

            self.assertEqual(1, self.post.call_count)
            self.assertEqual(
                mock.call(
                    self.test_url,
                    data=m_build_report.return_value,
                    extra_headers=self.test_default_headers),
                self.post.call_args)

    def test_build_report_for_health_document(self):
        health_document = self._get_report_ready_health_document()
        reporter = azure_helper.GoalStateHealthReporter(
            azure_helper.GoalState(mock.MagicMock(), mock.MagicMock()),
            azure_helper.AzureEndpointHttpClient(mock.MagicMock()),
            self.test_endpoint)
        generated_health_document = reporter.build_report(
            incarnation=self.default_parameters['incarnation'],
            container_id=self.default_parameters['container_id'],
            instance_id=self.default_parameters['instance_id'],
            status=self.provisioning_success_status)
        self.assertEqual(health_document, generated_health_document)
        self.assertIn(
            '<GoalStateIncarnation>{}</GoalStateIncarnation>'.format(
                str(self.default_parameters['incarnation'])),
            generated_health_document)
        self.assertIn(
            ''.join([
                '<ContainerId>',
                self.default_parameters['container_id'],
                '</ContainerId>']),
            generated_health_document)
        self.assertIn(
            ''.join([
                '<InstanceId>',
                self.default_parameters['instance_id'],
                '</InstanceId>']),
            generated_health_document)
        self.assertIn(
            ''.join([
                '<State>',
                self.provisioning_success_status,
                '</State>']),
            generated_health_document
        )
        self.assertNotIn('<Details>', generated_health_document)
        self.assertNotIn('<SubStatus>', generated_health_document)
        self.assertNotIn('<Description>', generated_health_document)

    def test_send_ready_signal_calls_build_report(self):
        with mock.patch.object(
            azure_helper.GoalStateHealthReporter, 'build_report'
        ) as m_build_report:
            reporter = azure_helper.GoalStateHealthReporter(
                azure_helper.GoalState(mock.MagicMock(), mock.MagicMock()),
                azure_helper.AzureEndpointHttpClient(mock.MagicMock()),
                self.test_endpoint)
            reporter.send_ready_signal()

            self.assertEqual(1, m_build_report.call_count)
            self.assertEqual(
                mock.call(
                    incarnation=self.default_parameters['incarnation'],
                    container_id=self.default_parameters['container_id'],
                    instance_id=self.default_parameters['instance_id'],
                    status=self.provisioning_success_status),
                m_build_report.call_args)


class TestWALinuxAgentShim(CiTestCase):

    def setUp(self):
        super(TestWALinuxAgentShim, self).setUp()
        patches = ExitStack()
        self.addCleanup(patches.close)

        self.AzureEndpointHttpClient = patches.enter_context(
            mock.patch.object(azure_helper, 'AzureEndpointHttpClient'))
        self.find_endpoint = patches.enter_context(
            mock.patch.object(wa_shim, 'find_endpoint'))
        self.GoalState = patches.enter_context(
            mock.patch.object(azure_helper, 'GoalState'))
        self.OpenSSLManager = patches.enter_context(
            mock.patch.object(azure_helper, 'OpenSSLManager'))
        patches.enter_context(
            mock.patch.object(azure_helper.time, 'sleep', mock.MagicMock()))

        self.test_incarnation = 'TestIncarnation'
        self.test_container_id = 'TestContainerId'
        self.test_instance_id = 'TestInstanceId'
        self.GoalState.return_value.incarnation = self.test_incarnation
        self.GoalState.return_value.container_id = self.test_container_id
        self.GoalState.return_value.instance_id = self.test_instance_id

    def test_azure_endpoint_client_uses_certificate_during_report_ready(self):
        shim = wa_shim()
        shim.register_with_azure_and_fetch_data()
        self.assertEqual(
            [mock.call(self.OpenSSLManager.return_value.certificate)],
            self.AzureEndpointHttpClient.call_args_list)

    def test_correct_url_used_for_goalstate_during_report_ready(self):
        self.find_endpoint.return_value = 'test_endpoint'
        shim = wa_shim()
        shim.register_with_azure_and_fetch_data()
        get = self.AzureEndpointHttpClient.return_value.get
        self.assertEqual(
            [mock.call('http://test_endpoint/machine/?comp=goalstate')],
            get.call_args_list)
        self.assertEqual(
            [mock.call(get.return_value.contents,
                       self.AzureEndpointHttpClient.return_value)],
            self.GoalState.call_args_list)

    def test_certificates_used_to_determine_public_keys(self):
        # if register_with_azure_and_fetch_data() isn't passed some info about
        # the user's public keys, there's no point in even trying to parse the
        # certificates
        shim = wa_shim()
        mypk = [{'fingerprint': 'fp1', 'path': 'path1'},
                {'fingerprint': 'fp3', 'path': 'path3', 'value': ''}]
        certs = {'fp1': 'expected-key',
                 'fp2': 'should-not-be-found',
                 'fp3': 'expected-no-value-key',
                 }
        sslmgr = self.OpenSSLManager.return_value
        sslmgr.parse_certificates.return_value = certs
        data = shim.register_with_azure_and_fetch_data(pubkey_info=mypk)
        self.assertEqual(
            [mock.call(self.GoalState.return_value.certificates_xml)],
            sslmgr.parse_certificates.call_args_list)
        self.assertIn('expected-key', data['public-keys'])
        self.assertIn('expected-no-value-key', data['public-keys'])
        self.assertNotIn('should-not-be-found', data['public-keys'])

    def test_absent_certificates_produces_empty_public_keys(self):
        mypk = [{'fingerprint': 'fp1', 'path': 'path1'}]
        self.GoalState.return_value.certificates_xml = None
        shim = wa_shim()
        data = shim.register_with_azure_and_fetch_data(pubkey_info=mypk)
        self.assertEqual([], data['public-keys'])

    def test_correct_url_used_for_report_ready(self):
        self.find_endpoint.return_value = 'test_endpoint'
        shim = wa_shim()
        shim.register_with_azure_and_fetch_data()
        expected_url = 'http://test_endpoint/machine?comp=health'
        self.assertEqual(
            [mock.call(expected_url, data=mock.ANY, extra_headers=mock.ANY)],
            self.AzureEndpointHttpClient.return_value.post
                .call_args_list)

    def test_goal_state_values_used_for_report_ready(self):
        shim = wa_shim()
        shim.register_with_azure_and_fetch_data()
        posted_document = (
            self.AzureEndpointHttpClient.return_value.post
                .call_args[1]['data']
        )
        self.assertIn(self.test_incarnation, posted_document)
        self.assertIn(self.test_container_id, posted_document)
        self.assertIn(self.test_instance_id, posted_document)

    def test_xml_elems_in_report_ready(self):
        shim = wa_shim()
        shim.register_with_azure_and_fetch_data()
        health_document = HEALTH_REPORT_XML_TEMPLATE.format(
            incarnation=self.test_incarnation,
            container_id=self.test_container_id,
            instance_id=self.test_instance_id,
            health_status='Ready',
            health_detail_subsection='')
        posted_document = (
            self.AzureEndpointHttpClient.return_value.post
                .call_args[1]['data'])
        self.assertEqual(health_document, posted_document)

    def test_clean_up_can_be_called_at_any_time(self):
        shim = wa_shim()
        shim.clean_up()

    def test_clean_up_after_report_ready(self):
        shim = wa_shim()
        shim.register_with_azure_and_fetch_data()
        shim.clean_up()
        self.assertEqual(
            1, self.OpenSSLManager.return_value.clean_up.call_count)

    def test_fetch_goalstate_during_report_ready_raises_exc_on_get_exc(self):
        self.AzureEndpointHttpClient.return_value.get \
            .side_effect = (SentinelException)
        shim = wa_shim()
        self.assertRaises(SentinelException,
                          shim.register_with_azure_and_fetch_data)

    def test_fetch_goalstate_during_report_ready_raises_exc_on_parse_exc(self):
        self.GoalState.side_effect = SentinelException
        shim = wa_shim()
        self.assertRaises(SentinelException,
                          shim.register_with_azure_and_fetch_data)

    def test_failure_to_send_report_ready_health_doc_bubbles_up(self):
        self.AzureEndpointHttpClient.return_value.post \
            .side_effect = SentinelException
        shim = wa_shim()
        self.assertRaises(SentinelException,
                          shim.register_with_azure_and_fetch_data)


class TestGetMetadataGoalStateXMLAndReportReadyToFabric(CiTestCase):

    @mock.patch.object(azure_helper, 'WALinuxAgentShim')
    def test_data_from_shim_returned(self, shim):
        ret = azure_helper.get_metadata_from_fabric()
        self.assertEqual(
            shim.return_value.register_with_azure_and_fetch_data.return_value,
            ret)

    @mock.patch.object(azure_helper, 'WALinuxAgentShim')
    def test_success_calls_clean_up(self, shim):
        azure_helper.get_metadata_from_fabric()
        self.assertEqual(1, shim.return_value.clean_up.call_count)

    @mock.patch.object(azure_helper, 'WALinuxAgentShim')
    def test_failure_in_registration_calls_clean_up(self, shim):
        shim.return_value.register_with_azure_and_fetch_data.side_effect = (
            SentinelException)
        self.assertRaises(SentinelException,
                          azure_helper.get_metadata_from_fabric)
        self.assertEqual(1, shim.return_value.clean_up.call_count)

    @mock.patch.object(azure_helper, 'WALinuxAgentShim')
    def test_calls_shim_register_with_azure_and_fetch_data(self, shim):
        m_pubkey_info = mock.MagicMock()
        azure_helper.get_metadata_from_fabric(pubkey_info=m_pubkey_info)
        self.assertEqual(
            1,
            shim.return_value
                .register_with_azure_and_fetch_data.call_count)
        self.assertEqual(
            mock.call(pubkey_info=m_pubkey_info),
            shim.return_value
                .register_with_azure_and_fetch_data.call_args)

    @mock.patch.object(azure_helper, 'WALinuxAgentShim')
    def test_instantiates_shim_with_kwargs(self, shim):
        m_fallback_lease_file = mock.MagicMock()
        m_dhcp_options = mock.MagicMock()
        azure_helper.get_metadata_from_fabric(
            fallback_lease_file=m_fallback_lease_file,
            dhcp_opts=m_dhcp_options)
        self.assertEqual(1, shim.call_count)
        self.assertEqual(
            mock.call(
                fallback_lease_file=m_fallback_lease_file,
                dhcp_options=m_dhcp_options),
            shim.call_args)


class TestExtractIpAddressFromNetworkd(CiTestCase):

    azure_lease = dedent("""\
    # This is private data. Do not parse.
    ADDRESS=10.132.0.5
    NETMASK=255.255.255.255
    ROUTER=10.132.0.1
    SERVER_ADDRESS=169.254.169.254
    NEXT_SERVER=10.132.0.1
    MTU=1460
    T1=43200
    T2=75600
    LIFETIME=86400
    DNS=169.254.169.254
    NTP=169.254.169.254
    DOMAINNAME=c.ubuntu-foundations.internal
    DOMAIN_SEARCH_LIST=c.ubuntu-foundations.internal google.internal
    HOSTNAME=tribaal-test-171002-1349.c.ubuntu-foundations.internal
    ROUTES=10.132.0.1/32,0.0.0.0 0.0.0.0/0,10.132.0.1
    CLIENTID=ff405663a200020000ab11332859494d7a8b4c
    OPTION_245=624c3620
    """)

    def setUp(self):
        super(TestExtractIpAddressFromNetworkd, self).setUp()
        self.lease_d = self.tmp_dir()

    def test_no_valid_leases_is_none(self):
        """No valid leases should return None."""
        self.assertIsNone(
            wa_shim._networkd_get_value_from_leases(self.lease_d))

    def test_option_245_is_found_in_single(self):
        """A single valid lease with 245 option should return it."""
        populate_dir(self.lease_d, {'9': self.azure_lease})
        self.assertEqual(
            '624c3620', wa_shim._networkd_get_value_from_leases(self.lease_d))

    def test_option_245_not_found_returns_None(self):
        """A valid lease, but no option 245 should return None."""
        populate_dir(
            self.lease_d,
            {'9': self.azure_lease.replace("OPTION_245", "OPTION_999")})
        self.assertIsNone(
            wa_shim._networkd_get_value_from_leases(self.lease_d))

    def test_multiple_returns_first(self):
        """Somewhat arbitrarily return the first address when multiple.

        Most important at the moment is that this is consistent behavior
        rather than changing randomly as in order of a dictionary."""
        myval = "624c3601"
        populate_dir(
            self.lease_d,
            {'9': self.azure_lease,
             '2': self.azure_lease.replace("624c3620", myval)})
        self.assertEqual(
            myval, wa_shim._networkd_get_value_from_leases(self.lease_d))


# vi: ts=4 expandtab

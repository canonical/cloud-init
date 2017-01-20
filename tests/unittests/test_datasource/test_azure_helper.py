# This file is part of cloud-init. See LICENSE file for license information.

import os

from cloudinit.sources.helpers import azure as azure_helper

from ..helpers import ExitStack, mock, TestCase


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


class TestFindEndpoint(TestCase):

    def setUp(self):
        super(TestFindEndpoint, self).setUp()
        patches = ExitStack()
        self.addCleanup(patches.close)

        self.load_file = patches.enter_context(
            mock.patch.object(azure_helper.util, 'load_file'))

        self.dhcp_options = patches.enter_context(
            mock.patch.object(azure_helper.WALinuxAgentShim,
                              '_load_dhclient_json'))

    def test_missing_file(self):
        self.assertRaises(ValueError,
                          azure_helper.WALinuxAgentShim.find_endpoint)

    def test_missing_special_azure_line(self):
        self.load_file.return_value = ''
        self.dhcp_options.return_value = {'eth0': {'key': 'value'}}
        self.assertRaises(ValueError,
                          azure_helper.WALinuxAgentShim.find_endpoint)

    @staticmethod
    def _build_lease_content(encoded_address):
        return '\n'.join([
            'lease {',
            ' interface "eth0";',
            ' option unknown-245 {0};'.format(encoded_address),
            '}'])

    def test_from_dhcp_client(self):
        self.dhcp_options.return_value = {"eth0": {"unknown_245": "5:4:3:2"}}
        self.assertEqual('5.4.3.2',
                         azure_helper.WALinuxAgentShim.find_endpoint(None))

    def test_latest_lease_used(self):
        encoded_addresses = ['5:4:3:2', '4:3:2:1']
        file_content = '\n'.join([self._build_lease_content(encoded_address)
                                  for encoded_address in encoded_addresses])
        self.load_file.return_value = file_content
        self.assertEqual(encoded_addresses[-1].replace(':', '.'),
                         azure_helper.WALinuxAgentShim.find_endpoint("foobar"))


class TestExtractIpAddressFromLeaseValue(TestCase):

    def test_hex_string(self):
        ip_address, encoded_address = '98.76.54.32', '62:4c:36:20'
        self.assertEqual(
            ip_address,
            azure_helper.WALinuxAgentShim.get_ip_from_lease_value(
                encoded_address
            ))

    def test_hex_string_with_single_character_part(self):
        ip_address, encoded_address = '4.3.2.1', '4:3:2:1'
        self.assertEqual(
            ip_address,
            azure_helper.WALinuxAgentShim.get_ip_from_lease_value(
                encoded_address
            ))

    def test_packed_string(self):
        ip_address, encoded_address = '98.76.54.32', 'bL6 '
        self.assertEqual(
            ip_address,
            azure_helper.WALinuxAgentShim.get_ip_from_lease_value(
                encoded_address
            ))

    def test_packed_string_with_escaped_quote(self):
        ip_address, encoded_address = '100.72.34.108', 'dH\\"l'
        self.assertEqual(
            ip_address,
            azure_helper.WALinuxAgentShim.get_ip_from_lease_value(
                encoded_address
            ))

    def test_packed_string_containing_a_colon(self):
        ip_address, encoded_address = '100.72.58.108', 'dH:l'
        self.assertEqual(
            ip_address,
            azure_helper.WALinuxAgentShim.get_ip_from_lease_value(
                encoded_address
            ))


class TestGoalStateParsing(TestCase):

    default_parameters = {
        'incarnation': 1,
        'container_id': 'MyContainerId',
        'instance_id': 'MyInstanceId',
        'certificates_url': 'MyCertificatesUrl',
    }

    def _get_goal_state(self, http_client=None, **kwargs):
        if http_client is None:
            http_client = mock.MagicMock()
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
        return azure_helper.GoalState(xml, http_client)

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

    def test_certificates_xml_parsed_and_fetched_correctly(self):
        http_client = mock.MagicMock()
        certificates_url = 'TestCertificatesUrl'
        goal_state = self._get_goal_state(
            http_client=http_client, certificates_url=certificates_url)
        certificates_xml = goal_state.certificates_xml
        self.assertEqual(1, http_client.get.call_count)
        self.assertEqual(certificates_url, http_client.get.call_args[0][0])
        self.assertTrue(http_client.get.call_args[1].get('secure', False))
        self.assertEqual(http_client.get.return_value.contents,
                         certificates_xml)

    def test_missing_certificates_skips_http_get(self):
        http_client = mock.MagicMock()
        goal_state = self._get_goal_state(
            http_client=http_client, certificates_url=None)
        certificates_xml = goal_state.certificates_xml
        self.assertEqual(0, http_client.get.call_count)
        self.assertIsNone(certificates_xml)


class TestAzureEndpointHttpClient(TestCase):

    regular_headers = {
        'x-ms-agent-name': 'WALinuxAgent',
        'x-ms-version': '2012-11-30',
    }

    def setUp(self):
        super(TestAzureEndpointHttpClient, self).setUp()
        patches = ExitStack()
        self.addCleanup(patches.close)

        self.read_file_or_url = patches.enter_context(
            mock.patch.object(azure_helper.util, 'read_file_or_url'))

    def test_non_secure_get(self):
        client = azure_helper.AzureEndpointHttpClient(mock.MagicMock())
        url = 'MyTestUrl'
        response = client.get(url, secure=False)
        self.assertEqual(1, self.read_file_or_url.call_count)
        self.assertEqual(self.read_file_or_url.return_value, response)
        self.assertEqual(mock.call(url, headers=self.regular_headers),
                         self.read_file_or_url.call_args)

    def test_secure_get(self):
        url = 'MyTestUrl'
        certificate = mock.MagicMock()
        expected_headers = self.regular_headers.copy()
        expected_headers.update({
            "x-ms-cipher-name": "DES_EDE3_CBC",
            "x-ms-guest-agent-public-x509-cert": certificate,
        })
        client = azure_helper.AzureEndpointHttpClient(certificate)
        response = client.get(url, secure=True)
        self.assertEqual(1, self.read_file_or_url.call_count)
        self.assertEqual(self.read_file_or_url.return_value, response)
        self.assertEqual(mock.call(url, headers=expected_headers),
                         self.read_file_or_url.call_args)

    def test_post(self):
        data = mock.MagicMock()
        url = 'MyTestUrl'
        client = azure_helper.AzureEndpointHttpClient(mock.MagicMock())
        response = client.post(url, data=data)
        self.assertEqual(1, self.read_file_or_url.call_count)
        self.assertEqual(self.read_file_or_url.return_value, response)
        self.assertEqual(
            mock.call(url, data=data, headers=self.regular_headers),
            self.read_file_or_url.call_args)

    def test_post_with_extra_headers(self):
        url = 'MyTestUrl'
        client = azure_helper.AzureEndpointHttpClient(mock.MagicMock())
        extra_headers = {'test': 'header'}
        client.post(url, extra_headers=extra_headers)
        self.assertEqual(1, self.read_file_or_url.call_count)
        expected_headers = self.regular_headers.copy()
        expected_headers.update(extra_headers)
        self.assertEqual(
            mock.call(mock.ANY, data=mock.ANY, headers=expected_headers),
            self.read_file_or_url.call_args)


class TestOpenSSLManager(TestCase):

    def setUp(self):
        super(TestOpenSSLManager, self).setUp()
        patches = ExitStack()
        self.addCleanup(patches.close)

        self.subp = patches.enter_context(
            mock.patch.object(azure_helper.util, 'subp'))
        try:
            self.open = patches.enter_context(
                mock.patch('__builtin__.open'))
        except ImportError:
            self.open = patches.enter_context(
                mock.patch('builtins.open'))

    @mock.patch.object(azure_helper, 'cd', mock.MagicMock())
    @mock.patch.object(azure_helper.tempfile, 'mkdtemp')
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
    @mock.patch.object(azure_helper.tempfile, 'mkdtemp', mock.MagicMock())
    @mock.patch.object(azure_helper.util, 'del_dir')
    def test_clean_up(self, del_dir):
        manager = azure_helper.OpenSSLManager()
        manager.clean_up()
        self.assertEqual([mock.call(manager.tmpdir)], del_dir.call_args_list)


class TestWALinuxAgentShim(TestCase):

    def setUp(self):
        super(TestWALinuxAgentShim, self).setUp()
        patches = ExitStack()
        self.addCleanup(patches.close)

        self.AzureEndpointHttpClient = patches.enter_context(
            mock.patch.object(azure_helper, 'AzureEndpointHttpClient'))
        self.find_endpoint = patches.enter_context(
            mock.patch.object(
                azure_helper.WALinuxAgentShim, 'find_endpoint'))
        self.GoalState = patches.enter_context(
            mock.patch.object(azure_helper, 'GoalState'))
        self.OpenSSLManager = patches.enter_context(
            mock.patch.object(azure_helper, 'OpenSSLManager'))
        patches.enter_context(
            mock.patch.object(azure_helper.time, 'sleep', mock.MagicMock()))

    def test_http_client_uses_certificate(self):
        shim = azure_helper.WALinuxAgentShim()
        shim.register_with_azure_and_fetch_data()
        self.assertEqual(
            [mock.call(self.OpenSSLManager.return_value.certificate)],
            self.AzureEndpointHttpClient.call_args_list)

    def test_correct_url_used_for_goalstate(self):
        self.find_endpoint.return_value = 'test_endpoint'
        shim = azure_helper.WALinuxAgentShim()
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
        shim = azure_helper.WALinuxAgentShim()
        data = shim.register_with_azure_and_fetch_data()
        self.assertEqual(
            [mock.call(self.GoalState.return_value.certificates_xml)],
            self.OpenSSLManager.return_value.parse_certificates.call_args_list)
        self.assertEqual(
            self.OpenSSLManager.return_value.parse_certificates.return_value,
            data['public-keys'])

    def test_absent_certificates_produces_empty_public_keys(self):
        self.GoalState.return_value.certificates_xml = None
        shim = azure_helper.WALinuxAgentShim()
        data = shim.register_with_azure_and_fetch_data()
        self.assertEqual([], data['public-keys'])

    def test_correct_url_used_for_report_ready(self):
        self.find_endpoint.return_value = 'test_endpoint'
        shim = azure_helper.WALinuxAgentShim()
        shim.register_with_azure_and_fetch_data()
        expected_url = 'http://test_endpoint/machine?comp=health'
        self.assertEqual(
            [mock.call(expected_url, data=mock.ANY, extra_headers=mock.ANY)],
            self.AzureEndpointHttpClient.return_value.post.call_args_list)

    def test_goal_state_values_used_for_report_ready(self):
        self.GoalState.return_value.incarnation = 'TestIncarnation'
        self.GoalState.return_value.container_id = 'TestContainerId'
        self.GoalState.return_value.instance_id = 'TestInstanceId'
        shim = azure_helper.WALinuxAgentShim()
        shim.register_with_azure_and_fetch_data()
        posted_document = (
            self.AzureEndpointHttpClient.return_value.post.call_args[1]['data']
        )
        self.assertIn('TestIncarnation', posted_document)
        self.assertIn('TestContainerId', posted_document)
        self.assertIn('TestInstanceId', posted_document)

    def test_clean_up_can_be_called_at_any_time(self):
        shim = azure_helper.WALinuxAgentShim()
        shim.clean_up()

    def test_clean_up_will_clean_up_openssl_manager_if_instantiated(self):
        shim = azure_helper.WALinuxAgentShim()
        shim.register_with_azure_and_fetch_data()
        shim.clean_up()
        self.assertEqual(
            1, self.OpenSSLManager.return_value.clean_up.call_count)

    def test_failure_to_fetch_goalstate_bubbles_up(self):
        class SentinelException(Exception):
            pass
        self.AzureEndpointHttpClient.return_value.get.side_effect = (
            SentinelException)
        shim = azure_helper.WALinuxAgentShim()
        self.assertRaises(SentinelException,
                          shim.register_with_azure_and_fetch_data)


class TestGetMetadataFromFabric(TestCase):

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
        class SentinelException(Exception):
            pass
        shim.return_value.register_with_azure_and_fetch_data.side_effect = (
            SentinelException)
        self.assertRaises(SentinelException,
                          azure_helper.get_metadata_from_fabric)
        self.assertEqual(1, shim.return_value.clean_up.call_count)

# vi: ts=4 expandtab

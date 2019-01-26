.. _instance_metadata:

*****************
Instance Metadata
*****************

What is a instance data?
========================

Instance data is the collection of all configuration data that cloud-init
processes to configure the instance. This configuration typically
comes from any number of sources:

* cloud-provided metadata services (aka metadata)
* custom config-drive attached to the instance
* cloud-config seed files in the booted cloud image or distribution
* vendordata provided from files or cloud metadata services
* userdata provided at instance creation

Each cloud provider presents unique configuration metadata in different
formats to the instance. Cloud-init provides a cache of any crawled metadata
as well as a versioned set of standardized instance data keys which it makes
available on all platforms.

Cloud-init produces a simple json object in
``/run/cloud-init/instance-data.json`` which represents standardized and
versioned representation of the metadata it consumes during initial boot. The
intent is to provide the following benefits to users or scripts on any system
deployed with cloud-init:

* simple static object to query to obtain a instance's metadata
* speed: avoid costly network transactions for metadata that is already cached
  on the filesytem
* reduce need to recrawl metadata services for static metadata that is already
  cached
* leverage cloud-init's best practices for crawling cloud-metadata services
* avoid rolling unique metadata crawlers on each cloud platform to get
  metadata configuration values

Cloud-init stores any instance data processed in the following files:

* ``/run/cloud-init/instance-data.json``: world-readable json containing
  standardized keys, sensitive keys redacted
* ``/run/cloud-init/instance-data-sensitive.json``: root-readable unredacted
  json blob
* ``/var/lib/cloud/instance/user-data.txt``: root-readable sensitive raw
  userdata
* ``/var/lib/cloud/instance/vendor-data.txt``: root-readable sensitive raw
  vendordata

Cloud-init redacts any security sensitive content from instance-data.json,
stores ``/run/cloud-init/instance-data.json`` as a world-readable json file.
Because user-data and vendor-data can contain passwords both of these files
are readonly for *root* as well. The *root* user can also read
``/run/cloud-init/instance-data-sensitive.json`` which is all instance data
from instance-data.json as well as unredacted sensitive content.


Format of instance-data.json
============================

The instance-data.json and instance-data-sensitive.json files are well-formed
JSON and record the set of keys and values for any metadata processed by
cloud-init. Cloud-init standardizes the format for this content so that it
can be generalized across different cloud platforms.

There are three basic top-level keys:

* **base64_encoded_keys**: A list of forward-slash delimited key paths into
  the instance-data.json object whose value is base64encoded for json
  compatibility. Values at these paths should be decoded to get the original
  value.

* **sensitive_keys**: A list of forward-slash delimited key paths into
  the instance-data.json object whose value is considered by the datasource as
  'security sensitive'. Only the keys listed here will be redacted from
  instance-data.json for non-root users.

* **ds**: Datasource-specific metadata crawled for the specific cloud
  platform. It should closely represent the structure of the cloud metadata
  crawled. The structure of content and details provided are entirely
  cloud-dependent. Mileage will vary depending on what the cloud exposes.
  The content exposed under the 'ds' key is currently **experimental** and
  expected to change slightly in the upcoming cloud-init release.

* **v1**: Standardized cloud-init metadata keys, these keys are guaranteed to
  exist on all cloud platforms. They will also retain their current behavior
  and format and will be carried forward even if cloud-init introduces a new
  version of standardized keys with **v2**.

The standardized keys present:

+----------------------+-----------------------------------------------+-----------------------------------+
|  Key path            | Description                                   | Examples                          |
+======================+===============================================+===================================+
| v1._beta_keys        | List of standardized keys still in 'beta'.    | [subplatform]                     |
|                      | The format, intent or presence of these keys  |                                   |
|                      | can change. Do not consider them              |                                   |
|                      | production-ready.                             |                                   |
+----------------------+-----------------------------------------------+-----------------------------------+
| v1.cloud_name        | Where possible this will indicate the 'name'  | aws, openstack, azure,            |
|                      | of the cloud this system is running on.  This | configdrive, nocloud,             |
|                      | is specifically different than the 'platform' | ovf, etc.                         |
|                      | below.  As an example, the name of Amazon Web |                                   |
|                      | Services is 'aws' while the platform is 'ec2'.|                                   |
|                      |                                               |                                   |
|                      | If no specific name is determinable or        |                                   |
|                      | provided in meta-data, then this field may    |                                   |
|                      | contain the same content as 'platform'.       |                                   |
+----------------------+-----------------------------------------------+-----------------------------------+
| v1.instance_id       | Unique instance_id allocated by the cloud     | i-<somehash>                      |
+----------------------+-----------------------------------------------+-----------------------------------+
| v1.local_hostname    | The internal or local hostname of the system  | ip-10-41-41-70,                   |
|                      |                                               | <user-provided-hostname>          |
+----------------------+-----------------------------------------------+-----------------------------------+
| v1.platform          | An attempt to identify the cloud platform     | ec2, openstack, lxd, gce          |
|                      | instance that the system is running on.       | nocloud, ovf                      |
+----------------------+-----------------------------------------------+-----------------------------------+
| v1.subplatform       | Additional platform details describing the    | metadata (http://168.254.169.254),|
|                      | specific source or type of metadata used.     | seed-dir (/path/to/seed-dir/),    |
|                      | The format of subplatform will be:            | config-disk (/dev/cd0),           |
|                      | <subplatform_type> (<url_file_or_dev_path>)   | configdrive (/dev/sr0)            |
+----------------------+-----------------------------------------------+-----------------------------------+
| v1.public_ssh_keys   | A list of  ssh keys provided to the instance  | ['ssh-rsa AA...', ...]            |
|                      | by the datasource metadata.                   |                                   |
+----------------------+-----------------------------------------------+-----------------------------------+
| v1.region            | The physical region/datacenter in which the   | us-east-2                         |
|                      | instance is deployed                          |                                   |
+----------------------+-----------------------------------------------+-----------------------------------+
| v1.availability_zone | The physical availability zone in which the   | us-east-2b, nova, null            |
|                      | instance is deployed                          |                                   |
+----------------------+-----------------------------------------------+-----------------------------------+


Below is an example of ``/run/cloud-init/instance_data.json`` on an EC2
instance:

.. sourcecode:: json

  {
   "base64_encoded_keys": [],
   "ds": {
    "_doc": "EXPERIMENTAL: The structure and format of content scoped under the 'ds' key may change in subsequent releases of cloud-init.",
    "_metadata_api_version": "2016-09-02",
    "dynamic": {
     "instance-identity": {
      "document": {
       "accountId": "437526006925",
       "architecture": "x86_64",
       "availabilityZone": "us-east-2b",
       "billingProducts": null,
       "devpayProductCodes": null,
       "imageId": "ami-079638aae7046bdd2",
       "instanceId": "i-075f088c72ad3271c",
       "instanceType": "t2.micro",
       "kernelId": null,
       "marketplaceProductCodes": null,
       "pendingTime": "2018-10-05T20:10:43Z",
       "privateIp": "10.41.41.95",
       "ramdiskId": null,
       "region": "us-east-2",
       "version": "2017-09-30"
      },
      "pkcs7": [
       "MIAGCSqGSIb3DQEHAqCAMIACAQExCzAJBgUrDgMCGgUAMIAGCSqGSIb3DQEHAaCAJIAEggHbewog",
       "ICJkZXZwYXlQcm9kdWN0Q29kZXMiIDogbnVsbCwKICAibWFya2V0cGxhY2VQcm9kdWN0Q29kZXMi",
       "IDogbnVsbCwKICAicHJpdmF0ZUlwIiA6ICIxMC40MS40MS45NSIsCiAgInZlcnNpb24iIDogIjIw",
       "MTctMDktMzAiLAogICJpbnN0YW5jZUlkIiA6ICJpLTA3NWYwODhjNzJhZDMyNzFjIiwKICAiYmls",
       "bGluZ1Byb2R1Y3RzIiA6IG51bGwsCiAgImluc3RhbmNlVHlwZSIgOiAidDIubWljcm8iLAogICJh",
       "Y2NvdW50SWQiIDogIjQzNzUyNjAwNjkyNSIsCiAgImF2YWlsYWJpbGl0eVpvbmUiIDogInVzLWVh",
       "c3QtMmIiLAogICJrZXJuZWxJZCIgOiBudWxsLAogICJyYW1kaXNrSWQiIDogbnVsbCwKICAiYXJj",
       "aGl0ZWN0dXJlIiA6ICJ4ODZfNjQiLAogICJpbWFnZUlkIiA6ICJhbWktMDc5NjM4YWFlNzA0NmJk",
       "ZDIiLAogICJwZW5kaW5nVGltZSIgOiAiMjAxOC0xMC0wNVQyMDoxMDo0M1oiLAogICJyZWdpb24i",
       "IDogInVzLWVhc3QtMiIKfQAAAAAAADGCARcwggETAgEBMGkwXDELMAkGA1UEBhMCVVMxGTAXBgNV",
       "BAgTEFdhc2hpbmd0b24gU3RhdGUxEDAOBgNVBAcTB1NlYXR0bGUxIDAeBgNVBAoTF0FtYXpvbiBX",
       "ZWIgU2VydmljZXMgTExDAgkAlrpI2eVeGmcwCQYFKw4DAhoFAKBdMBgGCSqGSIb3DQEJAzELBgkq",
       "hkiG9w0BBwEwHAYJKoZIhvcNAQkFMQ8XDTE4MTAwNTIwMTA0OFowIwYJKoZIhvcNAQkEMRYEFK0k",
       "Tz6n1A8/zU1AzFj0riNQORw2MAkGByqGSM44BAMELjAsAhRNrr174y98grPBVXUforN/6wZp8AIU",
       "JLZBkrB2GJA8A4WJ1okq++jSrBIAAAAAAAA="
      ],
      "rsa2048": [
       "MIAGCSqGSIb3DQEHAqCAMIACAQExDzANBglghkgBZQMEAgEFADCABgkqhkiG9w0BBwGggCSABIIB",
       "23sKICAiZGV2cGF5UHJvZHVjdENvZGVzIiA6IG51bGwsCiAgIm1hcmtldHBsYWNlUHJvZHVjdENv",
       "ZGVzIiA6IG51bGwsCiAgInByaXZhdGVJcCIgOiAiMTAuNDEuNDEuOTUiLAogICJ2ZXJzaW9uIiA6",
       "ICIyMDE3LTA5LTMwIiwKICAiaW5zdGFuY2VJZCIgOiAiaS0wNzVmMDg4YzcyYWQzMjcxYyIsCiAg",
       "ImJpbGxpbmdQcm9kdWN0cyIgOiBudWxsLAogICJpbnN0YW5jZVR5cGUiIDogInQyLm1pY3JvIiwK",
       "ICAiYWNjb3VudElkIiA6ICI0Mzc1MjYwMDY5MjUiLAogICJhdmFpbGFiaWxpdHlab25lIiA6ICJ1",
       "cy1lYXN0LTJiIiwKICAia2VybmVsSWQiIDogbnVsbCwKICAicmFtZGlza0lkIiA6IG51bGwsCiAg",
       "ImFyY2hpdGVjdHVyZSIgOiAieDg2XzY0IiwKICAiaW1hZ2VJZCIgOiAiYW1pLTA3OTYzOGFhZTcw",
       "NDZiZGQyIiwKICAicGVuZGluZ1RpbWUiIDogIjIwMTgtMTAtMDVUMjA6MTA6NDNaIiwKICAicmVn",
       "aW9uIiA6ICJ1cy1lYXN0LTIiCn0AAAAAAAAxggH/MIIB+wIBATBpMFwxCzAJBgNVBAYTAlVTMRkw",
       "FwYDVQQIExBXYXNoaW5ndG9uIFN0YXRlMRAwDgYDVQQHEwdTZWF0dGxlMSAwHgYDVQQKExdBbWF6",
       "b24gV2ViIFNlcnZpY2VzIExMQwIJAM07oeX4xevdMA0GCWCGSAFlAwQCAQUAoGkwGAYJKoZIhvcN",
       "AQkDMQsGCSqGSIb3DQEHATAcBgkqhkiG9w0BCQUxDxcNMTgxMDA1MjAxMDQ4WjAvBgkqhkiG9w0B",
       "CQQxIgQgkYz0pZk3zJKBi4KP4egeOKJl/UYwu5UdE7id74pmPwMwDQYJKoZIhvcNAQEBBQAEggEA",
       "dC3uIGGNul1OC1mJKSH3XoBWsYH20J/xhIdftYBoXHGf2BSFsrs9ZscXd2rKAKea4pSPOZEYMXgz",
       "lPuT7W0WU89N3ZKviy/ReMSRjmI/jJmsY1lea6mlgcsJXreBXFMYucZvyeWGHdnCjamoKWXkmZlM",
       "mSB1gshWy8Y7DzoKviYPQZi5aI54XK2Upt4kGme1tH1NI2Cq+hM4K+adxTbNhS3uzvWaWzMklUuU",
       "QHX2GMmjAVRVc8vnA8IAsBCJJp+gFgYzi09IK+cwNgCFFPADoG6jbMHHf4sLB3MUGpiA+G9JlCnM",
       "fmkjI2pNRB8spc0k4UG4egqLrqCz67WuK38tjwAAAAAAAA=="
      ],
      "signature": [
       "Tsw6h+V3WnxrNVSXBYIOs1V4j95YR1mLPPH45XnhX0/Ei3waJqf7/7EEKGYP1Cr4PTYEULtZ7Mvf",
       "+xJpM50Ivs2bdF7o0c4vnplRWe3f06NI9pv50dr110j/wNzP4MZ1pLhJCqubQOaaBTF3LFutgRrt",
       "r4B0mN3p7EcqD8G+ll0="
      ]
     }
    },
    "meta-data": {
     "ami-id": "ami-079638aae7046bdd2",
     "ami-launch-index": "0",
     "ami-manifest-path": "(unknown)",
     "block-device-mapping": {
      "ami": "/dev/sda1",
      "ephemeral0": "sdb",
      "ephemeral1": "sdc",
      "root": "/dev/sda1"
     },
     "hostname": "ip-10-41-41-95.us-east-2.compute.internal",
     "instance-action": "none",
     "instance-id": "i-075f088c72ad3271c",
     "instance-type": "t2.micro",
     "local-hostname": "ip-10-41-41-95.us-east-2.compute.internal",
     "local-ipv4": "10.41.41.95",
     "mac": "06:74:8f:39:cd:a6",
     "metrics": {
      "vhostmd": "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
     },
     "network": {
      "interfaces": {
       "macs": {
	"06:74:8f:39:cd:a6": {
	 "device-number": "0",
	 "interface-id": "eni-052058bbd7831eaae",
	 "ipv4-associations": {
	  "18.218.221.122": "10.41.41.95"
	 },
	 "local-hostname": "ip-10-41-41-95.us-east-2.compute.internal",
	 "local-ipv4s": "10.41.41.95",
	 "mac": "06:74:8f:39:cd:a6",
	 "owner-id": "437526006925",
	 "public-hostname": "ec2-18-218-221-122.us-east-2.compute.amazonaws.com",
	 "public-ipv4s": "18.218.221.122",
	 "security-group-ids": "sg-828247e9",
	 "security-groups": "Cloud-init integration test secgroup",
	 "subnet-id": "subnet-282f3053",
	 "subnet-ipv4-cidr-block": "10.41.41.0/24",
	 "subnet-ipv6-cidr-blocks": "2600:1f16:b80:ad00::/64",
	 "vpc-id": "vpc-252ef24d",
	 "vpc-ipv4-cidr-block": "10.41.0.0/16",
	 "vpc-ipv4-cidr-blocks": "10.41.0.0/16",
	 "vpc-ipv6-cidr-blocks": "2600:1f16:b80:ad00::/56"
	}
       }
      }
     },
     "placement": {
      "availability-zone": "us-east-2b"
     },
     "profile": "default-hvm",
     "public-hostname": "ec2-18-218-221-122.us-east-2.compute.amazonaws.com",
     "public-ipv4": "18.218.221.122",
     "public-keys": {
      "cloud-init-integration": [
       "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDSL7uWGj8cgWyIOaspgKdVy0cKJ+UTjfv7jBOjG2H/GN8bJVXy72XAvnhM0dUM+CCs8FOf0YlPX+Frvz2hKInrmRhZVwRSL129PasD12MlI3l44u6IwS1o/W86Q+tkQYEljtqDOo0a+cOsaZkvUNzUyEXUwz/lmYa6G4hMKZH4NBj7nbAAF96wsMCoyNwbWryBnDYUr6wMbjRR1J9Pw7Xh7WRC73wy4Va2YuOgbD3V/5ZrFPLbWZW/7TFXVrql04QVbyei4aiFR5n//GvoqwQDNe58LmbzX/xvxyKJYdny2zXmdAhMxbrpFQsfpkJ9E/H5w0yOdSvnWbUoG5xNGoOB cloud-init-integration"
      ]
     },
     "reservation-id": "r-0594a20e31f6cfe46",
     "security-groups": "Cloud-init integration test secgroup",
     "services": {
      "domain": "amazonaws.com",
      "partition": "aws"
     }
    }
   },
   "sensitive_keys": [],
   "v1": {
    "_beta_keys": [
     "subplatform"
    ],
    "availability-zone": "us-east-2b",
    "availability_zone": "us-east-2b",
    "cloud_name": "aws",
    "instance_id": "i-075f088c72ad3271c",
    "local_hostname": "ip-10-41-41-95",
    "platform": "ec2",
    "public_ssh_keys": [
     "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDSL7uWGj8cgWyIOaspgKdVy0cKJ+UTjfv7jBOjG2H/GN8bJVXy72XAvnhM0dUM+CCs8FOf0YlPX+Frvz2hKInrmRhZVwRSL129PasD12MlI3l44u6IwS1o/W86Q+tkQYEljtqDOo0a+cOsaZkvUNzUyEXUwz/lmYa6G4hMKZH4NBj7nbAAF96wsMCoyNwbWryBnDYUr6wMbjRR1J9Pw7Xh7WRC73wy4Va2YuOgbD3V/5ZrFPLbWZW/7TFXVrql04QVbyei4aiFR5n//GvoqwQDNe58LmbzX/xvxyKJYdny2zXmdAhMxbrpFQsfpkJ9E/H5w0yOdSvnWbUoG5xNGoOB cloud-init-integration"
    ],
    "region": "us-east-2",
    "subplatform": "metadata (http://169.254.169.254)"
   }
  }


Using instance-data
===================

As of cloud-init v. 18.4, any variables present in
``/run/cloud-init/instance-data.json`` can be used in:

* User-data scripts
* Cloud config data
* Command line interface via **cloud-init query** or
  **cloud-init devel render**

Many clouds allow users to provide user-data to an instance at
the time the instance is launched. Cloud-init supports a number of
:ref:`user_data_formats`.

Both user-data scripts and **#cloud-config** data support jinja template
rendering.
When the first line of the provided user-data begins with,
**## template: jinja** cloud-init will use jinja to render that file.
Any instance-data-sensitive.json variables are surfaced as dot-delimited
jinja template variables because cloud-config modules are run as 'root'
user.


Below are some examples of providing these types of user-data:

* Cloud config calling home with the ec2 public hostname and avaliability-zone

.. code-block:: shell-session

  ## template: jinja
  #cloud-config
  runcmd:
      - echo 'EC2 public hostname allocated to instance: {{
        ds.meta_data.public_hostname }}' > /tmp/instance_metadata
      - echo 'EC2 avaiability zone: {{ v1.availability_zone }}' >>
        /tmp/instance_metadata
      - curl -X POST -d '{"hostname": "{{ds.meta_data.public_hostname }}",
        "availability-zone": "{{ v1.availability_zone }}"}'
        https://example.com

* Custom user-data script performing different operations based on region

.. code-block:: shell-session

   ## template: jinja
   #!/bin/bash
   {% if v1.region == 'us-east-2' -%}
   echo 'Installing custom proxies for {{ v1.region }}
   sudo apt-get install my-xtra-fast-stack
   {%- endif %}
   ...

.. note::
  Trying to reference jinja variables that don't exist in
  instance-data.json will result in warnings in ``/var/log/cloud-init.log``
  and the following string in your rendered user-data:
  ``CI_MISSING_JINJA_VAR/<your_varname>``.

Cloud-init also surfaces a commandline tool **cloud-init query** which can
assist developers or scripts with obtaining instance metadata easily. See
:ref:`cli_query` for more information.

To cut down on keystrokes on the command line, cloud-init also provides
top-level key aliases for any standardized ``v#`` keys present. The preceding
``v1`` is not required of ``v1.var_name`` These aliases will represent the
value of the highest versioned standard key. For example, ``cloud_name``
value will be ``v2.cloud_name`` if both ``v1`` and ``v2`` keys are present in
instance-data.json.
The **query** command also publishes ``userdata`` and ``vendordata`` keys to
the root user which will contain the decoded user and vendor data provided to
this instance. Non-root users referencing userdata or vendordata keys will
see only redacted values.

.. code-block:: shell-session

 # List all top-level instance-data keys available
 % cloud-init query --list-keys

 # Find your EC2 ami-id
 % cloud-init query ds.metadata.ami_id

 # Format your cloud_name and region using jinja template syntax
 % cloud-init query --format 'cloud: {{ v1.cloud_name }} myregion: {{
 % v1.region }}'

.. note::
  To save time designing a user-data template for a specific cloud's
  instance-data.json, use the 'render' cloud-init command on an
  instance booted on your favorite cloud. See :ref:`cli_devel` for more
  information.

.. vi: textwidth=78

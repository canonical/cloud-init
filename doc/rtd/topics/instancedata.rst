.. _instance_metadata:

*****************
Instance Metadata
*****************

What is instance data?
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

* **merged_cfg**: Merged cloud-init 'system_config' from `/etc/cloud/cloud.cfg`
  and  `/etc/cloud/cloud-cfg.d`. Values under this key could contain sensitive
  information such as passwords, so it is included in the **sensitive-keys**
  list which is only readable by root.

* **ds**: Datasource-specific metadata crawled for the specific cloud
  platform. It should closely represent the structure of the cloud metadata
  crawled. The structure of content and details provided are entirely
  cloud-dependent. Mileage will vary depending on what the cloud exposes.
  The content exposed under the 'ds' key is currently **experimental** and
  expected to change slightly in the upcoming cloud-init release.

* **sys_info**: Information about the underlying os, python, architecture and
  kernel. This represents the data collected by `cloudinit.util.system_info`.

* **v1**: Standardized cloud-init metadata keys, these keys are guaranteed to
  exist on all cloud platforms. They will also retain their current behavior
  and format and will be carried forward even if cloud-init introduces a new
  version of standardized keys with **v2**.

The standardized keys present:

v1._beta_keys
-------------
List of standardized keys still in 'beta'. The format, intent or presence of
these keys can change. Do not consider them production-ready.

Example output:

- [subplatform]

v1.cloud_name
-------------
Where possible this will indicate the 'name' of the cloud the system is running
on. This is different than the 'platform' item. For example, the cloud name of
Amazon Web Services is 'aws', while the platform is 'ec2'.

If determining a specific name is not possible or provided in meta-data, then
this filed may contain the same content as 'platform'.

Example output:

- aws
- openstack
- azure
- configdrive
- nocloud
- ovf

v1.distro, v1.distro_version, v1.distro_release
-----------------------------------------------
This shall be the distro name, version and release as determined by
`cloudinit.util.get_linux_distro`.

Example output:

- alpine, 3.12.0, ''
- centos, 7.5, core
- debian, 9, stretch
- freebsd, 12.0-release-p10,
- opensuse, 42.3, x86_64
- opensuse-tumbleweed, 20180920, x86_64
- redhat, 7.5, 'maipo'
- sles, 12.3, x86_64
- ubuntu, 20.04, focal

v1.instance_id
--------------
Unique instance_id allocated by the cloud.

Examples output:

- i-<hash>

v1.kernel_release
-----------------
This shall be the running kernel `uname -r`

Example output:

- 5.3.0-1010-aws

v1.local_hostname
-----------------
The internal or local hostname of the system.

Examples output:

- ip-10-41-41-70
- <user-provided-hostname>

v1.machine
----------
This shall be the running cpu machine architecture `uname -m`

Example output:

- x86_64
- i686
- ppc64le
- s390x

v1.platform
-------------
An attempt to identify the cloud platfrom instance that the system is running
on.

Examples output:

- ec2
- openstack
- lxd
- gce
- nocloud
- ovf

v1.subplatform
--------------
Additional platform details describing the specific source or type of metadata
used. The format of subplatform will be:

``<subplatform_type> (<url_file_or_dev_path>)``

Examples output:

- metadata (http://168.254.169.254)
- seed-dir (/path/to/seed-dir/)
- config-disk (/dev/cd0)
- configdrive (/dev/sr0)

v1.public_ssh_keys
------------------
A list of SSH keys provided to the instance by the datasource metadata.

Examples output:

- ['ssh-rsa AA...', ...]

v1.python_version
-----------------
The version of python that is running cloud-init as determined by
`cloudinit.util.system_info`

Example output:

- 3.7.6

v1.region
---------
The physical region/data center in which the instance is deployed.

Examples output:

- us-east-2

v1.availability_zone
--------------------
The physical availability zone in which the instance is deployed.

Examples output:

- us-east-2b
- nova
- null

Example Output
--------------

Below is an example of ``/run/cloud-init/instance-data-sensitive.json`` on an
EC2 instance:

.. sourcecode:: json

  {
   "_beta_keys": [
    "subplatform"
   ],
   "availability_zone": "us-east-1b",
   "base64_encoded_keys": [],
   "merged_cfg": {
    "_doc": "Merged cloud-init system config from /etc/cloud/cloud.cfg and /etc/cloud/cloud.cfg.d/",
    "_log": [
     "[loggers]\nkeys=root,cloudinit\n\n[handlers]\nkeys=consoleHandler,cloudLogHandler\n\n[formatters]\nkeys=simpleFormatter,arg0Formatter\n\n[logger_root]\nlevel=DEBUG\nhandlers=consoleHandler,cloudLogHandler\n\n[logger_cloudinit]\nlevel=DEBUG\nqualname=cloudinit\nhandlers=\npropagate=1\n\n[handler_consoleHandler]\nclass=StreamHandler\nlevel=WARNING\nformatter=arg0Formatter\nargs=(sys.stderr,)\n\n[formatter_arg0Formatter]\nformat=%(asctime)s - %(filename)s[%(levelname)s]: %(message)s\n\n[formatter_simpleFormatter]\nformat=[CLOUDINIT] %(filename)s[%(levelname)s]: %(message)s\n",
     "[handler_cloudLogHandler]\nclass=FileHandler\nlevel=DEBUG\nformatter=arg0Formatter\nargs=('/var/log/cloud-init.log',)\n",
     "[handler_cloudLogHandler]\nclass=handlers.SysLogHandler\nlevel=DEBUG\nformatter=simpleFormatter\nargs=(\"/dev/log\", handlers.SysLogHandler.LOG_USER)\n"
    ],
    "cloud_config_modules": [
     "emit_upstart",
     "snap",
     "ssh-import-id",
     "locale",
     "set-passwords",
     "grub-dpkg",
     "apt-pipelining",
     "apt-configure",
     "ubuntu-advantage",
     "ntp",
     "timezone",
     "disable-ec2-metadata",
     "runcmd",
     "byobu"
    ],
    "cloud_final_modules": [
     "package-update-upgrade-install",
     "fan",
     "landscape",
     "lxd",
     "ubuntu-drivers",
     "puppet",
     "chef",
     "mcollective",
     "salt-minion",
     "rightscale_userdata",
     "scripts-vendor",
     "scripts-per-once",
     "scripts-per-boot",
     "scripts-per-instance",
     "scripts-user",
     "ssh-authkey-fingerprints",
     "keys-to-console",
     "phone-home",
     "final-message",
     "power-state-change"
    ],
    "cloud_init_modules": [
     "migrator",
     "seed_random",
     "bootcmd",
     "write-files",
     "growpart",
     "resizefs",
     "disk_setup",
     "mounts",
     "set_hostname",
     "update_hostname",
     "update_etc_hosts",
     "ca-certs",
     "rsyslog",
     "users-groups",
     "ssh"
    ],
    "datasource_list": [
     "Ec2",
     "None"
    ],
    "def_log_file": "/var/log/cloud-init.log",
    "disable_root": true,
    "log_cfgs": [
     [
      "[loggers]\nkeys=root,cloudinit\n\n[handlers]\nkeys=consoleHandler,cloudLogHandler\n\n[formatters]\nkeys=simpleFormatter,arg0Formatter\n\n[logger_root]\nlevel=DEBUG\nhandlers=consoleHandler,cloudLogHandler\n\n[logger_cloudinit]\nlevel=DEBUG\nqualname=cloudinit\nhandlers=\npropagate=1\n\n[handler_consoleHandler]\nclass=StreamHandler\nlevel=WARNING\nformatter=arg0Formatter\nargs=(sys.stderr,)\n\n[formatter_arg0Formatter]\nformat=%(asctime)s - %(filename)s[%(levelname)s]: %(message)s\n\n[formatter_simpleFormatter]\nformat=[CLOUDINIT] %(filename)s[%(levelname)s]: %(message)s\n",
      "[handler_cloudLogHandler]\nclass=FileHandler\nlevel=DEBUG\nformatter=arg0Formatter\nargs=('/var/log/cloud-init.log',)\n"
     ]
    ],
    "output": {
     "all": "| tee -a /var/log/cloud-init-output.log"
    },
    "preserve_hostname": false,
    "syslog_fix_perms": [
     "syslog:adm",
     "root:adm",
     "root:wheel",
     "root:root"
    ],
    "users": [
     "default"
    ],
    "vendor_data": {
     "enabled": true,
     "prefix": []
    }
   },
   "cloud_name": "aws",
   "distro": "ubuntu",
   "distro_release": "focal",
   "distro_version": "20.04",
   "ds": {
    "_doc": "EXPERIMENTAL: The structure and format of content scoped under the 'ds' key may change in subsequent releases of cloud-init.",
    "_metadata_api_version": "2016-09-02",
    "dynamic": {
     "instance_identity": {
      "document": {
       "accountId": "329910648901",
       "architecture": "x86_64",
       "availabilityZone": "us-east-1b",
       "billingProducts": null,
       "devpayProductCodes": null,
       "imageId": "ami-02e8aa396f8be3b6d",
       "instanceId": "i-0929128ff2f73a2f1",
       "instanceType": "t2.micro",
       "kernelId": null,
       "marketplaceProductCodes": null,
       "pendingTime": "2020-02-27T20:46:18Z",
       "privateIp": "172.31.81.43",
       "ramdiskId": null,
       "region": "us-east-1",
       "version": "2017-09-30"
      },
      "pkcs7": [
       "MIAGCSqGSIb3DQ...",
       "REDACTED",
       "AhQUgq0iPWqPTVnT96tZE6L1XjjLHQAAAAAAAA=="
      ],
      "rsa2048": [
       "MIAGCSqGSIb...",
       "REDACTED",
       "clYQvuE45xXm7Yreg3QtQbrP//owl1eZHj6s350AAAAAAAA="
      ],
      "signature": [
       "dA+QV+LLCWCRNddnrKleYmh2GvYo+t8urDkdgmDSsPi",
       "REDACTED",
       "kDT4ygyJLFkd3b4qjAs="
      ]
     }
    },
    "meta_data": {
     "ami_id": "ami-02e8aa396f8be3b6d",
     "ami_launch_index": "0",
     "ami_manifest_path": "(unknown)",
     "block_device_mapping": {
      "ami": "/dev/sda1",
      "root": "/dev/sda1"
     },
     "hostname": "ip-172-31-81-43.ec2.internal",
     "instance_action": "none",
     "instance_id": "i-0929128ff2f73a2f1",
     "instance_type": "t2.micro",
     "local_hostname": "ip-172-31-81-43.ec2.internal",
     "local_ipv4": "172.31.81.43",
     "mac": "12:7e:c9:93:29:af",
     "metrics": {
      "vhostmd": "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
     },
     "network": {
      "interfaces": {
       "macs": {
        "12:7e:c9:93:29:af": {
         "device_number": "0",
         "interface_id": "eni-0c07a0474339b801d",
         "ipv4_associations": {
          "3.89.187.177": "172.31.81.43"
         },
         "local_hostname": "ip-172-31-81-43.ec2.internal",
         "local_ipv4s": "172.31.81.43",
         "mac": "12:7e:c9:93:29:af",
         "owner_id": "329910648901",
         "public_hostname": "ec2-3-89-187-177.compute-1.amazonaws.com",
         "public_ipv4s": "3.89.187.177",
         "security_group_ids": "sg-0100038b68aa79986",
         "security_groups": "launch-wizard-3",
         "subnet_id": "subnet-04e2d12a",
         "subnet_ipv4_cidr_block": "172.31.80.0/20",
         "vpc_id": "vpc-210b4b5b",
         "vpc_ipv4_cidr_block": "172.31.0.0/16",
         "vpc_ipv4_cidr_blocks": "172.31.0.0/16"
        }
       }
      }
     },
     "placement": {
      "availability_zone": "us-east-1b"
     },
     "profile": "default-hvm",
     "public_hostname": "ec2-3-89-187-177.compute-1.amazonaws.com",
     "public_ipv4": "3.89.187.177",
     "reservation_id": "r-0c481643d15766a02",
     "security_groups": "launch-wizard-3",
     "services": {
      "domain": "amazonaws.com",
      "partition": "aws"
     }
    }
   },
   "instance_id": "i-0929128ff2f73a2f1",
   "kernel_release": "5.3.0-1010-aws",
   "local_hostname": "ip-172-31-81-43",
   "machine": "x86_64",
   "platform": "ec2",
   "public_ssh_keys": [],
   "python_version": "3.7.6",
   "region": "us-east-1",
   "sensitive_keys": [],
   "subplatform": "metadata (http://169.254.169.254)",
   "sys_info": {
    "dist": [
     "ubuntu",
     "20.04",
     "focal"
    ],
    "platform": "Linux-5.3.0-1010-aws-x86_64-with-Ubuntu-20.04-focal",
    "python": "3.7.6",
    "release": "5.3.0-1010-aws",
    "system": "Linux",
    "uname": [
     "Linux",
     "ip-172-31-81-43",
     "5.3.0-1010-aws",
     "#11-Ubuntu SMP Thu Jan 16 07:59:32 UTC 2020",
     "x86_64",
     "x86_64"
    ],
    "variant": "ubuntu"
   },
   "system_platform": "Linux-5.3.0-1010-aws-x86_64-with-Ubuntu-20.04-focal",
   "userdata": "#cloud-config\nssh_import_id: [<my-launchpad-id>]\n...",
   "v1": {
    "_beta_keys": [
     "subplatform"
    ],
    "availability_zone": "us-east-1b",
    "cloud_name": "aws",
    "distro": "ubuntu",
    "distro_release": "focal",
    "distro_version": "20.04",
    "instance_id": "i-0929128ff2f73a2f1",
    "kernel": "5.3.0-1010-aws",
    "local_hostname": "ip-172-31-81-43",
    "machine": "x86_64",
    "platform": "ec2",
    "public_ssh_keys": [],
    "python": "3.7.6",
    "region": "us-east-1",
    "subplatform": "metadata (http://169.254.169.254)",
    "system_platform": "Linux-5.3.0-1010-aws-x86_64-with-Ubuntu-20.04-focal",
    "variant": "ubuntu"
   },
   "variant": "ubuntu",
   "vendordata": ""
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

* Cloud config calling home with the ec2 public hostname and availability-zone

.. code-block:: yaml

  ## template: jinja
  #cloud-config
  runcmd:
      - echo 'EC2 public hostname allocated to instance: {{
        ds.meta_data.public_hostname }}' > /tmp/instance_metadata
      - echo 'EC2 availability zone: {{ v1.availability_zone }}' >>
        /tmp/instance_metadata
      - curl -X POST -d '{"hostname": "{{ds.meta_data.public_hostname }}",
        "availability-zone": "{{ v1.availability_zone }}"}'
        https://example.com

* Custom user-data script performing different operations based on region

.. code-block:: jinja

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

Cloud-init also surfaces a command line tool **cloud-init query** which can
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

 # Locally test that your template userdata provided to the vm was rendered as
 # intended.
 % cloud-init query --format "$(sudo cloud-init query userdata)"

 # The --format command renders jinja templates, this can also be used
 # to develop and test jinja template constructs
 % cat > test-templating.yaml <<EOF
   {% for val in ds.meta_data.keys() %}
   - {{ val }}
   {% endfor %}
   EOF
 % cloud-init query --format="$( cat test-templating.yaml )"
 - instance_id
 - dsmode
 - local_hostname

.. note::
  To save time designing a user-data template for a specific cloud's
  instance-data.json, use the 'render' cloud-init command on an
  instance booted on your favorite cloud. See :ref:`cli_devel` for more
  information.

.. vi: textwidth=78

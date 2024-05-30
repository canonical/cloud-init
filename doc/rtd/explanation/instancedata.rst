.. _instance_metadata:


Instance metadata
*****************

.. toctree::
   :maxdepth: 1
   :hidden:

   kernel-command-line.rst

What is ``instance-data?``
==========================

Each cloud provider presents unique configuration metadata to a launched cloud
instance. ``Cloud-init`` crawls this metadata and then caches and exposes this
information as a standardised and versioned JSON object known as
``instance-data``. This ``instance-data`` may then be queried or later used
by ``cloud-init`` in templated configuration and scripts.

An example of a small subset of instance-data on a launched EC2 instance:

.. code-block:: json

   {
     "v1": {
       "cloud_name": "aws",
       "distro": "ubuntu",
       "distro_release": "jammy",
       "distro_version": "22.04",
       "instance_id": "i-06b5687b4d7b8595d",
       "machine": "x86_64",
       "platform": "ec2",
       "python_version": "3.10.4",
       "region": "us-east-2",
       "variant": "ubuntu"
     }
   }


Discovery
=========

One way to easily explore which ``instance-data`` variables are available on
your machine is to use the :ref:`cloud-init query<cli_query>` tool.
Warnings or exceptions will be raised on invalid ``instance-data`` keys,
paths or invalid syntax.

The :command:`query` command also publishes ``userdata`` and ``vendordata``
keys to the root user which will contain the decoded user and vendor data
provided to this instance. Non-root users referencing ``userdata`` or
``vendordata`` keys will see only redacted values.

.. note::
   To save time designing a user data template for a specific cloud's
   :file:`instance-data.json`, use the :command:`render` command on an
   instance booted on your favorite cloud. See :ref:`cli_devel` for more
   information.

.. _instancedata-Using:

Using ``instance-data``
=======================

``instance-data`` can be used in:

* :ref:`User data scripts<user_data_script>`.
* :ref:`Cloud-config data<user_data_formats>`.
* :ref:`Base configuration<configuration>`.
* Command line interface via :command:`cloud-init query` or
  :command:`cloud-init devel render`.

The aforementioned configuration sources support jinja template rendering.
When the first line of the provided configuration begins with
**## template: jinja**, ``cloud-init`` will use jinja to render that file.
Any ``instance-data`` variables are surfaced as jinja template variables.

.. note::
   Trying to reference jinja variables that don't exist in ``instance-data``
   will result in warnings in :file:`/var/log/cloud-init.log` and the following
   string in your rendered :file:`user-data`:
   ``CI_MISSING_JINJA_VAR/<your_varname>``.

Sensitive data such as user passwords may be contained in ``instance-data``.
``Cloud-init`` separates this sensitive data such that is it only readable by
root. In the case that a non-root user attempts to read sensitive
``instance-data``, they will receive redacted data or the same warnings and
text that occur if a variable does not exist.

Example: Cloud config with ``instance-data``
--------------------------------------------

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

Example: User data script with ``instance-data``
------------------------------------------------

.. code-block:: jinja

   ## template: jinja
   #!/bin/bash
   {% if v1.region == 'us-east-2' -%}
   echo 'Installing custom proxies for {{ v1.region }}'
   sudo apt-get install my-xtra-fast-stack
   {%- endif %}
   ...

Example: CLI discovery of ``instance-data``
-------------------------------------------

.. code-block:: shell-session

   # List all instance-data keys and values as root user
   $ sudo cloud-init query --all
   {...}

   # List all top-level instance-data keys available
   $ cloud-init query --list-keys

   # Introspect nested keys on an object
   $ cloud-init query -f "{{ds.keys()}}"
   dict_keys(['meta_data', '_doc'])

   # Failure to reference valid dot-delimited key path on a known top-level key
   $ cloud-init query v1.not_here
   ERROR: instance-data 'v1' has no 'not_here'

   # Test expected value using valid instance-data key path
   $ cloud-init query -f "My AMI: {{ds.meta_data.ami_id}}"
   My AMI: ami-0fecc35d3c8ba8d60

   # The --format command renders jinja templates, this can also be used
   # to develop and test jinja template constructs
   $ cat > test-templating.yaml <<EOF
     {% for val in ds.meta_data.keys() %}
     - {{ val }}
     {% endfor %}
     EOF
   $ cloud-init query --format="$( cat test-templating.yaml )"
   - instance_id
   - dsmode
   - local_hostname

Reference
=========

Storage locations
-----------------

* :file:`/run/cloud-init/instance-data.json`: world-readable JSON containing
  standardised keys, sensitive keys redacted.
* :file:`/run/cloud-init/instance-data-sensitive.json`: root-readable
  unredacted JSON blob.
* :file:`/run/cloud-init/combined-cloud-config.json`: root-readable
  unredacted JSON blob. Any meta-data, vendor-data and user-data overrides
  are applied to the :file:`/run/cloud-init/combined-cloud-config.json` config values.

:file:`instance-data.json` top level keys
-----------------------------------------

``base64_encoded_keys``
^^^^^^^^^^^^^^^^^^^^^^^

A list of forward-slash delimited key paths into the :file:`instance-data.json`
object whose value is base64encoded for JSON compatibility. Values at these
paths should be decoded to get the original value.

``features``
^^^^^^^^^^^^

A dictionary of feature name and boolean value pairs. A value of ``True`` means
the feature is enabled.


``sensitive_keys``
^^^^^^^^^^^^^^^^^^

A list of forward-slash delimited key paths into the :file:`instance-data.json`
object whose value is considered by the datasource as 'security sensitive'.
Only the keys listed here will be redacted from :file:`instance-data.json` for
non-root users.

``merged_cfg``
^^^^^^^^^^^^^^
Deprecated use ``merged_system_cfg`` instead.

``merged_system_cfg``
^^^^^^^^^^^^^^^^^^^^^

Merged ``cloud-init`` :ref:`base_config_reference` from
:file:`/etc/cloud/cloud.cfg` and :file:`/etc/cloud/cloud-cfg.d`. Values under
this key could contain sensitive information such as passwords, so it is
included in the ``sensitive-keys`` list which is only readable by root.

.. note::
   ``merged_system_cfg`` represents only the merged config from the underlying
   filesystem. These values can be overridden by meta-data, vendor-data or
   user-data. The fully merged cloud-config provided to a machine
   which accounts for any supplemental overrides is the file
   :file:`/run/cloud-init/combined-cloud-config.json`.

``ds``
^^^^^^

Datasource-specific metadata crawled for the specific cloud platform. It should
closely represent the structure of the cloud metadata crawled. The structure of
content and details provided are entirely cloud-dependent. Mileage will vary
depending on what the cloud exposes. The content exposed under the ``ds`` key
is currently **experimental** and expected to change slightly in the upcoming
``cloud-init`` release.

``sys_info``
^^^^^^^^^^^^

Information about the underlying OS, Python, architecture and kernel. This
represents the data collected by ``cloudinit.util.system_info``.

``system_info``
^^^^^^^^^^^^^^^

This is a cloud-init configuration key present in :file:`/etc/cloud/cloud.cfg`
which describes cloud-init's configured `default_user`, `distro`, `network`
renderers, and `paths` that cloud-init will use. Not to be confused with the
underlying host ``sys_info`` key above.

``v1``
^^^^^^

Standardised ``cloud-init`` metadata keys, these keys are guaranteed to exist
on all cloud platforms. They will also retain their current behaviour and
format, and will be carried forward even if ``cloud-init`` introduces a new
version of standardised keys with ``v2``.

To cut down on keystrokes on the command line, ``cloud-init`` also provides
top-level key aliases for any standardised ``v#`` keys present. The preceding
``v1`` is not required of ``v1.var_name`` These aliases will represent the
value of the highest versioned standard key. For example, ``cloud_name``
value will be ``v2.cloud_name`` if both ``v1`` and ``v2`` keys are present in
:file:`instance-data.json`.

``Cloud-init`` also provides jinja-safe key aliases for any ``instance-data``
keys which contain jinja operator characters such as ``+``, ``-``, ``.``,
``/``, etc. Any jinja operator will be replaced with underscores in the
jinja-safe key alias. This allows for ``cloud-init`` templates to use aliased
variable references which allow for jinja's dot-notation reference such as
``{{ ds.v1_0.my_safe_key }}`` instead of ``{{ ds["v1.0"]["my/safe-key"] }}``.

Standardised :file:`instance-data.json` v1 keys
-----------------------------------------------

``v1._beta_keys``
^^^^^^^^^^^^^^^^^

List of standardised keys still in 'beta'. The format, intent or presence of
these keys can change. Do not consider them production-ready.

Example output:

  - [subplatform]

``v1.cloud_name``
^^^^^^^^^^^^^^^^^

Where possible this will indicate the 'name' of the cloud the system is running
on. This is different than the 'platform' item. For example, the cloud name of
Amazon Web Services is 'aws', while the platform is 'ec2'.

If determining a specific name is not possible or provided in
:file:`meta-data`, then this filed may contain the same content as 'platform'.

Example output:

  - aws
  - openstack
  - azure
  - configdrive
  - nocloud
  - ovf

``v1.distro``, ``v1.distro_version``, ``v1.distro_release``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

This shall be the distro name, version and release as determined by
``cloudinit.util.get_linux_distro``.

Example output:

  - alpine, 3.12.0, 'Alpine Linux v3.12'
  - centos, 7.5, core
  - debian, 9, stretch
  - freebsd, 12.0-release-p10,
  - opensuse, 42.3, x86_64
  - opensuse-tumbleweed, 20180920, x86_64
  - redhat, 7.5, 'maipo'
  - sles, 12.3, x86_64
  - ubuntu, 20.04, focal

``v1.instance_id``
^^^^^^^^^^^^^^^^^^

Unique ``instance_id`` allocated by the cloud.

Example output:

  - i-<hash>

``v1.kernel_release``
^^^^^^^^^^^^^^^^^^^^^

This shall be the running kernel ``uname -r``.

Example output:

  - 5.3.0-1010-aws

``v1.local_hostname``
^^^^^^^^^^^^^^^^^^^^^

The internal or local hostname of the system.

Example output:

  - ``ip-10-41-41-70``
  - ``<user-provided-hostname>``

``v1.machine``
^^^^^^^^^^^^^^

This shall be the running cpu machine architecture ``uname -m``.

Example output:

  - x86_64
  - i686
  - ppc64le
  - s390x

``v1.platform``
^^^^^^^^^^^^^^^

An attempt to identify the cloud platform instance that the system is running
on.

Example output:

  - ec2
  - openstack
  - lxd
  - gce
  - nocloud
  - ovf

``v1.subplatform``
^^^^^^^^^^^^^^^^^^

Additional platform details describing the specific source or type of metadata
used. The format of subplatform will be:

``<subplatform_type> (<url_file_or_dev_path>)``

Example output:

  - metadata (http://169.254.169.254)
  - seed-dir (/path/to/seed-dir/)
  - config-disk (/dev/cd0)
  - configdrive (/dev/sr0)

``v1.public_ssh_keys``
^^^^^^^^^^^^^^^^^^^^^^

A list of SSH keys provided to the instance by the datasource metadata.

Example output:

  - ['ssh-rsa AA...', ...]

``v1.python_version``
^^^^^^^^^^^^^^^^^^^^^

The version of Python that is running ``cloud-init`` as determined by
``cloudinit.util.system_info``.

Example output:

  - 3.7.6

``v1.region``
^^^^^^^^^^^^^

The physical region/data centre in which the instance is deployed.

Example output:

  - us-east-2

``v1.availability_zone``
^^^^^^^^^^^^^^^^^^^^^^^^

The physical availability zone in which the instance is deployed.

Example output:

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
    "_doc": "Merged cloud-init base config from /etc/cloud/cloud.cfg and /etc/cloud/cloud.cfg.d/",
    "_log": [
     "[loggers]\nkeys=root,cloudinit\n\n[handlers]\nkeys=consoleHandler,cloudLogHandler\n\n[formatters]\nkeys=simpleFormatter,arg0Formatter\n\n[logger_root]\nlevel=DEBUG\nhandlers=consoleHandler,cloudLogHandler\n\n[logger_cloudinit]\nlevel=DEBUG\nqualname=cloudinit\nhandlers=\npropagate=1\n\n[handler_consoleHandler]\nclass=StreamHandler\nlevel=WARNING\nformatter=arg0Formatter\nargs=(sys.stderr,)\n\n[formatter_arg0Formatter]\nformat=%(asctime)s - %(filename)s[%(levelname)s]: %(message)s\n\n[formatter_simpleFormatter]\nformat=[CLOUDINIT] %(filename)s[%(levelname)s]: %(message)s\n",
     "[handler_cloudLogHandler]\nclass=FileHandler\nlevel=DEBUG\nformatter=arg0Formatter\nargs=('/var/log/cloud-init.log',)\n",
     "[handler_cloudLogHandler]\nclass=handlers.SysLogHandler\nlevel=DEBUG\nformatter=simpleFormatter\nargs=(\"/dev/log\", handlers.SysLogHandler.LOG_USER)\n"
    ],
    "cloud_config_modules": [
     "snap",
     "ssh_import_id",
     "locale",
     "set_passwords",
     "grub_dpkg",
     "apt_pipelining",
     "apt_configure",
     "ubuntu_pro",
     "ntp",
     "timezone",
     "disable_ec2_metadata",
     "runcmd",
     "byobu"
    ],
    "cloud_final_modules": [
     "package_update_upgrade_install",
     "fan",
     "landscape",
     "lxd",
     "ubuntu_drivers",
     "puppet",
     "chef",
     "mcollective",
     "salt_minion",
     "scripts_vendor",
     "scripts_per_once",
     "scripts_per_boot",
     "scripts_per_instance",
     "scripts_user",
     "ssh_authkey_fingerprints",
     "keys_to_console",
     "phone_home",
     "final_message",
     "power_state_change"
    ],
    "cloud_init_modules": [
     "seed_random",
     "bootcmd",
     "write_files",
     "growpart",
     "resizefs",
     "disk_setup",
     "mounts",
     "set_hostname",
     "update_hostname",
     "update_etc_hosts",
     "ca_certs",
     "rsyslog",
     "users_groups",
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

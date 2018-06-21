*******************
Integration Testing
*******************

Overview
========

This page describes the execution, development, and architecture of the
cloud-init integration tests:

* Execution explains the options available and running of tests
* Development shows how to write test cases
* Architecture explains the internal processes

Execution
=========

Overview
--------

In order to avoid the need for dependencies and ease the setup and
configuration users can run the integration tests via tox:

.. code-block:: shell-session

    $ git clone https://git.launchpad.net/cloud-init
    $ cd cloud-init
    $ tox -e citest -- -h

Everything after the double dash will be passed to the integration tests.
Executing tests has several options:

* ``run`` an alias to run both ``collect`` and ``verify``. The ``tree_run``
  command does the same thing, except uses a deb built from the current
  working tree.

* ``collect`` deploys on the specified platform and distro, patches with the
  requested deb or rpm, and finally collects output of the arbitrary
  commands. Similarly, ```tree_collect`` will collect output using a deb
  built from the current working tree.

* ``verify`` given a directory of test data, run the Python unit tests on
  it to generate results.

* ``bddeb`` will build a deb of the current working tree.

Run
---

The first example will provide a complete end-to-end run of data
collection and verification. There are additional examples below
explaining how to run one or the other independently.

.. code-block:: shell-session

    $ git clone https://git.launchpad.net/cloud-init
    $ cd cloud-init
    $ tox -e citest -- run --verbose \
        --os-name stretch --os-name xenial \
        --deb cloud-init_0.7.8~my_patch_all.deb \
        --preserve-data --data-dir ~/collection \
        --preserve-instance

The above command will do the following:

* ``run`` both collect output and run tests the output

* ``--verbose`` verbose output

* ``--os-name stretch`` on the Debian Stretch release

* ``--os-name xenial`` on the Ubuntu Xenial release

* ``--deb cloud-init_0.7.8~patch_all.deb`` use this deb as the version of
  cloud-init to run with

* ``--preserve-data`` always preserve collected data, do not remove data
  after successful test run

* ``--preserve-instance`` do not destroy the instance after test to allow
  for debugging the stopped instance during integration test development. By
  default, test instances are destroyed after the test completes.

* ``--data-dir ~/collection`` write collected data into `~/collection`,
  rather than using a temporary directory

For a more detailed explanation of each option see below.

.. note::
    By default, data collected by the run command will be written into a
    temporary directory and deleted after a successful. If you would
    like to preserve this data, please use the option ``--preserve-data``.

Collect
-------

If developing tests it may be necessary to see if cloud-config works as
expected and the correct files are pulled down. In this case only a
collect can be ran by running:

.. code-block:: shell-session

    $ tox -e citest -- collect -n xenial --data-dir /tmp/collection

The above command will run the collection tests on xenial and place
all results into `/tmp/collection`.

Verify
------

When developing tests it is much easier to simply rerun the verify scripts
without the more lengthy collect process. This can be done by running:

.. code-block:: shell-session

    $ tox -e citest -- verify --data-dir /tmp/collection

The above command will run the verify scripts on the data discovered in
`/tmp/collection`.

TreeRun and TreeCollect
-----------------------

If working on a cloud-init feature or resolving a bug, it may be useful to
run the current copy of cloud-init in the integration testing environment.
The integration testing suite can automatically build a deb based on the
current working tree of cloud-init and run the test suite using this deb.

The ``tree_run`` and ``tree_collect`` commands take the same arguments as
the ``run`` and ``collect`` commands. These commands will build a deb and
write it into a temporary file, then start the test suite and pass that deb
in. To build a deb only, and not run the test suite, the ``bddeb`` command
can be used.

Note that code in the cloud-init working tree that has not been committed
when the cloud-init deb is built will still be included. To build a
cloud-init deb from or use the ``tree_run`` command using a copy of
cloud-init located in a different directory, use the option ``--cloud-init
/path/to/cloud-init``.

.. code-block:: shell-session

    $ tox -e citest -- tree_run --verbose \
        --os-name xenial --os-name stretch \
        --test modules/final_message --test modules/write_files \
        --result /tmp/result.yaml

Bddeb
-----

The ``bddeb`` command can be used to generate a deb file. This is used by
the tree_run and tree_collect commands to build a deb of the current
working tree. It can also be used a user to generate a deb for use in other
situations and avoid needing to have all the build and test dependencies
installed locally.

* ``--bddeb-args``: arguments to pass through to bddeb
* ``--build-os``: distribution to use as build system (default is xenial)
* ``--build-platform``: platform to use for build system (default is lxd)
* ``--cloud-init``: path to base of cloud-init tree (default is '.')
* ``--deb``: path to write output deb to (default is '.')

Setup Image
-----------

By default an image that is used will remain unmodified, but certain
scenarios may require image modification. For example, many images may use
a much older cloud-init. As a result tests looking at newer functionality
will fail because a newer version of cloud-init may be required. The
following options can be used for further customization:

* ``--deb``: install the specified deb into the image
* ``--rpm``: install the specified rpm into the image
* ``--repo``: enable a repository and upgrade cloud-init afterwards
* ``--ppa``: enable a ppa and upgrade cloud-init afterwards
* ``--upgrade``: upgrade cloud-init from repos
* ``--upgrade-full``: run a full system upgrade
* ``--script``: execute a script in the image. This can perform any setup
  required that is not covered by the other options

Test Case Development
=====================

Overview
--------

As a test writer you need to develop a test configuration and a
verification file:

 * The test configuration specifies a specific cloud-config to be used by
   cloud-init and a list of arbitrary commands to capture the output of
   (e.g my_test.yaml)

 * The verification file runs tests on the collected output to determine
   the result of the test (e.g. my_test.py)

The names must match, however the extensions will of course be different,
yaml vs py.

Configuration
-------------

The test configuration is a YAML file such as *ntp_server.yaml* below:

.. code-block:: yaml

    #
    # Empty NTP config to setup using defaults
    #
    # NOTE: this should not require apt feature, use 'which' rather than 'dpkg -l'
    # NOTE: this should not require no_ntpdate feature, use 'which' to check for
    #       installation rather than 'dpkg -l', as 'grep ntp' matches 'ntpdate'
    # NOTE: the verifier should check for any ntp server not 'ubuntu.pool.ntp.org'
    cloud_config: |
      #cloud-config
      ntp:
        servers:
          - pool.ntp.org
    required_features:
      - apt
      - no_ntpdate
      - ubuntu_ntp
    collect_scripts:
      ntp_installed_servers: |
        #!/bin/bash
        dpkg -l | grep ntp | wc -l
      ntp_conf_dist_servers: |
        #!/bin/bash
        ls /etc/ntp.conf.dist | wc -l
      ntp_conf_servers: |
        #!/bin/bash
        cat /etc/ntp.conf | grep '^server'

There are several keys, 1 required and some optional, in the YAML file:

1. The required key is ``cloud_config``. This should be a string of valid
   YAML that is exactly what would normally be placed in a cloud-config
   file, including the cloud-config header. This essentially sets up the
   scenario under test.

2. One optional key is ``collect_scripts``. This key has one or more
   sub-keys containing strings of arbitrary commands to execute (e.g.
   ```cat /var/log/cloud-config-output.log```). In the example above the
   output of dpkg is captured, grep for ntp, and the number of lines
   reported. The name of the sub-key is important. The sub-key is used by
   the verification script to recall the output of the commands ran.

3. The optional ``enabled`` key enables or disables the test case. By
   default the test case will be enabled.

4. The optional ``required_features`` key may be used to specify a list
   of features flags that an image must have to be able to run the test
   case. For example, if a test case relies on an image supporting apt,
   then the config for the test case should include ``required_features:
   [ apt ]``.


Default Collect Scripts
-----------------------

By default the following files will be collected for every test. There is
no need to specify these items:

* ``/var/log/cloud-init.log``
* ``/var/log/cloud-init-output.log``
* ``/run/cloud-init/.instance-id``
* ``/run/cloud-init/result.json``
* ``/run/cloud-init/status.json``
* ```dpkg-query -W -f='${Version}' cloud-init```

Verification
------------

The verification script is a Python file with unit tests like the one,
`ntp_server.py`, below:

.. code-block:: python

    # This file is part of cloud-init. See LICENSE file for license information.

    """cloud-init Integration Test Verify Script"""
    from tests.cloud_tests.testcases import base


    class TestNtp(base.CloudTestCase):
        """Test ntp module"""

        def test_ntp_installed(self):
            """Test ntp installed"""
            out = self.get_data_file('ntp_installed_empty')
            self.assertEqual(1, int(out))

        def test_ntp_dist_entries(self):
            """Test dist config file has one entry"""
            out = self.get_data_file('ntp_conf_dist_empty')
            self.assertEqual(1, int(out))

        def test_ntp_entires(self):
            """Test config entries"""
            out = self.get_data_file('ntp_conf_empty')
            self.assertIn('pool 0.ubuntu.pool.ntp.org iburst', out)
            self.assertIn('pool 1.ubuntu.pool.ntp.org iburst', out)
            self.assertIn('pool 2.ubuntu.pool.ntp.org iburst', out)
            self.assertIn('pool 3.ubuntu.pool.ntp.org iburst', out)

    # vi: ts=4 expandtab


Here is a breakdown of the unit test file:

* The import statement allows access to the output files.

* The class can be named anything, but must import the
  ``base.CloudTestCase``, either directly or via another test class.

* There can be 1 to N number of functions with any name, however only
  functions starting with ``test_*`` will be executed.

* There can be 1 to N number of classes in a test module, however only
  classes inheriting from ``base.CloudTestCase`` will be loaded.

* Output from the commands can be accessed via
  ``self.get_data_file('key')`` where key is the sub-key of
  ``collect_scripts`` above.

* The cloud config that the test ran with can be accessed via
  ``self.cloud_config``, or any entry from the cloud config can be accessed
  via ``self.get_config_entry('key')``.

* See the base ``CloudTestCase`` for additional helper functions.

Layout
------

Integration tests are located under the `tests/cloud_tests` directory.
Test configurations are placed under `configs` and the test verification
scripts under `testcases`:

.. code-block:: shell-session

    cloud-init$ tree -d tests/cloud_tests/
    tests/cloud_tests/
    ├── configs
    │   ├── bugs
    │   ├── examples
    │   ├── main
    │   └── modules
    └── testcases
        ├── bugs
        ├── examples
        ├── main
        └── modules

The sub-folders of bugs, examples, main, and modules help organize the
tests. View the README.md in each to understand in more detail each
directory.

Test Creation Helper
--------------------

The integration testing suite has a built in helper to aid in test
development. Help can be invoked via ``tox -e citest -- create --help``. It
can create a template test case config file with user data passed in from
the command line, as well as a template test case verifier module.

The following would create a test case named ``example`` under the
``modules`` category with the given description, and cloud config data read
in from ``/tmp/user_data``.

.. code-block:: shell-session

    $ tox -e citest -- create modules/example \
        -d "a simple example test case" -c "$(< /tmp/user_data)"


Development Checklist
---------------------

* Configuration File
    * Named 'your_test.yaml'
    * Contains at least a valid cloud-config
    * Optionally, commands to capture additional output
    * Valid YAML
    * Placed in the appropriate sub-folder in the configs directory
    * Any image features required for the test are specified
* Verification File
    * Named 'your_test.py'
    * Valid unit tests validating output collected
    * Passes pylint & pep8 checks
    * Placed in the appropriate sub-folder in the test cases directory
* Tested by running the test:

   .. code-block:: shell-session

       $ tox -e citest -- run -verbose \
           --os-name <release target> \
           --test modules/your_test.yaml \
           [--deb <build of cloud-init>]


Platforms
=========

EC2
---
To run on the EC2 platform it is required that the user has an AWS credentials
configuration file specifying his or her access keys and a default region.
These configuration files are the standard that the AWS cli and other AWS
tools utilize for interacting directly with AWS itself and are normally
generated when running ``aws configure``:

.. code-block:: shell-session

    $ cat $HOME/.aws/credentials
    [default]
    aws_access_key_id = <KEY HERE>
    aws_secret_access_key = <KEY HERE>

.. code-block:: shell-session

    $ cat $HOME/.aws/config
    [default]
    region = us-west-2


Architecture
============

The following section outlines the high-level architecture of the
integration process.

Overview
--------
The process flow during a complete end-to-end LXD-backed test.

1. Configuration
    * The back end and specific distro releases are verified as supported
    * The test or tests that need to be run are determined either by
      directory or by individual yaml

2. Image Creation
    * Acquire the request LXD image
    * Install the specified cloud-init package
    * Clean the image so that it does not appear to have been booted
    * A snapshot of the image is created and reused by all tests

3. Configuration
    * For each test, the cloud-config is injected into a copy of the
      snapshot and booted
    * The framework waits for ``/var/lib/cloud/instance/boot-finished``
      (up to 120 seconds)
    * All default commands are ran and output collected
    * Any commands the user specified are executed and output collected

4. Verification
    * The default commands are checked for any failures, errors, and
      warnings to validate basic functionality of cloud-init completed
      successfully
    * The user generated unit tests are then ran validating against the
      collected output

5. Results
    * If any failures were detected the test suite returns a failure
    * Results can be dumped in yaml format to a specified file using the
      ``-r <result_file_name>.yaml`` option

Configuring the Test Suite
--------------------------

Most of the behavior of the test suite is configurable through several yaml
files. These control the behavior of the test suite's platforms, images, and
tests. The main config files for platforms, images and test cases are
``platforms.yaml``, ``releases.yaml`` and ``testcases.yaml``.

Config handling
^^^^^^^^^^^^^^^

All configurable parts of the test suite use a defaults + overrides system
for managing config entries. All base config items are dictionaries.

Merging is done on a key-by-key basis, with all keys in the default and
override represented in the final result. If a key exists both in
the defaults and the overrides, then the behavior depends on the type of data
the key refers to. If it is atomic data or a list, then the overrides will
replace the default. If the data is a dictionary then the value will be the
result of merging that dictionary from the default config and that
dictionary from the overrides.

Merging is done using the function
``tests.cloud_tests.config.merge_config``, which can be examined for more
detail on config merging behavior.

The following demonstrates merge behavior:

.. code-block:: yaml

    defaults:
        list_item:
         - list_entry_1
         - list_entry_2
        int_item_1: 123
        int_item_2: 234
        dict_item:
            subkey_1: 1
            subkey_2: 2
            subkey_dict:
                subsubkey_1: a
                subsubkey_2: b

    overrides:
        list_item:
         - overridden_list_entry
        int_item_1: 0
        dict_item:
            subkey_2: false
            subkey_dict:
                subsubkey_2: 'new value'

    result:
        list_item:
         - overridden_list_entry
        int_item_1: 0
        int_item_2: 234
        dict_item:
            subkey_1: 1
            subkey_2: false
            subkey_dict:
                subsubkey_1: a
                subsubkey_2: 'new value'


Image Config
------------

Image configuration is handled in ``releases.yaml``. The image configuration
controls how platforms locate and acquire images, how the platforms should
interact with the images, how platforms should detect when an image has
fully booted, any options that are required to set the image up, and
features that the image supports.

Since settings for locating an image and interacting with it differ from
platform to platform, there are 4 levels of settings available for images on
top of the default image settings. The structure of the image config file
is:

.. code-block:: yaml

    default_release_config:
        default:
            ...
        <platform>:
            ...
        <platform>:
            ...

    releases:
        <release name>:
            <default>:
                ...
            <platform>:
                ...
            <platform>:
                ...


The base config is created from the overall defaults and the overrides for
the platform. The overrides are created from the default config for the
image and the platform specific overrides for the image.

System Boot
^^^^^^^^^^^

The test suite must be able to test if a system has fully booted and if
cloud-init has finished running, so that running collect scripts does not
race against the target image booting. This is done using the
``system_ready_script`` and ``cloud_init_ready_script`` image config keys.

Each of these keys accepts a small bash test statement as a string that must
return 0 or 1. Since this test statement will be added into a larger bash
statement it must be a single statement using the ``[`` test syntax.

The default image config provides a system ready script that works for any
systemd based image. If the image is not systemd based, then a different
test statement must be provided. The default config also provides a test
for whether or not cloud-init has finished which checks for the file
``/run/cloud-init/result.json``. This should be sufficient for most systems
as writing this file is one of the last things cloud-init does.

The setting ``boot_timeout`` controls how long, in seconds, the platform
should wait for an image to boot. If the system ready script has not
indicated that the system is fully booted within this time an error will be
raised.

Feature Flags
^^^^^^^^^^^^^

Not all test cases can work on all images due to features the test case
requires not being present on that image. If a test case requires features
in an image that are not likely to be present across all distros and
platforms that the test suite supports, then the test can be skipped
everywhere it is not supported.

Feature flags, which are names for features supported on some images, but
not all that may be required by test cases. Configuration for feature flags
is provided in ``releases.yaml`` under the ``features`` top level key. The
features config includes a list of all currently defined feature flags,
their meanings, and a list of feature groups.

Feature groups are groups of features that many images have in common. For
example, the ``Ubuntu_specific`` feature group includes features that
should be present across most Ubuntu releases, but may or may not be for
other distros. Feature groups are specified for an image as a list under
the key ``feature_groups``.

An image's feature flags are derived from the features groups that that
image has and any feature overrides provided. Feature overrides can be
specified under the ``features`` key which accepts a dictionary of
``{<feature_name>: true/false}`` mappings. If a feature is omitted from an
image's feature flags or set to false in the overrides then the test suite
will skip any tests that require that feature when using that image.

Feature flags may be overridden at run time using the ``--feature-override``
command line argument. It accepts a feature flag and value to set in the
format ``<feature name>=true/false``. Multiple ``--feature-override``
flags can be used, and will all be applied to all feature flags for images
used during a test.

Setup Overrides
^^^^^^^^^^^^^^^

If an image requires some of the options for image setup to be used, then it
may specify overrides for the command line arguments passed into setup
image. These may be specified as a dictionary under the ``setup_overrides``
key. When an image is set up, the arguments that control how it is set up
will be the arguments from the command line, with any entries in
``setup_overrides`` used to override these arguments.

For example, images that do not come with cloud-init already installed
should have ``setup_overrides: {upgrade: true}`` specified so that in the
event that no additional setup options are given, cloud-init will be
installed from the image's repos before running tests. Note that if other
options such as ``--deb`` are passed in on the command line, these will
still work as expected, since apt's policy for cloud-init would prefer the
locally installed deb over an older version from the repos.

Platform Specific Options
^^^^^^^^^^^^^^^^^^^^^^^^^

There are many platform specific options in image configuration that allow
platforms to locate images and that control additional setup that the
platform may have to do to make the image usable. For information on how
these work, please consult the documentation for that platform in the
integration testing suite and the ``releases.yaml`` file for examples.

Error Handling
--------------

The test suite makes an attempt to run as many tests as possible even in the
event of some failing so that automated runs collect as much data as
possible. In the event that something goes wrong while setting up for or
running a test, the test suite will attempt to continue running any tests
which have not been affected by the error.

For example, if the test suite was told to run tests on one platform for two
releases and an error occurred setting up the first image, all tests for
that image would be skipped, and the test suite would continue to set up
the second image and run tests on it. Or, if the system does not start
properly for one test case out of many to run on that image, that test case
will be skipped and the next one will be run.

Note that if any errors occur, the test suite will record the failure and
where it occurred in the result data and write it out to the specified
result file.

Results
-------

The test suite generates result data that includes how long each stage of
the test suite took and which parts were and were not successful. This data
is dumped to the log after the collect and verify stages, and may also be
written out in yaml format to a file. If part of the setup failed, the
traceback for the failure and the error message will be included in the
result file. If a test verifier finds a problem with the collected data
from a test run, the class, test function and test will be recorded in the
result data.

Exit Codes
^^^^^^^^^^

The test suite counts how many errors occur throughout a run. The exit code
after a run is the number of errors that occurred. If the exit code is
non-zero then something is wrong either with the test suite, the
configuration for an image, a test case, or cloud-init itself.

Note that the exit code does not always directly correspond to the number
of failed test cases, since in some cases, a single error during image setup
can mean that several test cases are not run. If run is used, then the exit
code will be the sum of the number of errors in the collect and verify
stages.

Data Dir
^^^^^^^^

When using run, the collected data is written into a temporary directory. In
the event that all tests pass, this directory is deleted, but if a test
fails or an error occurs, this data will be left in place, and a message
will be written to the log giving the location of the data.

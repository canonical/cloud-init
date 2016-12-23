****************
Test Development
****************


Overview
========

The purpose of this page is to describe how to write integration tests for
cloud-init. As a test writer you need to develop a test configuration and
a verification file:

 * The test configuration specifies a specific cloud-config to be used by
   cloud-init and a list of arbitrary commands to capture the output of
   (e.g my_test.yaml)

 * The verification file runs tests on the collected output to determine
   the result of the test (e.g. my_test.py)

The names must match, however the extensions will of course be different,
yaml vs py.

Configuration
=============

The test configuration is a YAML file such as *ntp_server.yaml* below:

.. code-block:: yaml

    #
    # NTP config using specific servers (ntp_server.yaml)
    #
    cloud_config: |
      #cloud-config
      ntp:
        servers:
          - pool.ntp.org
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


There are two keys, 1 required and 1 optional, in the YAML file:

1. The required key is ``cloud_config``. This should be a string of valid
   YAML that is exactly what would normally be placed in a cloud-config file,
   including the cloud-config header. This essentially sets up the scenario
   under test.

2. The optional key is ``collect_scripts``. This key has one or more
   sub-keys containing strings of arbitrary commands to execute (e.g.
   ```cat /var/log/cloud-config-output.log```). In the example above the
   output of dpkg is captured, grep for ntp, and the number of lines
   reported. The name of the sub-key is important. The sub-key is used by
   the verification script to recall the output of the commands ran.

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
============

The verification script is a Python file with unit tests like the one,
`ntp_server.py`, below:

.. code-block:: python

    """cloud-init Integration Test Verify Script (ntp_server.yaml)"""
    from tests.cloud_tests.testcases import base


    class TestNtpServers(base.CloudTestCase):
        """Test ntp module"""

        def test_ntp_installed(self):
            """Test ntp installed"""
            out = self.get_data_file('ntp_installed_servers')
            self.assertEqual(1, int(out))

        def test_ntp_dist_entries(self):
            """Test dist config file has one entry"""
            out = self.get_data_file('ntp_conf_dist_servers')
            self.assertEqual(1, int(out))

        def test_ntp_entires(self):
            """Test config entries"""
            out = self.get_data_file('ntp_conf_servers')
            self.assertIn('server pool.ntp.org iburst', out)


Here is a breakdown of the unit test file:

* The import statement allows access to the output files.

* The class can be named anything, but must import the ``base.CloudTestCase``

* There can be 1 to N number of functions with any name, however only
  tests starting with ``test_*`` will be executed.

* Output from the commands can be accessed via
  ``self.get_data_file('key')`` where key is the sub-key of
  ``collect_scripts`` above.

Layout
======

Integration tests are located under the `tests/cloud_tests` directory.
Test configurations are placed under `configs` and the test verification
scripts under `testcases`:

.. code-block:: bash

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


Development Checklist
=====================

* Configuration File
    * Named 'your_test_here.yaml'
    * Contains at least a valid cloud-config
    * Optionally, commands to capture additional output
    * Valid YAML
    * Placed in the appropriate sub-folder in the configs directory
* Verification File
    * Named 'your_test_here.py'
    * Valid unit tests validating output collected
    * Passes pylint & pep8 checks
    * Placed in the appropriate sub-folder in the testcsaes directory
* Tested by running the test: 

   .. code-block:: bash

       $ python3 -m tests.cloud_tests run -v -n <release of choice> \
           --deb <build of cloud-init> \
           -t tests/cloud_tests/configs/<dir>/your_test_here.yaml


Execution
=========

Executing tests has three options:

* ``run`` an alias to run both ``collect`` and ``verify``

* ``collect`` deploys on the specified platform and os, patches with the
  requested deb or rpm, and finally collects output of the arbitrary
  commands.

* ``verify`` given a directory of test data, run the Python unit tests on
  it to generate results.

Run
---
The first example will provide a complete end-to-end run of data
collection and verification. There are additional examples below
explaining how to run one or the other independently.

.. code-block:: bash

    $ git clone https://git.launchpad.net/cloud-init
    $ cd cloud-init
    $ python3 -m tests.cloud_tests run -v -n trusty -n xenial \
        --deb cloud-init_0.7.8~my_patch_all.deb

The above command will do the following:

* ``-v`` verbose output

* ``run`` both collect output and run tests the output

* ``-n trusty`` on the Ubuntu Trusty release

* ``-n xenial`` on the Ubuntu Xenial release

* ``--deb cloud-init_0.7.8~patch_all.deb`` use this deb as the version of
  cloud-init to run with

For a more detailed explanation of each option see below.

Collect
-------

If developing tests it may be necessary to see if cloud-config works as
expected and the correct files are pulled down. In this case only a
collect can be ran by running:

.. code-block:: bash

    $ python3 -m tests.cloud_tests collect -n xenial -d /tmp/collection \
        --deb cloud-init_0.7.8~my_patch_all.deb 

The above command will run the collection tests on xenial with the
provided deb and place all results into `/tmp/collection`.

Verify
------

When developing tests it is much easier to simply rerun the verify scripts
without the more lengthy collect process. This can be done by running:

.. code-block:: bash

    $ python3 -m tests.cloud_tests verify -d /tmp/collection

The above command will run the verify scripts on the data discovered in
`/tmp/collection`.


Architecture
============

The following outlines the process flow during a complete end-to-end LXD-backed test.

1. Configuration
    * The back end and specific OS releases are verified as supported
    * The test or tests that need to be run are determined either by directory or by individual yaml

2. Image Creation
    * Acquire the daily LXD image
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



.. _integration_tests:

Integration testing
*******************

Overview
=========

Integration tests are written using ``pytest`` and are located at
:file:`tests/integration_tests`. General design principles laid out in
:ref:`testing` should be followed for integration tests.

Setup is accomplished via a set of fixtures located in
:file:`tests/integration_tests/conftest.py`.

Test definition
===============

Tests are defined like any other ``pytest`` test. The ``user_data``
mark can be used to supply the cloud-config user-data. Platform-specific
marks can be used to limit tests to particular platforms. The ``client``
fixture can be used to interact with the launched test instance.

See `Examples`_ section for examples.

Test execution
==============

Test execution happens via ``pytest``. A ``tox`` definition exists to run
integration tests. When using this, normal ``pytest`` arguments can be
passed to the ``tox`` command by appending them after the ``--``. See the
following commands for examples.

.. tab-set::

    .. tab-item:: All integration tests

        .. code-block:: bash

            tox -e integration-tests

    .. tab-item:: Tests inside file or directory

        .. code-block:: bash

            tox -e integration-tests tests/integration_tests/modules/test_combined.py

    .. tab-item:: A specific test

        .. code-block:: bash

            tox -e integration-tests tests/integration_tests/modules/test_combined.py::test_bootcmd



Configuration
=============

All possible configuration values are defined in
`tests/integration_tests/integration_settings.py`_. Look in this file for
the full list of variables that are available and for context on what each
variable does and what the default values are.
Defaults can be overriden by supplying values in
:file:`tests/integration_tests/user_settings.py` or by
providing an environment variable of the same name prepended with
``CLOUD_INIT_``. For example, to set the ``PLATFORM`` setting:

.. code-block:: bash

    CLOUD_INIT_PLATFORM='ec2' tox -e integration_tests -- tests/integration_tests/


Common integration test run configurations
==========================================


Keep instance after test run
-------------------------------

By default, the test instance is torn down after the test run. To keep
the instance running after the test run, set the ``KEEP_INSTANCE`` variable
to ``True``.

.. tab-set::

    .. tab-item:: Inline environment variable

        .. code-block:: bash

            CLOUD_INIT_KEEP_INSTANCE=True tox -e integration_tests

    .. tab-item:: user_settings.py file

        .. code-block:: python

            KEEP_INSTANCE = True


Use in-place cloud-init source code
-------------------------------------

The simplest way to test an integraton test using your current cloud-init
changes is to set the ``CLOUD_INIT_SOURCE`` to ``IN_PLACE``. This works ONLY
on LXD containers. This will mount the source code as-is directly into
the container to override the pre-existing cloud-init code within the
container. This won't work for non-local LXD remotes and won't run any
installation code since the source code is mounted directly.

.. tab-set::

    .. tab-item:: Inline environment variable

        .. code-block:: bash

            CLOUD_INIT_CLOUD_INIT_SOURCE=IN_PLACE tox -e integration_tests

    .. tab-item:: user_settings.py file

        .. code-block:: python

            CLOUD_INIT_SOURCE = 'IN_PLACE'


Collecting logs after test run
-------------------------------

By default, logs are collected only when a test fails, by running ``cloud-init
collect-logs`` on the instance. To collect logs after every test run, set the
``COLLECT_LOGS`` variable to ``ALWAYS``.

By default, the logs are collected to the ``/tmp/cloud_init_test_logs``
directory. To change the directory, set the ``LOCAL_LOG_PATH`` variable to
the desired path.

.. tab-set::

    .. tab-item:: Inline environment variable

        .. code-block:: bash

            CLOUD_INIT_COLLECT_LOGS=ALWAYS CLOUD_INIT_LOCAL_LOG_PATH=/tmp/your-local-directory tox -e integration_tests

    .. tab-item:: user_settings.py file

        .. code-block:: python

            COLLECT_LOGS = "ALWAYS"
            LOCAL_LOG_PATH = "/tmp/logs"


Advanced test reporting and profiling
-------------------------------------

For advanced test reporting, set the ``INCLUDE_COVERAGE`` variable to ``True``.
This will generate a coverage report for the integration test run, and the
report will be stored in an ``html`` directory inside the directory specified
by ``LOCAL_LOG_PATH``.

.. tab-set::

    .. tab-item:: Inline environment variable

        .. code-block:: bash

            CLOUD_INIT_INCLUDE_COVERAGE=True tox -e integration_tests

    .. tab-item:: user_settings.py file

        .. code-block:: python

            INCLUDE_COVERAGE = True


Addtionally, for profiling the integration tests, set the ``INCLUDE_PROFILE``
variable to ``True``. This will generate a profile report for the integration
test run, and the report will be stored in the directory specified by
``LOCAL_LOG_PATH``.

.. tab-set::

    .. tab-item:: Inline environment variable

        .. code-block:: bash

            CLOUD_INIT_INCLUDE_PROFILE=True tox -e integration_tests

    .. tab-item:: user_settings.py file

        .. code-block:: python

            INCLUDE_PROFILE = True


Cloud interaction
=================

Cloud interaction happens via the `pycloudlib library`_. In order to run
integration tests, pycloudlib must `first be configured`_.

For a minimal setup using LXD, write the following to
:file:`~/.config/pycloudlib.toml`:

.. code-block:: toml

    [lxd]


For more information on configuring pycloudlib, see the
`pycloudlib configuration documentation`_.

To specify a specific cloud to test against, first, ensure that your pycloudlib
configuration is set up correctly. Then, modify the ``PLATFORM`` variable to be
on of:

- ``azure``: Microsoft Azure
- ``ec2``: Amazon EC2
- ``gce``: Google Compute Engine
- ``ibm``: IBM Cloud
- ``lxd_container``: LXD container
- ``lxd_vm``: LXD VM
- ``oci``: Oracle Cloud Infrastructure
- ``openstack``: OpenStack
- ``qemu``: QEMU

.. tab-set::

    .. tab-item:: Inline environment variable

        .. code-block:: bash

            CLOUD_INIT_PLATFORM='lxd_container' tox -e integration_tests

    .. tab-item:: user_settings.py file

        .. code-block:: python

            PLATFORM = 'lxd_container'


Selecting Instance Type
-----------------------

To select a specific instance type, modify the ``INSTANCE_TYPE`` variable to be
the desired instance type. This value is cloud-specific, so refer to the
cloud's documentation for the available instance types. If you specify an
instance type, be sure to also specify respective cloud platform you are
testing against.

.. tab-set::

    .. tab-item:: Inline environment variable

        .. code-block:: bash

            CLOUD_INIT_PLATFORM=ec2 CLOUD_INIT_INSTANCE_TYPE='t2.micro' tox -e integration_tests

    .. tab-item:: user_settings.py file

        .. code-block:: python

            PLATFORM = 'ec2'  # need to specify the cloud in order to use the instance type setting
            INSTANCE_TYPE = 't2.micro'

Image selection
===============

Each integration testing run uses a single image as its basis. This
image is configured using the ``OS_IMAGE`` variable; see
`Configuration`_ for details of how configuration works.

``OS_IMAGE`` can take two types of value: an Ubuntu series name (e.g.
"focal"), or an image specification. If an Ubuntu series name is
given, then the most recent image for that series on the target cloud
will be used. For other use cases, an image specification is used.

In its simplest form, an image specification can simply be a cloud's
image ID (e.g., "ami-deadbeef", "ubuntu:focal"). In this case, the
identified image will be used as the basis for this testing run.

This has a drawback, however. As we do not know what OS or release is
within the image, the integration testing framework will run *all*
tests against the image in question. If it's a RHEL8 image, then we
would expect Ubuntu-specific tests to fail (and vice versa).

To address this, a full image specification can be given. This is of
the form: ``<image_id>[::<os>::<release>::<version>]`` where ``image_id`` is a
cloud's image ID, ``os`` is the OS name, and ``release`` is the OS
release name. So, for example, Ubuntu 24.04 LTS (Noble Numbat) on LXD is
``ubuntu:noble::ubuntu::noble::24.04`` or RHEL8 on Amazon is
``ami-justanexample::rhel::9::9.3``. When a full specification is given,
only tests which are intended for use on that OS and release will be
executed.

To run integration tests on a specific image, modify the ``OS_IMAGE``
variable to be the desired image specification.

.. tab-set::

    .. tab-item:: Inline environment variable

        .. code-block:: bash

            CLOUD_INIT_OS_IMAGE='jammy' tox -e integration_tests

    .. tab-item:: user_settings.py file

        .. code-block:: python

            OS_IMAGE = 'jammy'


To run integration tests on a specific type/family of image, modify the
``OS_IMAGE_TYPE`` variable to be the desired image type. This comes from
`pycloudlib's ImageType enum`_, which can take the following values:

- "generic"
- "minimal"
- "Pro"
- "Pro FIPS"

.. tab-set::

    .. tab-item:: Inline environment variable

        .. code-block:: bash

            CLOUD_INIT_PLATFORM=lxd_container CLOUD_INIT_OS_IMAGE=noble CLOUD_INIT_OS_IMAGE_TYPE=minimal tox -e integration_tests

    .. tab-item:: user_settings.py file

        .. code-block:: python

            OS_PLATFORM = 'lxd_container'
            OS_IMAGE = 'noble'
            OS_IMAGE_TYPE = 'minimal'

Note: Not all clouds and OSes support all image types

Image setup
===========

Image setup occurs once when a test session begins and is implemented
via fixture. Image setup roughly follows these steps:

* Launch an instance on the specified test platform.
* Install the version of ``cloud-init`` under test.
* Run :command:`cloud-init clean` on the instance so subsequent boots
  resemble "out of the box" behaviour.
* Take a snapshot of the instance to be used as a new image from
  which new instances can be launched.


Keep image after test run
--------------------------

By default, the image created during the test run is torn down after
the test run. If further debugging is needed, you can keep the image snapshot
for further use by setting the ``KEEP_IMAGE`` variable to ``True``.

.. tab-set::

    .. tab-item:: Inline environment variable

        .. code-block:: bash

            CLOUD_INIT_KEEP_IMAGE=True tox -e integration_tests

    .. tab-item:: user_settings.py file

        .. code-block:: python

            KEEP_IMAGE = True


Test setup
==========

Test setup occurs between image setup and test execution. Test setup
is implemented via one of the ``client`` fixtures. When a ``client`` fixture
is used, a test instance from which to run tests is launched prior to
test execution, and then torn down after.

Continuous integration
======================

A subset of the integration tests are run when a pull request
is submitted on GitHub. The tests run on these continuous
integration (CI) runs are given a ``pytest`` mark:

.. code-block:: python

    @pytest.mark.ci

Most new tests should *not* use this mark, so be aware that having a
successful CI run does not necessarily mean that your test passed
successfully.

Fixtures
========

Integration tests rely heavily on fixtures to do initial test setup.
One or more of these fixtures will be used in almost every integration test.

Details such as the cloud platform or initial image to use are determined
via what is specified in the `Configuration`_.

``client``
----------

The ``client`` fixture should be used for most test cases. It ensures:

- All setup performed by `session_cloud`_ and `setup_image`_.
- `Pytest marks`_ used during instance creation are obtained and applied.
- The test instance is launched.
- Test failure status is determined after test execution.
- Logs are collected (if configured) after test execution.
- The test instance is torn down after test execution.

``module_client`` and ``class_client`` fixtures also exist for the
purpose of running multiple tests against a single launched instance.
They provide the exact same functionality as ``client``, but are
scoped to the module or class respectively.ci

``session_cloud``
-----------------

The ``session_cloud`` session-scoped fixture will provide an
`IntegrationCloud`_ instance for the currently configured cloud. The fixture
also ensures that any custom cloud session cleanup is performed.

``setup_image``
---------------

The ``setup_image`` session-scope fixture will create a new image to launch
all further cloud instances during this test run. It ensures:

- A cloud instance is launched on the configured platform.
- The version of ``cloud-init`` under test is installed on the instance.
- :command:`cloud-init clean --logs` is run on the instance.
- A snapshot of the instance is taken to be used as the basis for
  future instance launches.
- The originally launched instance is torn down.
- The custom created image is torn down after all tests finish.

Examples
--------

A simple test case using the ``client`` fixture:

.. code-block:: python

    USER_DATA = """\
    #cloud-config
    bootcmd:
    - echo 'hello!' > /var/tmp/hello.txt
    """


    @pytest.mark.user_data(USER_DATA)
    def test_bootcmd(client):
        log = client.read_from_file("/var/log/cloud-init.log")
        assert "Shellified 1 commands." in log
        assert client.execute('cat /var/tmp/hello.txt').strip() == "hello!"

Customizing the launch arguments before launching an instance manually:

.. code-block:: python

    def test_launch(session_cloud: IntegrationCloud, setup_image):
        with session_cloud.launch(launch_kwargs={"wait": False}) as client:
            client.instance.wait()
            assert client.execute("echo hello world").strip() == "hello world"

.. LINKS:
.. _tests/integration_tests/integration_settings.py: https://github.com/canonical/cloud-init/blob/main/tests/integration_tests/integration_settings.py
.. _pycloudlib library: https://pycloudlib.readthedocs.io/en/latest/index.html
.. _first be configured: https://pycloudlib.readthedocs.io/en/latest/configuration.html#configuration
.. _Pytest marks: https://github.com/canonical/cloud-init/blob/af7eb1deab12c7208853c5d18b55228e0ba29c4d/tests/integration_tests/conftest.py#L220-L224
.. _IntegrationCloud: https://github.com/canonical/cloud-init/blob/af7eb1deab12c7208853c5d18b55228e0ba29c4d/tests/integration_tests/clouds.py#L102
.. _pycloudlib configuration documentation: https://pycloudlib.readthedocs.io/en/latest/configuration.html
.. _pycloudlib's ImageType enum: https://github.com/canonical/pycloudlib/blob/1!10.0.0/pycloudlib/cloud.py#L28

.. _integration_tests:

*******************
Integration Testing
*******************

Overview
=========

Integration tests are written using pytest and are located at
``tests/integration_tests``. General design principles
laid out in :ref:`testing` should be followed for integration tests.

Setup is accomplished via a set of fixtures located in
``tests/integration_tests/conftest.py``.

Test Definition
===============
Tests are defined like any other pytest test. The ``user_data``
mark can be used to supply the cloud-config user data. Platform specific
marks can be used to limit tests to particular platforms. The
client fixture can be used to interact with the launched
test instance.

See :ref:`Examples` section for examples.

Test Execution
==============
Test execution happens via pytest. A tox definition exists to run integration
tests. To run all integration tests, you would run:

.. code-block:: bash

    $ tox -e integration-tests

Pytest arguments may also be passed. For example:

.. code-block:: bash

    $ tox -e integration-tests tests/integration_tests/modules/test_combined.py

Configuration
=============

All possible configuration values are defined in
`tests/integration_tests/integration_settings.py <https://github.com/canonical/cloud-init/blob/main/tests/integration_tests/integration_settings.py>`_.
Defaults can be
overridden by supplying values in ``tests/integration_tests/user_settings.py``
or by providing an environment variable of the same name prepended with
``CLOUD_INIT_``. For example, to set the ``PLATFORM`` setting:

.. code-block:: bash

    CLOUD_INIT_PLATFORM='ec2' pytest tests/integration_tests/


Cloud Interation
================
Cloud interaction happens via the
`pycloudlib <https://pycloudlib.readthedocs.io/en/latest/index.html>`_ library.
In order to run integration tests, pycloudlib must first be
`configured <https://pycloudlib.readthedocs.io/en/latest/configuration.html#configuration>`_.

For a minimal setup using LXD, write the following to
``~/.config/pycloudlib.toml``:

.. code-block:: toml

    [lxd]


Image Selection
===============

Each integration testing run uses a single image as its basis.  This
image is configured using the ``OS_IMAGE`` variable; see
:ref:`Configuration` for details of how configuration works.

``OS_IMAGE`` can take two types of value: an Ubuntu series name (e.g.
"focal"), or an image specification.  If an Ubuntu series name is
given, then the most recent image for that series on the target cloud
will be used.  For other use cases, an image specification is used.

In its simplest form, an image specification can simply be a cloud's
image ID (e.g. "ami-deadbeef", "ubuntu:focal").  In this case, the
image so-identified will be used as the basis for this testing run.

This has a drawback, however: as we do not know what OS or release is
within the image, the integration testing framework will run *all*
tests against the image in question.  If it's a RHEL8 image, then we
would expect Ubuntu-specific tests to fail (and vice versa).

To address this, a full image specification can be given.  This is of
the form: ``<image_id>[::<os>[::<release>]]`` where ``image_id`` is a
cloud's image ID, ``os`` is the OS name, and ``release`` is the OS
release name.  So, for example, Ubuntu 18.04 (Bionic Beaver) on LXD is
``ubuntu:bionic::ubuntu::bionic`` or RHEL 8 on Amazon is
``ami-justanexample::rhel::8``.  When a full specification is given,
only tests which are intended for use on that OS and release will be
executed.

Image Setup
===========

Image setup occurs once when a test session begins and is implemented
via fixture. Image setup roughly follows these steps:

* Launch an instance on the specified test platform
* Install the version of cloud-init under test
* Run ``cloud-init clean`` on the instance so subsequent boots
  resemble out of the box behavior
* Take a snapshot of the instance to be used as a new image from
  which new instances can be launched

Test Setup
==============
Test setup occurs between image setup and test execution. Test setup
is implemented via one of the ``client`` fixtures. When a client fixture
is used, a test instance from which to run tests is launched prior to
test execution and torn down after.

Continuous Integration
======================
A subset of the integration tests are run when a pull request
is submitted on Github. The tests run on these continuous
integration (CI) runs are given a pytest mark:

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
via what is specified in the :ref:`Configuration`.

client
------
The ``client`` fixture should be used for most test cases. It ensures:

- All setup performed by :ref:`session_cloud` and :ref:`setup_image`
- `Pytest marks <https://github.com/canonical/cloud-init/blob/af7eb1deab12c7208853c5d18b55228e0ba29c4d/tests/integration_tests/conftest.py#L220-L224>`_
  used during instance creation are obtained and applied
- The test instance is launched
- Test failure status is determined after test execution
- Logs are collected (if configured) after test execution
- The test instance is torn down after test execution

``module_client`` and ``class_client`` fixtures also exist for the
purpose of running multiple tests against a single launched instance.
They provide the exact same functionality as ``client``, but are
scoped to the module or class respectively.

session_cloud
-------------
The ``session_cloud`` session-scoped fixture will provide an
`IntegrationCloud <https://github.com/canonical/cloud-init/blob/af7eb1deab12c7208853c5d18b55228e0ba29c4d/tests/integration_tests/clouds.py#L102>`_
instance for the currently configured cloud. The fixture also
ensures that any custom cloud session cleanup is performed.

setup_image
-----------
The ``setup_image`` session-scope fixture will
create a new image to launch all further cloud instances
during this test run. It ensures:

- A cloud instance is launched on the configured platform
- The version of cloud-init under test is installed on the instance
- ``cloud-init clean --logs`` is run on the instance
- A snapshot of the instance is taken to be used as the basis for
  future instance launches
- The originally launched instance is torn down
- The custom created image is torn down after all tests finish

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

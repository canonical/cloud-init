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
the form: ``<image_id>[::<os>[::<release]]`` where ``image_id`` is a
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

Test Definition
===============
Tests are defined like any other pytest test. The ``user_data``
mark can be used to supply the cloud-config user data. Platform specific
marks can be used to limit tests to particular platforms. The
client fixture can be used to interact with the launched
test instance.

A basic example:

.. code-block:: python

    USER_DATA = """#cloud-config
    bootcmd:
    - echo 'hello config!' > /tmp/user_data.txt"""


    class TestSimple:
        @pytest.mark.user_data(USER_DATA)
        @pytest.mark.ec2
        def test_simple(self, client):
            print(client.exec('cloud-init -v'))

Test Execution
==============
Test execution happens via pytest. To run all integration tests,
you would run:

.. code-block:: bash

    pytest tests/integration_tests/


Configuration
=============

All possible configuration values are defined in
``tests/integration_tests/integration_settings.py``. Defaults can be
overridden by supplying values in ``tests/integration_tests/user_settings.py``
or by providing an environment variable of the same name prepended with
``CLOUD_INIT_``. For example, to set the ``PLATFORM`` setting:

.. code-block:: bash

    CLOUD_INIT_PLATFORM='ec2' pytest tests/integration_tests/

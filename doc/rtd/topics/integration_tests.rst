.. _integration_tests:

*******************
Integration Testing
*******************

Overview
=========

Integration tests are written using pytest and are located at
``tests/integration_tests``. General design principles
laid out in :ref:`unit_testing` should be followed for integration tests.

Setup is accomplished via a set of fixtures located in
``tests/integration_tests/conftest.py``.

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

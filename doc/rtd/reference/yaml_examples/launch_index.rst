.. _cce-launch-index:

Amazon EC2 launch index
***********************

This configuration syntax can be provided to have a given set of cloud config
data show up on a certain launch index (and not other launches).
This is done by providing a key here which acts as a filter on the instance's
user-data. When this key is absent (or non-integer) then the content of this
file will always be used for all launch-indexes (i.e. the default behavior).

.. code-block:: yaml

    #cloud-config
    launch-index: 5
    # Upgrade the instance on first boot
    # Default: false
    package_upgrade: true

For further information on launch indexes, refer to the
`Amazon EC2 documentation`.

.. LINKS

.. _Amazon EC2 documentation: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/AMI-launch-index-examples.html

.. _cce-archive:

Archive
*******

.. code-block:: yaml

    #cloud-config-archive
    - type: foo/wark
      filename: bar
      content: |
        This is my payload
        hello
    - this is also payload
    - |
      multi line payload
      here
    -
      type: text/cloud-config
      content: '#cloud-config\n\n        password: gocubs'

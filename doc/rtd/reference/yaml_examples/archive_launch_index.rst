.. _cce-archive-launch-index:

Cloud archive launch indexes
****************************

This is an example of a cloud archive format which includes a set of launch
indexes that will be filtered on (thus only showing up in instances with that
launch index). This is done by adding the ``launch-index`` key which maps to
the integer ``launch-index`` that the corresponding content should be used
with.

It is possible to leave this value out which means that the content will be
applicable for all instances.

.. code-block:: yaml

    #cloud-config-archive
    - type: foo/wark
      filename: bar
      content: |
        This is my payload
        hello
      launch-index: 1  # Will only be used on launch-index 1
    - this is also payload
    - |
      multi line payload
      here
    -
      type: text/upstart-job
      filename: my-upstart.conf
      content: |
       whats this, yo?s
      launch-index: 0 # Will only be used on launch-index 0

.. _qemu_debug_info:

QEMU tutorial debugging
***********************

You may wish to test out the commands in this tutorial as a
:download:`script<qemu-script.sh>` to check for copy-paste mistakes.

If you successfully launched the virtual machine, but couldn't log in,
there are a few places to check to debug your setup.

To debug, answer the following questions:

Did ``cloud-init`` discover the IMDS webserver?
===============================================

The webserver should print a message in the terminal for each request it
receives.  If it didn't print out any messages when the virtual machine booted,
then ``cloud-init`` was unable to obtain the config. Make sure that the
webserver can be locally accessed using :command:`curl` or :command:`wget`.

.. code-block:: sh

   $ curl 0.0.0.0:8000/user-data
   $ curl 0.0.0.0:8000/meta-data
   $ curl 0.0.0.0:8000/vendor-data

Did the IMDS webserver serve the expected files?
================================================

If the webserver prints out ``404 errors`` when launching QEMU, then check
that you started the server in the temp directory.

Were the configurations inside the file correct?
================================================

When launching QEMU, if the webserver shows that it succeeded in serving
:file:`user-data`, :file:`meta-data` and :file:`vendor-data`, but you cannot
log in, then you may have provided incorrect cloud-config files. If you can
mount a copy of the virtual machine's filesystem locally to inspect the logs,
it should be possible to get clues about what went wrong.

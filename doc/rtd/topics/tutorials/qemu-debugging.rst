.. _debug information:

Qemu Tutorial Debugging
***********************

If you successfully launched the virtual machine, but couldn't log in,
there are a few places to check to debug your setup.

To debug, answer the following questions:

Did cloud-init discover the imds webserver?
===========================================

The webserver should print a message in the terminal for each request it
receives.  If it didn't print out any messages when the virtual machine booted,
then cloud-init was unable to obtain the config. Make sure that the webserver
can be locally accessed using ``curl`` or ``wget``.

.. code-block:: sh

   $ curl 0.0.0.0:8000/user-data
   $ curl 0.0.0.0:8000/meta-data
   $ curl 0.0.0.0:8000/vendor-data

Did the imds webserver serve the files it was expected to serve?
================================================================

When launching Qemu, if the webserver prints out 404 errors, then try to figure
out why those files can't be served.

Did you forget to start the server in the temp directory?

Were the configurations inside of the file correct?
===================================================
When launching Qemu, if the webserver shows that it succeeded in serving
``user-data``, ``meta-data``, and ``vendor-data``, but you cannot log in, then
you may have provided incorrect cloud-config files. If you can mount a copy of
the virtual machine's filesystem locally to inspect the logs, it should be
possible to get clues about what went wrong.

.. _custom_formats:

Custom Formats
**************

One can define custom data formats by presenting a `#part-handler`
:ref:`user-data format<user_data_formats>`
config via user-data or vendor-data with the contents described in this page.

It contains custom code for either supporting new
mime-types in multi-part user data, or overriding the existing handlers for
supported mime-types. It will be written to a file in
:file:`/var/lib/cloud/data` based on its filename (which is generated).

This must be Python code that contains a ``list_types`` function and a
``handle_part`` function. Once the section is read the ``list_types`` method
will be called. It must return a list of mime-types that this `part-handler`
handles. Since MIME parts are processed in order, a `part-handler` part
must precede any parts with mime-types it is expected to handle in the same
user data.

The ``handle_part`` function must be defined like:

.. code-block:: python

    #part-handler

    def handle_part(data, ctype, filename, payload):
      # data = the cloudinit object
      # ctype = "__begin__", "__end__", or the mime-type of the part that is being handled.
      # filename = the filename of the part (or a generated filename if none is present in mime data)
      # payload = the parts' content

``Cloud-init`` will then call the ``handle_part`` function once before it
handles any parts, once per part received, and once after all parts have been
handled. The ``'__begin__'`` and ``'__end__'`` sentinels allow the part
handler to do initialisation or teardown before or after receiving any parts.

Begins with: ``#part-handler`` or ``Content-Type: text/part-handler`` when
using a MIME archive.

Example
-------

.. literalinclude:: ../../../examples/part-handler.txt
   :language: python
   :linenos:

Also, `this blog post`_ offers another example for more advanced usage.

.. _this blog post: http://foss-boss.blogspot.com/2011/01/advanced-cloud-init-custom-handlers.html

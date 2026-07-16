.. _custom_part_handler:

Custom Part Handler
*******************

This must be Python code that contains a ``list_types`` function and a
``handle_part`` function.

The ``list_types`` function takes no arguments and must return a list
of :ref:`content types<user_data_formats-content_types>` that this
part handler handles. These can include custom content types or built-in
content types that this handler will override.

The ``handle_part`` function takes 4 arguments and returns nothing. See the
example for how exactly each argument is used.

To use this part handler, it must be included in a MIME multipart file as
part of the :ref:`user-data<user_data_formats-mime_archive>`.
Since MIME parts are processed in order, a part handler part must precede
any parts with mime-types that it is expected to handle in the same user-data.

``Cloud-init`` will then call the ``handle_part`` function once before it
handles any parts, once per part received, and once after all parts have been
handled. These additional calls allow for initialization or teardown before
or after receiving any parts.

Example
=======

.. literalinclude:: ../../../examples/part-handler.txt
   :language: python
   :linenos:

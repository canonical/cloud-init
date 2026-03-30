.. _user_data_formats-part_handler:

Part handler
************

Part handlers define configuration formats by modifying ``cloud-init``'s
source code. These are not recommended for most users. The part handler API
is not guaranteed to be stable.

Example
-------

.. literalinclude:: ../../examples/part-handler.txt
   :language: python
   :linenos:


Explanation
-----------

A part handler contains custom code for either supporting new
mime-types in multi-part user-data or for overriding the existing handlers for
supported mime-types.

See the :ref:`custom part handler<custom_part_handler>` reference documentation
for details on writing custom handlers along with an annotated example.

`This blog post`_ offers another example for more advanced usage.

.. _This blog post: http://foss-boss.blogspot.com/2011/01/advanced-cloud-init-custom-handlers.html

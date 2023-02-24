.. _datasource_fallback:

Fallback/no datasource
**********************

This is the fallback datasource when no other datasource can be selected. It
is the equivalent of an empty datasource, in that it provides an empty string
as user data, and an empty dictionary as metadata.

It is useful for testing, as well as for occasions when you do not need an
actual datasource to meet your instance requirements (i.e. you just want to
run modules that are not concerned with any external data).

It is typically put at the end of the datasource search list so that if all
other datasources are not matched, then this one will be so that the user is
not left with an inaccessible instance.

.. note::
   The instance id that this datasource provides is ``iid-datasource-none``.

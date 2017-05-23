.. _datasource_fallback:

Fallback/None
=============

This is the fallback datasource when no other datasource can be selected. It
is the equivalent of a empty datasource in that it provides a empty string as
userdata and a empty dictionary as metadata. It is useful for testing as well
as for when you do not have a need to have an actual datasource to meet your
instance requirements (ie you just want to run modules that are not concerned
with any external data). It is typically put at the end of the datasource
search list so that if all other datasources are not matched, then this one
will be so that the user is not left with an inaccessible instance.

**Note:** the instance id that this datasource provides is
``iid-datasource-none``.

.. vi: textwidth=78

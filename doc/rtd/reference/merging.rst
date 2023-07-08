.. _merging_user_data:

Merging user data sections
**************************

A common requirement when using multiple user data sections is merging them,
so different cloud-config YAML files can specify the same keys. For example,
if we have two different cloud-configs in our user data:

.. code-block:: yaml

   #cloud-config (1)
   runcmd:
     - bash1
     - bash2

   #cloud-config (2)
   runcmd:
     - bash3
     - bash4

Merging will allow us to have an end result such as:

..code-block:: yaml

   #cloud-config (merged)
   runcmd:
     - bash1
     - bash2
     - bash3
     - bash4

By default, merging is limited to recursively adding keys that do not exist
yet. There are two ways to enable more advanced merging strategies:

1. In cloud-config YAML configuration, two keys will be checked: ``merge_how``,
   and ``merge_type`` (in this order). Their value should be either a format
   string, or a configuration object as described below.
2. In multi-part documents, two headers will be checked: ``Merge-Type`` and
   ``X-Merge-Type`` (in this order). The value should contain a merging format
   string as described below.

There are three types of configuration that can be merged: Lists, dictionaries,
and strings. Cloud-config allows enabling and configuring merging for all of
them separately. For the available options, look below.

Dictionary format
-----------------

A dictionary can be used when it specifies the same information as the
string format (i.e., the second option above). For example:

.. code-block:: yaml

   merge_how:
     - name: list
       settings: ['append']
     - name: dict
       settings: ['no_replace', 'recurse_list']
     - name: str
       settings: ['append']

This example matches the default configuration.

String format
-------------

The following string format is expected: ::

   type1(option1,option2)+type2(option3,option4)....

The type must be one of ``list`` (arrays), ``dict`` (objects), 
or ``str`` (strings). In brackets, you can pass options for each type. To use
the defaults, pass the type with braces (e.g. ``list()``). The default format
string looks like this:

.. code-block:: python

   list()+dict()+str()

To enable an option, pass its name (or omit to disable). For example:

.. code-block:: python

   merge_how: "list(replace,append)+dict(replace)"

Available options
-----------------

Dicts
~~~~~

These options apply to dicts:

- :command:`allow_delete`: Existing values not present in the new value can be
  deleted. Disabled by default.
- :command:`no_replace`: Do not replace an existing value if one is already
  present. Enabled by default.
- :command:`replace`: Overwrite existing values with new ones. Disabled by 
  default.

Lists
~~~~~

These options apply to lists:

- :command:`append`: Add new value to the end of the list. Disabled by 
  default.
- :command:`prepend`: Add new values to the start of the list. Disabled by
  default.
- :command:`no_replace`: Do not replace an existing value if one is already
  present. Enabled by default.
- :command:`replace`: Overwrite existing values with new ones. Disabled by
  default.

Strings
~~~~~~~

These options apply to strings:

- :command:`append`: Add new value to the end of the string. Disabled by 
  default.

Common options
~~~~~~~~~~~~~~

These are the common options for all merge types, which control how recursive
merging is done on other types.

- :command:`recurse_dict`: Merge the new values of the dictionary. Enabled by
  default.
- :command:`recurse_list`: Merge the new values of the list. Disabled by 
  default.
- :command:`recurse_array`: Alias for ``recurse_list``.
- :command:`recurse_str`: Merge the new values of the string. Disabled by 
  default.

Example cloud-config
====================

A common request is to include multiple ``runcmd`` directives in different
files and merge all of the commands together. To achieve this, we must modify
the default merging to allow for dictionaries to join list values.

The first config:

.. code-block:: yaml

   #cloud-config
   merge_how:
    - name: list
      settings: [append]
    - name: dict
      settings: [no_replace, recurse_list]

   runcmd:
     - bash1
     - bash2

The second config:

.. code-block:: yaml

   #cloud-config
   merge_how:
    - name: list
      settings: [append]
    - name: dict
      settings: [no_replace, recurse_list]

   runcmd:
     - bash3
     - bash4

The effective config:

.. code-block:: yaml

   #cloud-config
   runcmd:
     - bash1
     - bash2
     - bash3
     - bash4

Specifying multiple merge types
===============================

When several cloud-config files define a merge type, the effective type will
be the result of stacking all previous types, starting from the default:

+---+---------------+--------------------------+---------------------------------------------------+
| # | Origin        | Definition in file       | Effective type                                    |
+===+===============+==========================+===================================================+
| 0 | _default_     | ``dict()+list()+str()``  | ``dict()+list()+str()``                           |
+---+---------------+--------------------------+---------------------------------------------------+
| 1 | config-1.yaml | ``list(replace,append)`` | ``dict()+list(replace,append)+str()``             |
+---+---------------+--------------------------+---------------------------------------------------+
| 2 | config-2.yaml | ``dict(recurse_list)``   | ``dict(recurse_list)+list(replace,append)+str()`` |
+---+---------------+--------------------------+---------------------------------------------------+
| 3 | config-3.yaml | ``list(prepend)``        | ``dict(recurse_list)+list(prepend)+str()``        |
+---+---------------+--------------------------+---------------------------------------------------+

In this way, a cloud-config can decide how it will merge with a cloud-config 
that comes after it. If you rely on a specific merge result, you should set
the required merge type explicitly.

Customisation
=============

Because the above merging algorithm may not always be desired (just as the
previous merging algorithm was not always the preferred one), the concept of
customised merging was introduced through `merge classes`.

A `merge class` is a class definition providing functions that can be used
to merge a given type with another given type.

An example of one of these `merging classes` is the following:

.. code-block:: python

   class Merger:
       def __init__(self, merger, opts):
           self._merger = merger
           self._overwrite = 'overwrite' in opts

       # This merging algorithm will attempt to merge with
       # another dictionary, on encountering any other type of object
       # it will not merge with said object, but will instead return
       # the original value
       #
       # On encountering a dictionary, it will create a new dictionary
       # composed of the original and the one to merge with, if 'overwrite'
       # is enabled then keys that exist in the original will be overwritten
       # by keys in the one to merge with (and associated values). Otherwise
       # if not in overwrite mode the 2 conflicting keys themselves will
       # be merged.
       def _on_dict(self, value, merge_with):
           if not isinstance(merge_with, (dict)):
               return value
           merged = dict(value)
           for (k, v) in merge_with.items():
               if k in merged:
                   if not self._overwrite:
                       merged[k] = self._merger.merge(merged[k], v)
                   else:
                       merged[k] = v
               else:
                   merged[k] = v
           return merged

As you can see, there is an ``_on_dict`` method here that will be given a
source value, and a value to merge with. The result will be the merged object.

This code itself is called by another merging class which "directs" the
merging to happen by analysing the object types to merge, and attempting to
find a known object that will merge that type. An example of this can be found
in the :file:`mergers/__init__.py` file (see ``LookupMerger`` and
``UnknownMerger``).

So, following the typical ``cloud-init`` approach of allowing source code to
be downloaded and used dynamically, it is possible for users to inject their
own merging files to handle specific types of merging as they choose (the
basic ones included will handle lists, dicts, and strings). Note how each
merge can have options associated with it, which affect how the merging is
performed. For example, a dictionary merger can be told to overwrite instead
of attempting to merge, or a string merger can be told to append strings
instead of discarding other strings to merge with.

Other uses
==========

In addition to being used for merging user data sections, the default merging
algorithm for merging :file:`'conf.d'` YAML files (which form an initial YAML
config for ``cloud-init``) was also changed to use this mechanism, to take
advantage of the full benefits (and customisation) here as well. Other places
that used the previous merging are also, similarly, now extensible (metadata
merging, for example).

Note, however, that merge algorithms are not used *across* configuration types.
As was the case before merging was implemented, user data will overwrite
:file:`'conf.d'` configuration without merging.

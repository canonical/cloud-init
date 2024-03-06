.. _merging_user_data:

Merging user data sections
**************************

The ability to merge user data sections allows a way to specify how
cloud-config YAML "dictionaries" provided as user data are handled when there
are multiple YAML files to be merged together (e.g., when performing an
#include).

For example merging these two configurations:

.. code-block:: yaml

   #cloud-config (1)
   runcmd:
     - bash1
     - bash2

   #cloud-config (2)
   runcmd:
     - bash3
     - bash4

Yields the following merged config:

.. code-block:: yaml

   #cloud-config (merged)
   runcmd:
     - bash1
     - bash2
     - bash3
     - bash4

Built-in mergers
================

``Cloud-init`` provides merging for the following built-in types:

- :command:`Dict`
- :command:`List`
- :command:`String`

``Dict``
--------

The :command:`Dict` merger has the following options, which control what is
done with values contained within the config.

- :command:`allow_delete`: Existing values not present in the new value can be
  deleted. Defaults to ``False``.
- :command:`no_replace`: Do not replace an existing value if one is already
  present. Enabled by default.
- :command:`replace`: Overwrite existing values with new ones.

``List``
--------

The :command:`List` merger has the following options, which control what is
done with the values contained within the config.

- :command:`append`: Add new value to the end of the list. Defaults to
  ``False``.
- :command:`prepend`: Add new values to the start of the list. Defaults to
  ``False``.
- :command:`no_replace`: Do not replace an existing value if one is already
  present. Enabled by default.
- :command:`replace`: Overwrite existing values with new ones.

String
------

The :command:`Str` merger has the following options, which control what is
done with the values contained within the config.

- :command:`append`: Add new value to the end of the string. Defaults to
  False.

Common options
--------------

These are the common options for all merge types, which control how recursive
merging is done on other types.

- :command:`recurse_dict`: If ``True``, merge the new values of the
  dictionary. Defaults to ``True``.
- :command:`recurse_list`: If ``True``, merge the new values of the list.
  Defaults to ``False``.
- :command:`recurse_array`: Alias for ``recurse_list``.
- :command:`recurse_str`: If ``True``, merge the new values of the string.
  Defaults to False.

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

How to activate
===============

There are a few ways to activate the merging algorithms, and to customise them
for your own usage.

1. The first way involves the usage of MIME messages in ``cloud-init`` to
   specify multi-part documents (this is one way in which multiple
   cloud-config can be joined together into a single cloud-config). Two new
   headers are looked for, both of which can define the way merging is done
   (the first header to exist "wins"). These new headers (in lookup order) are
   ``'Merge-Type'`` and ``'X-Merge-Type'``. The value should be a string which
   will satisfy the new merging format definition (see below for this format).

2. The second way is to specify the `merge type` in the body of the
   cloud-config dictionary. There are two ways to specify this; either as a
   string, or as a dictionary (see format below). The keys that are looked up
   for this definition are the following (in order): ``'merge_how'``,
   ``'merge_type'``.

String format
-------------

The following string format is expected: ::

   classname1(option1,option2)+classname2(option3,option4)....

The ``class name`` will be connected to class names used when looking for
the class that can be used to merge, and options provided will be given to the
class upon construction of that class.

The following example shows the default string that gets used when none is
otherwise provided: ::

   list()+dict()+str()

Dictionary format
-----------------

A dictionary can be used when it specifies the same information as the
string format (i.e., the second option above). For example:

.. code-block:: python

   {'merge_how': [{'name': 'list', 'settings': ['append']},
                  {'name': 'dict', 'settings': ['no_replace', 'recurse_list']},
                  {'name': 'str', 'settings': ['append']}]}

This would be the dictionary equivalent of the default string format.

Specifying multiple types, and what this does
=============================================

Now you may be asking yourself: "What exactly happens if I specify a
``merge-type`` header or dictionary for every cloud-config I provide?"

The answer is that when merging, a stack of ``'merging classes'`` is kept. The
first one in the stack is the default merging class. This set of mergers
will be used when the first cloud-config is merged with the initial empty
cloud-config dictionary. If the cloud-config that was just merged provided a
set of merging classes (via the above formats) then those merging classes will
be pushed onto the stack. Now if there is a second cloud-config to be merged
then the merging classes from the cloud-config before the first will be used
(not the default) and so on. In this way a cloud-config can decide how it will
merge with a cloud-config dictionary coming after it.

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

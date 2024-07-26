.. _custom_mergers:

Custom Mergers
**************

It is possible for users to inject their own :ref:`merging<merging_user_data>`
files to handle specific types of merging as they choose (the
basic ones included will handle lists, dicts, and strings).

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

There is an ``_on_dict`` method here that will be given a
source value, and a value to merge with. The result will be the merged object.

This code itself is called by another merging class which "directs" the
merging to happen by analysing the object types to merge, and attempting to
find a known object that will merge that type. An example of this can be found
in the :file:`mergers/__init__.py` file (see ``LookupMerger`` and
``UnknownMerger``).

Note how each
merge can have options associated with it, which affect how the merging is
performed. For example, a dictionary merger can be told to overwrite instead
of attempting to merge, or a string merger can be told to append strings
instead of discarding other strings to merge with.

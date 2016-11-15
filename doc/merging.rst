Overview
========

This was implemented because it has been a common feature request that there be
a way to specify how cloud-config yaml "dictionaries" provided as user-data are
merged together when there are multiple yamls to merge together (say when
performing an #include).

Since previously the merging algorithm was very simple and would only overwrite
and not append lists, or strings, and so on it was decided to create a new and
improved way to merge dictionaries (and there contained objects) together in a
way that is customizable, thus allowing for users who provide cloud-config
user-data to determine exactly how there objects will be merged.

For example.

.. code-block:: yaml

   #cloud-config (1)
   run_cmd:
     - bash1
     - bash2

   #cloud-config (2)
   run_cmd:
     - bash3
     - bash4

The previous way of merging the following 2 objects would result in a final
cloud-config object that contains the following.

.. code-block:: yaml

   #cloud-config (merged)
   run_cmd:
     - bash3
     - bash4

Typically this is not what users want, instead they would likely prefer:

.. code-block:: yaml

   #cloud-config (merged)
   run_cmd:
     - bash1
     - bash2
     - bash3
     - bash4

This way makes it easier to combine the various cloud-config objects you have
into a more useful list, thus reducing duplication that would have had to
occur in the previous method to accomplish the same result.

Customizability
===============

Since the above merging algorithm may not always be the desired merging
algorithm (like how the previous merging algorithm was not always the preferred
one) the concept of customizing how merging can be done was introduced through
a new concept call 'merge classes'.

A merge class is a class defintion which provides functions that can be used
to merge a given type with another given type.

An example of one of these merging classes is the following:

.. code-block:: python

   class Merger(object):
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

As you can see there is a '_on_dict' method here that will be given a source
value and a value to merge with. The result will be the merged object. This
code itself is called by another merging class which 'directs' the merging to
happen by analyzing the types of the objects to merge and attempting to find a
know object that will merge that type. I will avoid pasting that here, but it
can be found in the `mergers/__init__.py` file (see `LookupMerger` and
`UnknownMerger`).

So following the typical cloud-init way of allowing source code to be
downloaded and used dynamically, it is possible for users to inject there own
merging files to handle specific types of merging as they choose (the basic
ones included will handle lists, dicts, and strings). Note how each merge can
have options associated with it which affect how the merging is performed, for
example a dictionary merger can be told to overwrite instead of attempt to
merge, or a string merger can be told to append strings instead of discarding
other strings to merge with.

How to activate
===============

There are a few ways to activate the merging algorithms, and to customize them
for your own usage.

1. The first way involves the usage of MIME messages in cloud-init to specify
   multipart documents (this is one way in which multiple cloud-config is
   joined together into a single cloud-config). Two new headers are looked
   for, both of which can define the way merging is done (the first header to
   exist wins).  These new headers (in lookup order) are 'Merge-Type' and
   'X-Merge-Type'. The value should be a string which will satisfy the new
   merging format defintion (see below for this format).

2. The second way is actually specifying the merge-type in the body of the
   cloud-config dictionary. There are 2 ways to specify this, either as a
   string or as a dictionary (see format below). The keys that are looked up
   for this definition are the following (in order), 'merge_how',
   'merge_type'.

String format
-------------

The string format that is expected is the following.

::

   classname1(option1,option2)+classname2(option3,option4)....

The class name there will be connected to class names used when looking for the
class that can be used to merge and options provided will be given to the class
on construction of that class.

For example, the default string that is used when none is provided is the
following:

::

   list()+dict()+str()

Dictionary format
-----------------

In cases where a dictionary can be used to specify the same information as the
string format (ie option #2 of above) it can be used, for example.

.. code-block:: python

   {'merge_how': [{'name': 'list', 'settings': ['extend']},
                  {'name': 'dict', 'settings': []},
                  {'name': 'str', 'settings': ['append']}]}

This would be the equivalent format for default string format but in dictionary
form instead of string form.

Specifying multiple types and its effect
========================================

Now you may be asking yourself, if I specify a merge-type header or dictionary
for every cloud-config that I provide, what exactly happens?

The answer is that when merging, a stack of 'merging classes' is kept, the
first one on that stack is the default merging classes, this set of mergers
will be used when the first cloud-config is merged with the initial empty
cloud-config dictionary. If the cloud-config that was just merged provided a
set of merging classes (via the above formats) then those merging classes will
be pushed onto the stack. Now if there is a second cloud-config to be merged
then the merging classes from the cloud-config before the first will be used
(not the default) and so on. This way a cloud-config can decide how it will
merge with a cloud-config dictionary coming after it.

Other uses
==========

In addition to being used for merging user-data sections, the default merging
algorithm for merging 'conf.d' yaml files (which form an initial yaml config
for cloud-init) was also changed to use this mechanism so its full
benefits (and customization) can also be used there as well. Other places that
used the previous merging are also, similarly, now extensible (metadata
merging, for example).

Note, however, that merge algorithms are not used *across* types of
configuration.  As was the case before merging was implemented,
user-data will overwrite conf.d configuration without merging.

.. vi: textwidth=78

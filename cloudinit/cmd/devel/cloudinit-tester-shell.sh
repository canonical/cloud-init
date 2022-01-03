#! /usr/bin/env sh

# Use this script to startup a cloudinit-tester and then shell into it.
# This is potentially useful if you want to run a large number of commands,
# or play around.

# It also supports cmdline args at the end, to allow for running arbitrary commands 
# in case the default entrypoint of `python -m` is not suitable.

docker run --rm --name cloudinit-tester --volume $PWD:/src -it --entrypoint /bin/bash cloudinit-tester "$@" 

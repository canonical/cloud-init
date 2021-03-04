#!/usr/bin/env sh

# Use this script to run various commands inside a cloudinit-tester container.
# The cloudinit-tester container has an ENTRYPOINT of 'python -m', so use the
# script like this:
#
#    ./cloud-init-tester.sh pylint cloudinit  # This runs python -m pylint cloudinit
docker run --rm --name cloudinit-tester --volume $PWD:/src cloudinit-tester "$@" 

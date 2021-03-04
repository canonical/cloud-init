#!/usr/bin/env sh

# Use this script to build the docker image.
# Not too fancy, but it does ensure the image gets a predictable name,
# for use by other scripts.

docker build --tag cloudinit-tester .
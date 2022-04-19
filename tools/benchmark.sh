#!/usr/bin/bash

BIN="$@"
chmod +x "$BIN"

time for _ in $(seq 1 $ITER); do
	"$BIN";
done

#!/bin/sh

set -e

PYTHONPATH=../..:../../submodules/nmigen-examples \
          nmigen mono-square.py
sed -n '/Device utili.ation/,/^$/p' build/top.tim
grep MHz build/top.tim | tail -n 1

# Removed these.
#   NMIGEN_synth_opts=-dsp
#   NMIGEN_nextpnr_opts="--freq 24"


#!/bin/sh

PYTHONPATH=../..:../../submodules/nmigen-examples \
          nmigen mono-square.py
grep MHz build/top.tim | tail -n 1

# Removed these.
#   NMIGEN_synth_opts=-dsp
#   NMIGEN_nextpnr_opts="--freq 24"


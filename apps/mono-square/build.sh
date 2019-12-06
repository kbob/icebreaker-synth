#!/bin/sh

PYTHONPATH=../..:../../submodules/nmigen-examples \
NMIGEN_synth_opts=-dsp \
NMIGEN_nextpnr_opts="--freq 24" \
          nmigen mono-square.py

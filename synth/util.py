#!/usr/bin/env nmigen

def MIDI_note_to_freq(note):
    return 440 * 2**((note - 69) / 12)

assert 261 < MIDI_note_to_freq(60) < 262

def cents(n):
    return 2**(n/1200)

assert cents(1200) == 2

def to_cents(r):
    return 1200 * log2(r)

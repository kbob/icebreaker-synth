#!/usr/bin/env nmigen

def MIDI_note_to_freq(note):
    return 440 * 2**((note - 69) / 12)

assert 261 < MIDI_note_to_freq(60) < 262

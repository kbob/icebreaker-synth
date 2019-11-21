# iCEBreaker-synth

A simple audio synthesizer on the iCEBreaker FPGA.

# Minimum Viable

What's the minimum needed to get something working?

 * UART input
 * MIDI decode
 * MIDI note to frequency
 * oscillator
 * gate
 * I2S output

## UART input

31250 baud.  Should be 5V but we'll ignore that.  UART is a common
module for HDL beginners, so I should make my own.

## MIDI decode

Just need to recognize Note On and Note Off messages and store the
most recent note (or none).

N.B., MIDI running status means the first byte of each MIDI message
can be elided.  Have to store the last status byte.

A "Note On" message with velocity 0 is a synonym for "Note Off".
Some controllers use the former.

## MIDI note to frequency

This should be parameterized with the sample rate.  At a low
sample rate, it can get by with a 16 bit word; at higher rates
it will need 17-22 bits.  Maybe nMigen will be smart enough to
split the note table across multiple BRAMs.

## Oscillator

I've already got that.  See [buzzer.py](https://github.com/kbob/nmigen-examples/blob/master/lib/buzzer.py).

The oscillator needs a gate.

## I2S output

I've also got that in the nmigen-examples repository.


# How to compile

This is messy - need a better solution.  Should probably write a
global build script or something.

```sh
$ cd synth
$ PYTHONPATH=../submodules/nmigen_examples nmigen <module>.py simulate
```

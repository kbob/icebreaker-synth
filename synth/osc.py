#!/usr/bin/env nmigen

from enum import Enum, IntEnum, auto
from math import ceil, log2

from nmigen import *

from nmigen_lib.util import Main, delay
from synth import SynthConfig, MIDI_note_to_freq

MIDI_NOTES = 128
STEPS = 12 # per octave
OCTAVES = MIDI_NOTES // STEPS

def div12(n):
    """divide by 12.  Works with small integers and Signals."""
    n2 = n << 1
    n8 = n << 3
    n32 = n << 5
    n43 = n + n2 + n8 + n32
    return n43 >> 9

assert all(div12(n) == n // 12 for n in range(MIDI_NOTES))

def mul12(n):
    """multiply by 12.  Works with integers and Signals."""
    n4 = n << 2
    n8 = n << 3
    return n4 + n8

assert all(mul12(n) == 12 * n for n in range(OCTAVES))

# if counter [-1]:
#     counter = MAX
# else:
#     counter -= 1
# FSM:
#     Step IDLE:
#         rdy_out = False
#         if counter[-1]:
#             latch inputs.
#             octave = note_in // 12
#             next = MODULUS
#
#     Step MODULUS
#         step = note - 12 * octave
#         inv_octave = 10 - octave
#         next = LOOKUP
#
#     Step LOOKUP:
#         get base inc from table
#         next = MODULATE
#
#     Step MODULATE:
#         multiply base inc. by modulation.
#         next = SHIFT
#
#     Step SHIFT:
#         inc = (base_inc << octave)[-self.shift:]
#         next = ADD
#
#     Step ADD:
#         phase += inc
#         next = EMIT
#
#     Step EMIT:
#        calc saw_out = 32767 - acc
#        calc square_out = inc[-8:] >= {0, pw} ? +32767 : -32767
#        rdy_out = True
#        next = IDLE

class FSM(Enum):
    IDLE     = auto(),
    MODULUS  = auto(),
    LOOKUP   = auto(),
    MODULATE = auto(),
    SHIFT    = auto(),
    ADD      = auto(),
    EMIT     = auto(),


class Oscillator(Elaboratable):

    def __init__(self, config):
        self.divisor = config.osc_divisor
        self._calc_params(config)

        self.sync_in = Signal()
        self.note_in = Signal(range(MIDI_NOTES))
        self.mod_in = Signal(signed(16))
        self.pw_in = Signal(7, reset=~0)

        self.rdy_out = Signal()
        self.square_out = Signal(signed(config.osc_depth))
        self.saw_out = Signal(signed(config.osc_depth))

    def _calc_params(self, config):

        # This is some unreadable code right here.
        #
        # Given the oscillator's sample rate, the min and max
        # frequency depth (how many bits of frequency to use), and the
        # frequency of some MIDI notes, we can calculate how many bits
        # the phase accumulator needs to be, how many positions to
        # shift the phase increment before adding it in, and a list of
        # "base increments" (normalized for some octave).
        #
        # There is a lot of conflicting information on how well humans
        # hear pitch.  The minimum perceptible pitch is somewhere
        # between 1 cent and 20 cents. (1 cent is a ratio of
        # 2**(1/1200) to 1.)  Our best pitch discrimination is in the
        # mid range, which might be 100-2000 Hz or somewhere near
        # there.
        #
        # The oscillator has a phase accumulator.  Every sample, an
        # increment is calculated and added to the phase.  Low
        # frequencies use a small increment.  A high sample rate makes
        # the increment even smaller.  So we compromise pitch accuracy
        # at the lowest frequencies to use a smaller phase
        # accumulator.
        # 
        # `max_freq_depth` is the number of bits to use in the
        # midrange.  `min_freq_depth` is the number of bits to use
        # for the lowest notes.
        #
        # The default config is 16 bits for `max_freq_depth` and
        # 11 bits for `min_freq_depth`.  Those are both much better
        # than human perception.
        #
        # The `base_incs` are chosen to be the largest that will fit
        # in `max_freq_depth` bits.  They correspond to some octave
        # which depends on the sample rate and frequency depths.  The
        # `shift` parameter, which is usually negative, says how many
        # places to left shift the base_incs for MIDI's bottom octave
        # of notes, which are between 8 and 16 Hz.  (Negative `shift`
        # means to shift right.  Shifting right loses precision.)

        def MIDI_note_to_inc(note, phase_depth):
            f = MIDI_note_to_freq(note)
            inc = f / config.osc_rate * 2**phase_depth
            return inc

        min_fdepth = config.min_freq_depth
        max_fdepth = config.max_freq_depth
        phase_depth = max_fdepth

        inc = MIDI_note_to_inc(STEPS - 1, phase_depth)
        while inc < 2**min_fdepth:
            phase_depth += 1
            inc = MIDI_note_to_inc(STEPS - 1, phase_depth)
        shift = ceil(log2(inc)) - max_fdepth
        while inc >= 2**max_fdepth:
            inc *= 0.5
            shift += 1

        incs = [int(MIDI_note_to_inc(note, phase_depth) * 2**-shift)
                for note in range(STEPS)]

        self.phase_depth = phase_depth
        self.inc_depth = max_fdepth
        self.shift = shift
        self._base_incs = [int(i) for i in incs]

    def elaborate(self, platform):
        tick = Signal(range(-1, self.divisor - 1))
        phase = Signal(self.phase_depth)
        note = Signal.like(self.note_in)
        mod = Signal.like(self.mod_in)
        pw = Signal.like(self.pw_in)
        octave = Signal(range(OCTAVES))
        step = Signal(range(STEPS))
        base_inc = Signal(self.inc_depth)
        step_incs = Array([Signal.like(base_inc, reset=inc)
                           for inc in self._base_incs])
        inc = Signal.like(phase)

        m = Module()
        with m.If(self.sync_in):
            m.d.sync += [
                phase.eq(0),
                self.rdy_out.eq(False),
            ]
        with m.Elif(tick[-1]):
            m.d.sync += [
                tick.eq(self.divisor - 2),
            ]
        with m.Else():
            m.d.sync += [
                tick.eq(tick - 1),
            ]

        with m.FSM():

            with m.State(FSM.IDLE):
                m.d.sync += [
                    self.rdy_out.eq(False),
                ]
                with m.If(tick[-1]):
                    m.d.sync += [
                        note.eq(self.note_in),
                        mod.eq(self.mod_in),
                        pw.eq(self.pw_in),
                        octave.eq(div12(self.note_in)),
                    ]
                    m.next = FSM.MODULUS

            with m.State(FSM.MODULUS):
                m.d.sync += [
                    step.eq(note - mul12(octave)),
                ]
                m.next = FSM.LOOKUP

            with m.State(FSM.LOOKUP):
                m.d.sync += [
                    base_inc.eq(step_incs[step]),
                ]
                # m.next = FSM.MODULATE
                m.next = FSM.SHIFT

            # with m.State(FSM.MODULATE):
            #     ...
            #     m.next = FSM.SHIFT

            with m.State(FSM.SHIFT):
                m.d.sync += [
                    inc.eq((base_inc << octave)[-self.shift:]),
                ]
                m.next = FSM.ADD

            with m.State(FSM.ADD):
                m.d.sync += [
                    phase.eq(phase + inc),
                ]
                m.next = FSM.EMIT

            with m.State(FSM.EMIT):
                samp_max = 2**(self.saw_out.shape()[0] - 1) - 1
                pw8 = Cat(pw, Const(0, unsigned(1)))
                m.d.sync += [
                    self.saw_out.eq(samp_max - phase[-self.inc_depth:]),
                    self.square_out.eq(Mux(phase[-8:] <= pw8,
                                           samp_max, -samp_max)),
                    self.rdy_out.eq(True),
                ]
                m.next = FSM.IDLE

        return m


if __name__ == '__main__':
    divisor = 25
    cfg = SynthConfig(1_000_000, divisor)
    design = Oscillator(cfg)
    with Main(design).sim as sim:
        @sim.sync_process
        def note_proc():
            for _ in range(500):
                yield design.note_in.eq(24+60)
                yield
                yield design.sync_in.eq(0)
                yield from delay(divisor - 1)

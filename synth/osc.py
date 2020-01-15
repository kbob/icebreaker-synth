#!/usr/bin/env nmigen

from enum import Enum, auto
from math import ceil, log2

from nmigen import Array, Cat, Const, Elaboratable, Module, Mux, Signal
from nmigen import signed, unsigned
from nmigen.back.pysim import Passive

from nmigen_lib.pipe import PipeSpec
from nmigen_lib.util import Main, delay

from synth.config import SynthConfig
from synth.priority import voice_note_spec
from synth.util import MIDI_note_to_freq


def mono_sample_spec(width):
    return PipeSpec(signed(width))


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


class FSM(Enum):
    START    = auto()
    MODULUS  = auto()
    LOOKUP   = auto()
    MODULATE = auto()
    SHIFT    = auto()
    ADD      = auto()
    SAMPLE   = auto()
    EMIT     = auto()


class Oscillator(Elaboratable):

    def __init__(self, config):
        self.divisor = config.osc_divisor
        self._calc_params(config)

        self.sync_in = Signal()
        # self.note_in = Signal(range(MIDI_NOTES))
        self.mod_in = Signal(signed(16))
        self.pw_in = Signal(7, reset=~0)

        self.note_in = voice_note_spec.outlet()
        self.pulse_out = mono_sample_spec(config.osc_depth).inlet()
        self.saw_out = mono_sample_spec(config.osc_depth).inlet()

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
        # print(f'osc: phase_depth = {self.phase_depth}')
        # print(f'     inc_depth = {self.inc_depth}')
        # print(f'     shift = {self.shift}')


    def elaborate(self, platform):
        phase = Signal(self.phase_depth)
        note = Signal.like(self.note_in.i_data.note)
        mod = Signal.like(self.mod_in)
        pw = Signal.like(self.pw_in)
        octave = Signal(range(OCTAVES))
        step = Signal(range(STEPS))
        base_inc = Signal(self.inc_depth)
        step_incs = Array([Signal.like(base_inc, reset=inc)
                           for inc in self._base_incs])
        inc = Signal.like(phase)
        pulse_sample = Signal.like(self.pulse_out.o_data)
        saw_sample = Signal.like(self.saw_out.o_data)

        m = Module()
        with m.If(self.sync_in):
            m.d.sync += [
                phase.eq(0),
                # self.rdy_out.eq(False),
            ]

        m.d.comb += [
            self.note_in.o_ready.eq(True),
        ]
        with m.If(self.note_in.received()):
            m.d.sync += [
                note.eq(self.note_in.i_data.note),
                octave.eq(div12(self.note_in.i_data.note)),
            ]
        # Calculate pulse wave edges.  The pulse must rise and fall
        # exactly once per cycle.
        prev_msb = Signal()
        new_cycle = Signal()
        pulse_up = Signal()
        up_latch = Signal()
        pw8 = Cat(pw, Const(0, unsigned(1)))
        m.d.sync += [
            prev_msb.eq(phase[-1]),
        ]
        m.d.comb += [
            new_cycle.eq(~phase[-1] & prev_msb),
            # Widen pulse to one sample period minimum.
            pulse_up.eq(new_cycle | (up_latch & (phase[-8:] <= pw8))),
        ]
        m.d.sync += [
            up_latch.eq((new_cycle | up_latch) & pulse_up),
        ]

        with m.FSM():

            with m.State(FSM.START):
                m.d.sync += [
                    # note.eq(self.note_in),
                    mod.eq(self.mod_in),
                    pw.eq(self.pw_in),
                    # octave.eq(div12(self.note_in)),
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
                m.next = FSM.SAMPLE

            with m.State(FSM.SAMPLE):
                samp_depth = self.saw_out.o_data.shape()[0]
                samp_max = 2**(samp_depth - 1) - 1
                m.d.sync += [
                    pulse_sample.eq(Mux(pulse_up, samp_max, -samp_max)),
                    saw_sample.eq(samp_max - phase[-samp_depth:]),
                ]
                m.next = FSM.EMIT

            with m.State(FSM.EMIT):
                with m.If(self.saw_out.i_ready & self.pulse_out.i_ready):
                    m.d.sync += [
                        self.pulse_out.o_valid.eq(True),
                        self.pulse_out.o_data.eq(pulse_sample),
                        self.saw_out.o_valid.eq(True),
                        self.saw_out.o_data.eq(saw_sample),
                    ]
                    m.next = FSM.START

        with m.If(self.pulse_out.sent()):
            m.d.sync += [
                self.pulse_out.o_valid.eq(False),
            ]
        with m.If(self.saw_out.sent()):
            m.d.sync += [
                self.saw_out.o_valid.eq(False),
            ]
        return m


if __name__ == '__main__':
    divisor = 25
    cfg = SynthConfig(1_000_000, divisor)
    cfg.describe()
    design = Oscillator(cfg)
    design.note_in.leave_unconnected()
    design.pulse_out.leave_unconnected()
    design.saw_out.leave_unconnected()

    with Main(design).sim as sim:
        @sim.sync_process
        def note_proc():
            # from C5 to C7 by major thirds:
            for note in range(60 + 12, 60 + 36 + 1, 4):
                pw = (50 * note - 360) % 128
                print(f'note = {note}, pw = {pw}')
                yield design.pw_in.eq(pw)
                yield design.note_in.i_valid.eq(True)
                yield design.note_in.i_data.note.eq(note)
                for _ in range(200):
                    yield
                    yield from delay(divisor - 1)
                    yield design.note_in.i_valid.eq(False)

        @sim.sync_process
        def tick_proc():
            yield Passive()
            while True:
                yield design.pulse_out.i_ready.eq(True)
                yield design.saw_out.i_ready.eq(True)
                for i in range(cfg.osc_divisor):
                    yield
                    if (yield design.pulse_out.o_valid):
                        yield design.pulse_out.i_ready.eq(False)
                    if (yield design.saw_out.o_valid):
                        yield design.saw_out.i_ready.eq(False)

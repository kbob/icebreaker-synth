#!/usr/bin/env nmigen

from nmigen import *
from nmigen.asserts import *

from nmigen_lib.util.main import Main
from nmigen_lib.util import delay

from synth.midi import note_msg_spec


class MonoPriority(Elaboratable):

    """Choose highest priority notes for monophonic synth.

       Channel = None means merge all MIDI channels.
       use_velocity: if false, output velocity is constant at 64.
    """

    def __init__(self, channel=None, use_velocity=False):
        self.channel = channel
        self.use_velocity = use_velocity
        self.note_outlet = note_msg_spec.outlet()
        self.mono_gate = Signal()
        self.mono_note = Signal(7)
        self.mono_velocity = Signal(7)

    def elaborate(self, platform):
        i_onoff = self.note_outlet.i_data.onoff
        i_channel = self.note_outlet.i_data.channel
        i_note = self.note_outlet.i_data.note
        i_velocity = self.note_outlet.i_data.velocity

        if self.channel is None:
            channel_ok = True
        else:
            channel_ok = i_channel == self.channel

        if self.use_velocity:
            velocity = i_velocity
        else:
            velocity = Const(64)

        m = Module()
        m.d.comb += [
            self.note_outlet.o_ready.eq(True),
        ]
        with m.If(self.note_outlet.received()):
            with m.If(channel_ok):
                with m.If(i_onoff):
                    m.d.sync += [
                        self.mono_gate.eq(True),
                        self.mono_note.eq(i_note),
                        self.mono_velocity.eq(velocity),
                    ]
                with m.Elif(i_note == self.mono_note):
                    m.d.sync += [
                        self.mono_gate.eq(False),
                    ]
        return m


if __name__ == '__main__':
    design = MonoPriority(channel=3, use_velocity=True)

    # Workaround nMigen issue #280
    m = Module()
    m.submodules.design = design
    i_valid = Signal()
    i_onoff = Signal()
    i_channel = Signal(4)
    i_note = Signal(7)
    i_velocity = Signal(7)
    m.d.comb += [
        design.note_outlet.i_valid.eq(i_valid),
        design.note_outlet.i_data.onoff.eq(i_onoff),
        design.note_outlet.i_data.channel.eq(i_channel),
        design.note_outlet.i_data.note.eq(i_note),
        design.note_outlet.i_data.velocity.eq(i_velocity),
    ]

    #280 with Main(design).sim as sim:
    with Main(m).sim as sim:
        @sim.sync_process
        def sim_notes():
            notes = [
                (1, 0, 60, 100),    # wrong channel
                (1, 3, 62,  99),    # ok, play D4
                (1, 3, 64,  98),    # ok, play E4
                (1, 0, 64,  97),    # wrong channel
                (0, 3, 62,   0),    # wrong note
                (0, 3, 64,   0),    # ok, stop
            ]
            for (on, chan, key, vel) in notes:
                yield i_valid.eq(True)
                yield i_onoff.eq(on)
                yield i_channel.eq(chan)
                yield i_note.eq(key)
                yield i_velocity.eq(vel)
                yield
                yield i_valid.eq(False)
                yield from delay(3)

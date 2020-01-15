#!/usr/bin/env nmigen

from nmigen import Const, Elaboratable, Module, Signal, unsigned

from nmigen_lib.pipe import PipeSpec
from nmigen_lib.util.main import Main
from nmigen_lib.util import delay

from synth.midi import note_msg_spec


voice_note_spec = PipeSpec((
    ('note', unsigned(7)),
))

voice_gate_spec = PipeSpec((
    ('gate', unsigned(1)),
    ('velocity', unsigned(7)),
))


class MonoPriority(Elaboratable):

    """Choose highest priority notes for monophonic synth.

       Channel = None means merge all MIDI channels.
       use_velocity: if false, output velocity is constant at 64.
    """

    def __init__(self, channel=None, use_velocity=False):
        self.channel = channel
        self.use_velocity = use_velocity
        self.note_outlet = note_msg_spec.outlet()
        self.voice_note_inlet = voice_note_spec.inlet()
        self.voice_gate_inlet = voice_gate_spec.inlet()

    def elaborate(self, platform):
        i_onoff = self.note_outlet.i_data.onoff
        i_channel = self.note_outlet.i_data.channel
        i_note = self.note_outlet.i_data.note
        i_velocity = self.note_outlet.i_data.velocity

        o_vn_valid = self.voice_note_inlet.o_valid
        o_vn_note = self.voice_note_inlet.o_data.note
        o_vg_valid = self.voice_gate_inlet.o_valid
        o_vg_gate = self.voice_gate_inlet.o_data.gate
        o_vg_velocity = self.voice_gate_inlet.o_data.velocity

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
                        o_vn_valid.eq(True),
                        o_vn_note.eq(i_note),
                        o_vg_valid.eq(True),
                        o_vg_gate.eq(True),
                        o_vg_velocity.eq(velocity),
                    ]
                with m.Elif(i_note == o_vn_note):
                    m.d.sync += [
                        o_vg_valid.eq(True),
                        o_vg_gate.eq(False),
                        o_vg_velocity.eq(velocity),
                    ]
        with m.Else():
            with m.If(self.voice_note_inlet.sent()):
                m.d.sync += [
                    o_vn_valid.eq(False),
                ]
            with m.If(self.voice_gate_inlet.sent()):
                m.d.sync += [
                    o_vg_valid.eq(False),
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

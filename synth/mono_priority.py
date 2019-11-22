#!/usr/bin/env nmigen

from nmigen import *
from nmigen.asserts import *

from nmigen_lib.util.main import Main
from nmigen_lib.util import delay


class MonoPriority(Elaboratable):

    """Choose highest priority notes for monophonic synth.

       Channel = None means merge all MIDI channels.
       use_velocity: if false, output velocity is constant at 64.
    """

    def __init__(self, channel=None, use_velocity=False):
        self.channel = channel
        self.use_velocity = use_velocity
        self.note_on_rdy = Signal()
        self.note_off_rdy = Signal()
        self.note_chan = Signal(4)
        self.note_key = Signal(7)
        self.note_vel = Signal(7)
        self.mono_gate = Signal()
        self.mono_key = Signal(7)
        self.mono_vel = Signal(7)
        self.ports = [sig
                      for sig in self.__dict__.values()
                      if isinstance(sig, Signal)]

    def elaborate(self, platform):
        channel_ok = Signal()
        velocity = Signal(7)

        m = Module()
        if self.channel is None:
            m.d.comb += [
                channel_ok.eq(True),
            ]
        else:
            m.d.comb += [
                channel_ok.eq(self.note_chan == self.channel),
            ]
        if self.use_velocity:
            m.d.comb += [
                velocity.eq(self.note_vel),
            ]
        else:
            m.d.comb += [
                velocity.eq(64),
            ]

        Assert (~self.note_on_rdy | ~self.note_off_rdy)
        with m.If(self.note_on_rdy & channel_ok):
            m.d.sync += [
                self.mono_gate.eq(True),
                self.mono_key.eq(self.note_key),
                self.mono_vel.eq(velocity),
            ]
        with m.If(self.note_off_rdy & channel_ok):
            with m.If(self.note_key == self.mono_key):
                m.d.sync += [
                    self.mono_gate.eq(False),
                ]
        return m


if __name__ == '__main__':
    design = MonoPriority(channel=3, use_velocity=True)
    with Main(design).sim as sim:
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
                yield design.note_on_rdy.eq(on)
                yield design.note_off_rdy.eq(not on)
                yield design.note_chan.eq(chan)
                yield design.note_key.eq(key)
                yield design.note_vel.eq(vel)
                yield
                yield design.note_on_rdy.eq(False)
                yield design.note_off_rdy.eq(False)
                yield from delay(3)

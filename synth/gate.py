#!/usr/bin/env nmigen

from nmigen import *
from nmigen.asserts import *

from nmigen_lib.pipe import PipeSpec
from nmigen_lib.util.main import Main
from nmigen_lib.util import delay

from synth.priority import voice_gate_spec


class Gate(Elaboratable):

    """Gate a signal."""

    def __init__(self, signal_spec):
        self.gate_outlet = voice_gate_spec.outlet()
        # self.signal_outlet = signal_spec.outlet()
        self.signal_inlet = signal_spec.inlet()
        self.signal_in = Record.like(self.signal_inlet.o_data)

    def elaborate(self, platform):
        gate = Signal.like(self.gate_outlet.i_data.gate)

        # s_in = self.signal_outlet
        s_out = self.signal_inlet

        m = Module()
        m.d.comb += [
            self.gate_outlet.o_ready.eq(True),
        ]
        with m.If(self.gate_outlet.received()):
            m.d.sync += [
                gate.eq(self.gate_outlet.i_data.gate),
            ]

        m.d.comb += [
            s_out.o_valid.eq(True),     # XXX
            s_out.o_data.eq(Mux(gate, self.signal_in, 0)),

            # s_out.o_valid.eq(s_in.i_valid),
            # se_out.o_data.eq(Mux(gate, s_in.i_data, 0)),
            # s_in.o_ready.eq(s_out.i_ready),
        ]
        return m


if __name__ == '__main__':
    spec = PipeSpec((('d', signed(2)), ))
    design = Gate(spec)
    design.gate_outlet.leave_unconnected()
    design.signal_inlet.leave_unconnected()

    # Work around nMigen issue #280.
    m = Module()
    m.submodules.gate = design
    i_signal = Signal(2)
    i_valid = Signal()
    i_gate = Signal()
    i_velocity = Signal(7)
    m.d.comb += [
        design.signal_in.eq(i_signal),
        design.gate_outlet.i_valid.eq(i_valid),
        design.gate_outlet.i_data.gate.eq(i_gate),
        design.gate_outlet.i_data.velocity.eq(i_velocity),
    ]

    #280 with Main(design).sim as sim:
    with Main(m).sim as sim:
        @sim.sync_process
        def gated_count():
            s0 = g0 = g1 = 0
            for i in range(16):
                s = i % 4 - 2
                g = bool(i & 4)
                #280 yield design.signal_in.eq(s)
                #280 yield design.gate_outlet.i_valid.eq(True)
                #280 yield design.gate_outlet.i_data.gate.eq(g)
                yield i_signal.eq(s)
                yield i_valid.eq(True)
                yield i_gate.eq(g)
                yield i_velocity.eq(64)
                yield
                o = (yield design.signal_inlet.o_data)
                # assert o == (s0 if g1 else 0), f'o = {o}, s0 = {s0}, g1 = {g1}'
                s0 = s; g1 = g0; g0 = g

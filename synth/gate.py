#!/usr/bin/env nmigen

from nmigen import *
from nmigen.asserts import *

from nmigen_lib.util.main import Main
from nmigen_lib.util import delay

class Gate(Elaboratable):

    """Gate a signal."""

    def __init__(self, shape=signed(16)):
        self.signal_in = Signal(shape)
        self.gate_in = Signal()
        self.signal_out = Signal.like(self.signal_in)

    def elaborate(self, platform):
        m = Module()
        m.d.sync += [
            self.signal_out.eq(Mux(self.gate_in, self.signal_in, 0)),
        ]
        return m


if __name__ == '__main__':
    design = Gate(signed(2))
    with Main(design).sim as sim:
        @sim.sync_process
        def gated_count():
            s0 = g0 = 0
            for i in range(16):
                s = i % 4 - 2
                g = bool(i & 4)
                yield design.signal_in.eq(s)
                yield design.gate_in.eq(g)
                yield
                o = (yield design.signal_out)
                assert o == (s0 if g0 else 0), f'o = {o}, s0 = {s0}, g0 = {g0}'
                s0 = s; g0 = g

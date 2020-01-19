#!/usr/bin/env nmigen

from nmigen import Elaboratable, Module
from nmigen.asserts import Assume
from nmigen.back.pysim import Delay

from nmigen_lib.util import Main

from .i2s import stereo_sample_spec
from .osc import mono_sample_spec


class ChannelPair(Elaboratable):

    def __init__(self, sample_width):
        self.left_in = mono_sample_spec(sample_width).outlet()
        self.right_in = mono_sample_spec(sample_width).outlet()
        self.stereo_out = stereo_sample_spec(sample_width).inlet()

    def elaborate(self, platform):
        m = Module()
        m.d.comb += [
            # Assume(self.left_in.i_valid == self.right_in.i_valid),
            self.stereo_out.o_valid.eq(self.left_in.i_valid),
            self.stereo_out.o_data.left.eq(self.left_in.i_data),
            self.stereo_out.o_data.right.eq(self.right_in.i_data),
            self.left_in.o_ready.eq(self.stereo_out.i_ready),
            self.right_in.o_ready.eq(self.stereo_out.i_ready),
        ]
        m.d.sync += []
        return m


if __name__ == '__main__':
    sample_width = 4
    design = ChannelPair(4)
    design.left_in.leave_unconnected()
    design.right_in.leave_unconnected()
    design.stereo_out.leave_unconnected()

    with Main(design).sim as sim:
        sim.add_clock(1e-6, if_exists=True)

        @sim.process
        def data_proc():
            sample_mask = 2**sample_width - 1
            for i in range(10):
                left = (3 * i) & sample_mask
                right = (5 * i - 8) & sample_mask
                yield design.left_in.i_valid.eq(True)
                yield design.right_in.i_valid.eq(True)
                yield design.left_in.i_data.eq(left)
                yield design.right_in.i_data.eq(right)
                yield Delay(1e-6)
                valid = yield design.stereo_out.o_valid
                assert valid
                expected = ((left & sample_mask)
                         | ((right & sample_mask) << sample_width))
                actual = yield design.stereo_out.o_data
                assert actual == expected

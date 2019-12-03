#!/usr/bin/env nmigen

from numbers import Complex
import time

from nmigen import *
from nmigen.build import *
from nmigen_boards.icebreaker import ICEBreakerPlatform

from nmigen_lib.buzzer import Buzzer
from nmigen_lib.pll import PLL

from synth import I2STx, MIDI_note_to_freq


class Top(Elaboratable):

    def __init__(self, pll_freq=48_000_000, sample_freq=46_875, depth=16):
        self.pll_freq = pll_freq
        self.sample_freq = sample_freq
        self.depth = depth

    def elaborate(self, platform):
        i2s_pins = platform.request('i2s', 0)
        clk_pin = platform.request(platform.default_clk, dir='-')

        freq_in = platform.default_clk_frequency
        freq_in_mhz = freq_in / 1_000_000
        pll_freq_mhz = self.pll_freq / 1_000_000
        buzz_freq = MIDI_note_to_freq(60)   # Middle C

        # vars = {k: v
        #         for (k, v) in locals().items()
        #         if isinstance(v, Complex)}
        # w = len(max(vars, key=len))
        # for k in sorted(vars):
        #     print(f'{k:{w}} = {vars[k]:,}')
        # print()

        m = Module()
        pll = PLL(freq_in_mhz=freq_in_mhz, freq_out_mhz=pll_freq_mhz)
        i2s_tx = I2STx(self.pll_freq, self.sample_freq, tx_depth=self.depth)
        buzzer = Buzzer(buzz_freq, self.sample_freq, self.depth)
        m.domains += pll.domain     # override the default 'sync' domain
        m.submodules += [pll, buzzer, i2s_tx]
        m.d.comb += [
            pll.clk_pin.eq(clk_pin),
            buzzer.enable.eq(True),
            buzzer.ack.eq(i2s_tx.tx_ack),
            i2s_tx.tx_samples[0].eq(buzzer.sample),
            i2s_tx.tx_samples[1].eq(buzzer.sample),
            i2s_tx.tx_stb.eq(buzzer.stb),
            i2s_pins.eq(i2s_tx.tx_i2s),
        ]
        return m


def build_and_program(pll_freq, sample_freq, depth):
    print(f'Programming w/ PLL = {pll_freq / 1_000_000} MHz, '
          f'samples = {depth} x {sample_freq:,}')

    platform = ICEBreakerPlatform()
    platform.add_resources([
        Resource('i2s', 0,
            Subsignal('mclk', Pins('1', conn=('pmod', 0), dir='o')),
            Subsignal('lrck', Pins('2', conn=('pmod', 0), dir='o')),
            Subsignal('sck',  Pins('3', conn=('pmod', 0), dir='o')),
            Subsignal('sd',   Pins('4', conn=('pmod', 0), dir='o')),
        ),
    ])
    top = Top(pll_freq=pll_freq, sample_freq=sample_freq, depth=depth)
    platform.build(top, do_program=True)


def build_and_program_variants():
    for oversample in (1, 2, 4):
        sample_freq = oversample * 46_875
        for (depth, pll_freq) in ((16, 48_000_000), (24, 36_000_000)):
            build_and_program(pll_freq, sample_freq, depth)

if __name__ == '__main__':
    build_and_program_variants()
    # build_and_program(pll_freq=36_000_000, sample_freq=46_875, depth=24)

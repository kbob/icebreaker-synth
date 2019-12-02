#!/usr/bin/env nmigen

from math import log2

from nmigen import *
from nmigen.build import Resource
from nmigen_lib.util import Main, delay


def I2STxRecord():
    return Record([
        ('mclk', 1),
        ('lrck', 1),
        ('sck', 1),
        ('sd', 1),
    ])

def I2SRxRecord():
    raise NotImplementedError()

def PmodI2STxResource(name, number, *, pmod, extras=None):
    return Resource(name, number,
        Subsignal('mclk', Pins('1', conn=('pmod', pmod), dir='o')),
        Subsignal('lrck', Pins('2', conn=('pmod', pmod), dir='o')),
        Subsignal('sck',  Pins('3', conn=('pmod', pmod), dir='o')),
        Subsignal('sd',   Pins('4', conn=('pmod', pmod), dir='o')),
        extras=extras
    )

def PmodI2STxResource(name, number, *, pmod, extras=None):
    raise NotImplementedEror()


class I2S(Elaboratable):

    def __init__(self, clk_freq, tx_rate, rx_rate, tx_depth=16, rx_depth=16):
        self.clk_freq = clk_freq
        self.tx_rate = tx_rate
        self.rx_rate = rx_rate
        self.tx_depth = tx_depth
        self.rx_depth = rx_depth

        self.tx_samples = Array([Signal(signed(tx_depth)) for i in range(2)])
        self.tx_stb = Signal()
        self.tx_ack = Signal()
        self.tx_i2s = I2STxRecord()

        self.rx_rdy = Signal()
        self.rx_samples = Array([Signal(signed(rx_depth)) for i in range(2)])
        self.rx_i2s = I2SRxRecord()

    def elaborate(self, platform):
        m = Module()
        i2s_tx = I2STx(clk_freq, tx_rate, tx_depth)
        i2s_rx = I2SRx(clk_freq, rx_rate, rx_depth)
        m.submodules += [i2s_tx, i2s_rx]
        m.d.comb += [
            i2s_tx.tx_samples.eq(self.tx_samples),
            i2s_tx.tx_stb.eq(self.tx_stb),
            self.tx_ack.eq(i2s_tx.tx_ack),
            i2s.tx_i2s.mclk.eq(self.tx_i2s.mclk),
            i2s.tx_i2s.lrck.eq(self.tx_i2s.lrck),
            i2s.tx_i2s.sck.eq(self.tx_i2s.sck),
            i2s.tx_i2s.sd.eq(self.tx_i2s.sd),

            # RX signals not connected.  TBD.
        ]
        return m


class I2STx(Elaboratable):

    def __init__(self, clk_freq, tx_rate, tx_depth=16):
        assert tx_depth in (16, 24), (
            f'I2STx: tx_depth = {tx_depth} must be 16 or 24.'
        )
        if 2_000 <= tx_rate < 50_000:
            lrck_divisor = 256
        elif 50_000 <= tx_rate < 100_000:
            lrck_divisor = 128
        elif 100_000 <= tx_rate <= 200_000:
            lrck_divisor = 64
        else:
            assert False, (
                f'tx_rate = {tx_rate:,} must be between 2,000 and 200,000.'
            )
        if tx_depth == 24:
            lrck_divisor = lrck_divisor * 3 // 2
        mclk_freq = lrck_divisor * tx_rate
        mclk_divisor = int(clk_freq) // int(mclk_freq)
        assert mclk_divisor == clk_freq / mclk_freq, (
            f'I2STx: mclk_freq = {mclk_freq:,} must divide '
            f'clk_freq = {clk_freq:,}'
        )
        assert clk_freq > mclk_freq, (
            f'clk_freq={clk_freq:,} must be '
            f'greater than mclk_freq={mclk_freq:,}'
        )
        self.tx_depth = tx_depth
        self.clk_freq = clk_freq
        self.mclk_divisor = mclk_divisor
        self.lrck_divisor = lrck_divisor

        self.tx_samples = Array([Signal(signed(tx_depth), name='sample0'),
                                 Signal(signed(tx_depth), name='sample1')])
        self.tx_stb = Signal()
        self.tx_ack = Signal()
        self.tx_i2s = I2STxRecord()
        self.ports = [
            self.tx_samples[0],
            self.tx_samples[1],
            self.tx_stb,
            self.tx_ack,
            self.tx_i2s.mclk,
            self.tx_i2s.lrck,
            self.tx_i2s.sck,
            self.tx_i2s.sd,
        ]

    def elaborate(self, platform):

        def is_power_of_2(n):
            return n and not n & (n - 1)

        bitstream = Signal(2 * self.tx_depth)

        m = Module()

        # There are four counters.
        #
        # `fast_cnt` decrements at clk frequency, and underflows
        #   at mclk frequency.
        #
        # `slow_cnt` decrements at mclk frequency, and underflows
        #   at lrck_frequeency.
        #
        # `mcnt` increments at mclk frequency.  It is used to derive
        #   all the I2S signals in 16 bit mode, all but `lrck` in
        #   24 bit mode.
        #
        # `lr_cnt` is only present in 24-bit mode.  It is used to toggle
        #   `lrck` in 24 bit mode.  It decrements at mclk frequency,
        #   and underflows when it's time to toggle `lrck`.
        #
        lr_cnt_needed = not is_power_of_2(self.lrck_divisor)
        fast_cnt = Signal(range(-1, self.mclk_divisor - 1))
        slow_cnt = Signal(range(-1, self.lrck_divisor - 1))
        mcnt = Signal(range(self.lrck_divisor), reset=self.lrck_divisor - 2)
        if lr_cnt_needed:
            lr_cnt = Signal(range(-1, self.lrck_divisor // 2 - 1))
            pre_lrck = Signal(reset=1)

        with m.If(fast_cnt[-1]):
            m.d.sync += [
                fast_cnt.eq(self.mclk_divisor - 2),
            ]
            with m.If(slow_cnt[-1]):
                m.d.sync += [
                    slow_cnt.eq(self.lrck_divisor - 2),
                    mcnt.eq(0),
                ]
            with m.Else():
                m.d.sync += [
                    slow_cnt.eq(slow_cnt - 1),
                    mcnt.eq(mcnt + 1),
                ]
            if lr_cnt_needed:
                with m.If(lr_cnt[-1]):
                    m.d.sync += [
                        lr_cnt.eq(self.lrck_divisor // 2 - 2),
                        pre_lrck.eq(~pre_lrck),
                    ]
                with m.Else():
                    m.d.sync += [
                        lr_cnt.eq(lr_cnt - 1),
                    ]
        with m.Else():
            m.d.sync += [
                fast_cnt.eq(fast_cnt - 1),
            ]

        # Load and ack next frame at start of period.
        with m.If(slow_cnt[-1] & fast_cnt[-1]):
            m.d.sync += [
                # I2S bitstream is MSB first, so reverse bits here.
                bitstream.eq(Mux(self.tx_stb,
                                 Cat(self.tx_samples[0][::-1],
                                     self.tx_samples[1][::-1]),
                                 0)),
                self.tx_ack.eq(self.tx_stb),
            ]
        with m.Else():
            m.d.sync += [
                self.tx_ack.eq(False),
            ]

        sck_bit = -7 if lr_cnt_needed else -6
        m.d.sync += [
            self.tx_i2s.mclk.eq(mcnt[0]),
            self.tx_i2s.sck.eq(mcnt[sck_bit]),
            self.tx_i2s.sd.eq(bitstream.bit_select(mcnt[sck_bit + 1:], 1)),
            self.tx_i2s.lrck.eq(pre_lrck if lr_cnt_needed else mcnt[-1]),
        ]
        return m


class I2SRx(Elaboratable):

    def __init__(self, clk_freq, mclk_divisor, rx_depth=16):
        raise NotImplementedError()

    def elaborate(self, platform):
        ...


if __name__ == '__main__':
    design = I2STx(48_000_000, 46_875, tx_depth=16)
    # design = I2STx(72_000_000, 46_875, tx_depth=24)
    # design = I2STx(48_000_000, 2 * 46_875, tx_depth=16)
    # design = I2STx(72_000_000, 2 * 46_875, tx_depth=24)
    # design = I2STx(48_000_000, 4 * 46_875, tx_depth=16)
    # design = I2STx(72_000_000, 4 * 46_875, tx_depth=24)
    with Main(design).sim as sim:
        sim.add_clock(1 / design.clk_freq, domain='sync')
        @sim.sync_process
        def tx_proc():
            left = 0; right = 100
            for i in range(24):
                yield design.tx_samples[0].eq(left)
                yield design.tx_samples[1].eq(right)
                yield design.tx_stb.eq(True)
                left += 3; right += 5
                while (yield design.tx_ack) == False:
                    yield
                yield design.tx_stb.eq(False)
                yield

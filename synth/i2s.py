#!/usr/bin/env nmigen

from numbers import Complex

from nmigen import Array, Cat, Const, Elaboratable, Module, Mux, Record
from nmigen import Signal, signed
from nmigen.build import Resource

from nmigen_lib.pipe import PipeSpec
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


def stereo_sample_spec(width=16):
    return PipeSpec((
        ('left', signed(width)),
        ('right', signed(width)),
    ))


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


class P_I2STx(Elaboratable):

    # def __init__(self, clk_freq, tx_rate, tx_depth=16):
    def __init__(self, cfg):
        self.clk_freq = cfg.clk_freq
        self.tx_rate = cfg.out_rate
        self.tx_depth = cfg.out_depth
        assert cfg.out_channels == 2

        self.sample_outlet = stereo_sample_spec(self.tx_depth).outlet()
        self.tx_i2s = I2STxRecord()

    def elaborate(self, platform):
        sample = Record.like(self.sample_outlet.i_data)

        m = Module()
        i2s_tx = I2STx(self.clk_freq, self.tx_rate, self.tx_depth)
        m.submodules.i2s_tx = i2s_tx
        m.d.comb += [
            i2s_tx.tx_stb.eq(True),
            i2s_tx.tx_samples[0].eq(sample.left),
            i2s_tx.tx_samples[1].eq(sample.right),
            self.tx_i2s.eq(i2s_tx.tx_i2s),
        ]
        with m.If(i2s_tx.tx_ack):
            m.d.sync += [
                self.sample_outlet.o_ready.eq(True),
            ]
        with m.If(self.sample_outlet.received()):
            m.d.sync += [
                self.sample_outlet.o_ready.eq(False),
                sample.eq(self.sample_outlet.i_data),
            ]
        return m


class I2STx(Elaboratable):

    def __init__(self, clk_freq, tx_rate, tx_depth=16):

        """I2S transmit side.  Generate an I2S stereo audio stream.

           tx_rate can be between 2KHz and 200KHz, but is restricted to
           specific fractions of clk_freq.  tx_depth can be either 16
           or 24 bits.

           This module will pick the "best" mode for the Cirrus CS4344
           based on tx_rate and tx_depth.
        """

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
        assert mclk_divisor // 2 == clk_freq / mclk_freq / 2, (
            f'I2STx: 2 * mclk_freq = {2 * mclk_freq:,} must divide '
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

        # # Print all the variables.
        # d = self.__dict__; d.update(locals())
        # vars = {k: v
        #         for (k, v) in d.items()
        #         if isinstance(v, Complex)}
        # w = len(max(vars, key=len))
        # for k in sorted(vars):
        #     print(f'{k:{w}} = {vars[k]:,}')
        # print()

        self.tx_samples = Array([Signal(signed(tx_depth), name='sample0'),
                                 Signal(signed(tx_depth), name='sample1')])
        self.tx_stb = Signal()
        self.tx_ack = Signal()
        self.tx_i2s = I2STxRecord()

    def elaborate(self, platform):
        bitstream = Signal(2 * self.tx_depth)
        pre_sd = Signal()
        sd = Signal()

        m = Module()

        # There are four counters.
        #
        # `fast_cnt` decrements at clk frequency and underflows at mclk
        #   frequency.  `fast_clk` is only needed/possible if mclk
        #   frequency is less than clk_freq.  It is used to advance
        #   `slow_cnt` and `mcnt`.
        #
        # `slow_cnt` decrements at twice mclk frequency and underflows
        #   at lrck_frequency.  It is used to reset `mcnt` each
        #   lrck period.
        #
        # `mcnt` increments at twice mclk frequency.  It is used to
        #   derive all the I2S signals in 16 bit mode and all except
        #  `lrck` in 24 bit mode.
        #
        # `lr_cnt` is only present in 24-bit mode.  It is used to toggle
        #   `lrck` in 24 bit mode.  It decrements at twice mclk
        #   frequency, and underflows when it's time to toggle `lrck`.
        #   In 16-bit mode, `lrck` is simply the high bit of `mcnt`.
        #
        fast_cnt_needed = self.mclk_divisor >= 2
        if fast_cnt_needed:
            fast_max = self.mclk_divisor // 2 - 2
            fast_cnt = Signal(range(-1, fast_max + 1))
            slow_inc = Signal()
            with m.If(fast_cnt[-1]):
                m.d.sync += [
                    fast_cnt.eq(fast_max),
                    slow_inc.eq(True),
                ]
            with m.Else():
                m.d.sync += [
                    fast_cnt.eq(fast_cnt - 1),
                    slow_inc.eq(False),
                ]
        else:
            slow_inc = True

        slow_max = 2 * self.lrck_divisor - 2
        slow_cnt = Signal(range(-1, slow_max + 1))
        mcnt_max = 2 * self.lrck_divisor - 1
        mcnt = Signal(range(mcnt_max + 1), reset=mcnt_max)
        with m.If(slow_inc):
            with m.If(slow_cnt[-1]):
                m.d.sync += [
                    slow_cnt.eq(slow_max),
                    mcnt.eq(0),
                ]
            with m.Else():
                m.d.sync += [
                    slow_cnt.eq(slow_cnt - 1),
                    mcnt.eq(mcnt + 1),
                ]

        lr_cnt_needed = self.tx_depth == 24
        if lr_cnt_needed:
            lr_cnt_max = self.lrck_divisor - 2
            lr_cnt = Signal(range(-1, lr_cnt_max + 1))
            pre_lrck = Signal(reset=1)
            with m.If(slow_inc):
                with m.If(lr_cnt[-1]):
                    m.d.sync += [
                        lr_cnt.eq(lr_cnt_max),
                        pre_lrck.eq(~pre_lrck),
                    ]
                with m.Else():
                    m.d.sync += [
                        lr_cnt.eq(lr_cnt - 1),
                    ]

        # Load and ack next frame at start of period.
        with m.If(slow_cnt[-1] & slow_inc):
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

        # The SD signal needs to be delayed by one SCK period.
        # So the LSB is actually sent after LRCK has transitioned.
        # This is apparently how I2S works.
        sck_bit = -7 if lr_cnt_needed else -6
        with m.If(fast_cnt[-1] & (~mcnt[:sck_bit + 1] == 0)):
            m.d.sync += [
                sd.eq(bitstream.bit_select(mcnt[sck_bit + 1:], 1))
            ]
        m.d.sync += [
            self.tx_i2s.mclk.eq(mcnt[0]),
            self.tx_i2s.sck.eq(mcnt[sck_bit]),
            self.tx_i2s.sd.eq(sd),
            self.tx_i2s.lrck.eq(pre_lrck if lr_cnt_needed else mcnt[-1]),
        ]
        return m


class I2SRx(Elaboratable):

    def __init__(self, clk_freq, mclk_divisor, rx_depth=16):
        raise NotImplementedError("I'm not writing it.  YOU write it.")

    def elaborate(self, platform):
        ...


if __name__ == '__main__':
    design = P_I2STx(48_000_000, 46_875, tx_depth=16)
    # design = I2STx(72_000_000, 46_875, tx_depth=24)
    # design = I2STx(48_000_000, 2 * 46_875, tx_depth=16)
    # design = I2STx(72_000_000, 2 * 46_875, tx_depth=24)
    # design = I2STx(48_000_000, 4 * 46_875, tx_depth=16)
    # design = I2STx(72_000_000, 4 * 46_875, tx_depth=24)
    design.sample_outlet.leave_unconnected()

    # Work around nMigen issue #280
    m = Module()
    m.submodules.p_i2s_tx = design
    i_valid = Signal()
    i_data = Signal.like(design.sample_outlet.i_data)
    m.d.comb += [
        design.sample_outlet.i_valid.eq(i_valid),
        design.sample_outlet.i_data.eq(i_data),
    ]

    # 280 with Main(design).sim as sim:
    with Main(m).sim as sim:
        sim.add_clock(1 / design.clk_freq, domain='sync')

        # # Simulate the non-pipe TX.
        # @sim.sync_process
        # def tx_proc():
        #     left = 0; right = 100
        #     for i in range(24):
        #         yield design.tx_samples[0].eq(left)
        #         yield design.tx_samples[1].eq(right)
        #         yield design.tx_stb.eq(True)
        #         left += 3; right += 5
        #         while (yield design.tx_ack) == False:
        #             yield
        #         yield design.tx_stb.eq(False)
        #         yield

        # Simulate the pipe TX.
        @sim.sync_process
        def tx_proc():
            left = 0; right = 100
            s = signed(design.tx_depth)
            for i in range(24):
                yield i_valid.eq(True)
                yield i_data.eq(Cat(Const(left, s), Const(right, s)))
                left += 3; right += 5
                while (yield design.sample_outlet.o_ready) == False:
                    yield
                yield i_valid.eq(False)
                yield

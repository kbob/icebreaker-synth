#!/usr/bin/env nmigen

from math import ceil, floor, log2, pi, tau

import numpy as np

from nmigen import Array, Cat, Const, Elaboratable, Memory, Module, Signal
from nmigen import signed, unsigned
from nmigen.asserts import Assert
from nmigen.back.pysim import Passive

from nmigen_lib.util import Main, delay

from .config import SynthConfig
from .osc import mono_sample_spec

# Coefficient size is hardcoded to 16 bit signed.
COEFF_WIDTH = 16
COEFF_SHAPE = signed(COEFF_WIDTH)
COEFF_MIN = -(2**(COEFF_WIDTH - 1))
COEFF_MAX = 1 - COEFF_MIN

def _is_power_of_2(n):
    return n and not n & (n - 1)

# unit test.
powers = {2**i for i in range(20)}
assert all(_is_power_of_2(n) for n in powers)
assert not any(_is_power_of_2(n) for n in range(1000) if n not in powers)
del powers


# See dspguide.com chapter 16 for windowed sinc filter info.
# See earlevel.com for polyphase filter based resampling.
# The code structure is based on ZipCPU's tutorials:
#     https://zipcpu.com/tutorial/lsn-10-fifo.pdf
#     https://zipcpu.com/dsp/2017/12/30/slowfil.html
#     https://zipcpu.com/blog/2017/08/14/strategies-for-pipelining.html

class Decimator(Elaboratable):

    def __init__(self, cfg, M=None, pass_freq=20_000):
        self.clk_freq = cfg.clk_freq
        self.sample_depth = cfg.osc_depth
        self.in_rate = cfg.osc_rate
        self.out_rate = cfg.out_rate
        assert cfg.osc_depth == 16
        assert cfg.out_depth == 16
        self.R = cfg.osc_rate // cfg.out_rate
        if M is None:
            # Quantization noise is objectionable for kernels above 128 taps.
            Mp2 = min(128, 2**(floor(log2(cfg.clk_freq // cfg.out_rate)) - 1))
            M = Mp2 - 2
        BW = 4 / M
        Fp = pass_freq / cfg.osc_rate
        Fc = Fp + BW / 2
        self.M = M
        self.BW = BW
        self.Fp = Fp
        self.Fc = Fc
        self._make_kernel()

        # R: decimation ratio.
        # M: convolution kernel size.  Chosen to be 2**n - 2.
        # Fp: pass frequency.  Typically 20 KHz.
        # BW: transition band width as a fraction of osc. Fs.
        # Fc: cutoff frequency.  Where filter attenuates to 0.5.
        # shift: number of LSBs to discard in output samples.
        # acc_width: number of bits in accumulator.
        # kernel: convolution kernel.
        if cfg.verbose:
            Fc_KHz = Fc * cfg.osc_rate / 1000
            print(f'Decimator:')
            print(f'    R         = {self.R:,}')
            print(f'    M         = {self.M:,}')
            print(f'    Fp        = {self.Fp:,.4}')
            print(f'    BW        = {self.BW:,.4}')
            print(f'    Fc        = {self.Fc:,.4} = {Fc_KHz:,.4} KHz')
            print(f'    shift     = {self.shift}')
            print(f'    acc_width = {self.acc_width}')
            print(f'    kernel    = ', end='')
            with np.printoptions(linewidth=75-16):
                print(str(self.kernel).replace('\n', '\n' + 16 * ' '))
            print()
        assert _is_power_of_2(M + 2), 'M must be 2**n - 2'
        assert self.R < self.M
        assert Fp + BW <= 0.5

        self.samples_in = mono_sample_spec(cfg.osc_depth).outlet()
        self.samples_out = mono_sample_spec(cfg.osc_depth).inlet()

    def _make_kernel(self):
        # Make a windowed sinc filter kernel.
        M = self.M
        Fc = self.Fc
        x = np.linspace(-Fc * M, +Fc * M, M + 1)
        sinc_x = np.sinc(x)
        window = np.blackman(M + 1)
        kernel = sinc_x + window

        # Prepend a zero coefficient to make the kernel 2**n long.
        kernel = np.append([0], kernel)
        assert _is_power_of_2(len(kernel))

        # Scale the kernel for maximum resolution.
        # First, scale it so the total kernel weight is 1.0.
        # Then, scale by a power of 2 so the coefficients are as large
        # as possible.  (Assume signed 16 bit coefficients.)
        kernel /= 1.01 * kernel.sum()

        peak = max(kernel)
        assert peak == kernel[M//2 + 1]
        shift = 0
        while 2 * peak <= COEFF_MAX:
            peak *= 2
            shift += 1

        kernel = (kernel * 2**shift).astype(np.int16)

        # # Is the kernel bigger than necessary?
        # nz = np.nonzero(kernel)[0]
        # print(f'first {nz[0]} kernel entries are zero.')
        # print(f'last {len(kernel) - nz[-1] - 1} kernel entries are zero.')
        # print(f'{M + 2 - len(nz)} kernel entries are zero.')
        # print(kernel)

        # Calculate how big the accumulator has to be.  In the worst
        # case, all samples multiplied by positive kernel coefficients
        # would be -32768, and all samples multiplied by negative
        # coefficients would be +32767.
        worst = ((COEFF_MAX + (kernel < 0)) * np.abs(kernel)).sum()
        acc_width = ceil(log2(worst))

        # if self._verbose:
        #     print(f'Decimator:')
        #     print(f'    shift     = {shift}')
        #     print(f'    acc_width = {acc_width}')
        #     print(f'    kernel    = ', end='')
        #     with np.printoptions(linewidth=75-16):
        #         print(str(kernel).replace('\n', '\n' + 16 * ' '))
        #     print()

        self.kernel = [int(c) for c in kernel]
        self.shift = shift
        self.acc_width = acc_width

    def elaborate(self, platform):

        m = Module()

        # N is size of RAMs.
        N = self.M + 2
        assert _is_power_of_2(N)

        # kernel_RAM is a buffer of convolution kernel coefficents.
        # It is read-only.  The 0'th element is zero, because the kernel
        # has length N-1.
        kernel_RAM = Memory(width=COEFF_WIDTH, depth=256, init=kernel)
        # kernel_RAM = Memory(width=COEFF_WIDTH, depth=N, init=kernel)
        m.submodules.kr_port = kr_port = kernel_RAM.read_port()

        # sample_RAM is a circular buffer for incoming samples.
        # sample_RAM = Array(
        #     Signal(signed(self.sample_depth), reset_less=True, reset=0)
        #     for _ in range(N)
        # )
        sample_RAM = Memory(width=self.sample_depth, depth=N, init=[0] * N)
        m.submodules.sw_port = sw_port = sample_RAM.write_port()
        m.submodules.sr_port = sr_port = sample_RAM.read_port()

        # The rotors index through sample_RAM.  They have an extra MSB
        # so we can distinguish between buffer full and buffer empty.
        #
        #   w_rotor: write rotor.  Points to the next entry to be written.
        #   s_rotor: start rotor.  Points to the oldest valid entry.
        #   r_rotor: read rotor.  Points to the next entry to be read.
        #
        # The polyphase decimator reads each sample N / R times, so
        # `r_rotor` is **NOT** the oldest needed sample.  Instead,
        # `s_rotor` is the oldest.  `s_rotor` is incremented by `R`
        # at the start of each convolution.
        #
        # We initialize the rotors so that the RAM contains N-1 zero samples,
        # and `r_rotor` is pointing to the first sample to be used.
        # The convolution engine can start immediately and produce a zero
        # result.
        w_rotor = Signal(range(2 * N), reset=N)
        s_rotor = Signal(range(2 * N), reset=1)
        r_rotor = Signal(range(2 * N), reset=1)

        # `c_index` is the next kernel coefficient to read.
        # `c_index` == 0 indicates done, so start at 1.
        c_index = Signal(range(N), reset=1)     # kernel coefficient index

        # Useful conditions
        buf_n_used = Signal(range(N + 1))
        buf_is_empty = Signal()
        buf_is_full = Signal()
        buf_n_readable = Signal(range(N + 1))
        buf_has_readable = Signal()
        m.d.comb += [
            buf_n_used.eq(w_rotor - s_rotor),
            buf_is_empty.eq(buf_n_used == 0),
            buf_is_full.eq(buf_n_used == N),
            buf_n_readable.eq(w_rotor - r_rotor),
            buf_has_readable.eq(buf_n_readable != 0),
            # Assert(buf_n_used <= N),
            # Assert(buf_n_readable <= buf_n_used),
        ]

        # put incoming samples into sample_RAM.
        m.d.comb += [
            self.samples_in.o_ready.eq(~buf_is_full),
            sw_port.addr.eq(w_rotor[:-1]),
            sw_port.data.eq(self.samples_in.i_data),
        ]
        m.d.sync += sw_port.en.eq(self.samples_in.received())
        with m.If(self.samples_in.received()):
            m.d.sync += [
                # sample_RAM[w_rotor[:-1]].eq(self.samples_in.i_data),
                w_rotor.eq(w_rotor + 1),
            ]

        # The convolution is pipelined.
        #
        #   stage 0: fetch coefficient and sample from their RAMs.
        #   stage 1: multiply coefficient and sample.
        #   stage 2: add product to accumulator.
        #   stage 3: if complete, try to send accumulated sample.
        #
        p_valid = Signal(4)
        p_ready = Array(
            Signal(name=f'p_ready{i}', reset=True)
            for i in range(4)
        )
        p_complete = Signal(4)
        m.d.sync += [
            p_valid[1:].eq(p_valid[:-1]),
            p_ready[0].eq(p_ready[1]),
            p_ready[1].eq(p_ready[2]),
            p_ready[2].eq(p_ready[3]),
        ]

        # calculation variables
        coeff = Signal(COEFF_SHAPE)
        sample = Signal(signed(self.sample_depth))
        prod = Signal(signed(COEFF_WIDTH + self.sample_depth))
        acc = Signal(signed(self.acc_width))

        # Stage 0.
        en0 = Signal()
        m.d.comb += en0.eq(buf_has_readable & p_ready[0] * (c_index != 0))

        # with m.If(en0):
        #     m.d.sync += [
        #         coeff.eq(kernel_RAM[c_index]),
        #     ]
        m.d.comb += coeff.eq(kr_port.data)
        with m.If(en0):
            m.d.sync += [
                sample.eq(sample_RAM[r_rotor[:-1]]),
            ]
        with m.If(en0):
            m.d.sync += [
                c_index.eq(c_index + 1),
                r_rotor.eq(r_rotor + 1),
                p_valid[0].eq(True),
                p_complete[0].eq(False),
                # kr_port.addr.eq(c_index + 1),
            ]
        m.d.comb += kr_port.addr.eq(c_index)
        # with m.If(buf_has_readable & p_ready[0] & (c_index != 0)):
        #     m.d.sync += [
        #         coeff.eq(kernel_RAM[c_index]),
        #         sample.eq(sample_RAM[r_rotor[:-1]]),
        #         c_index.eq(c_index + 1),
        #         r_rotor.eq(r_rotor + 1),
        #         p_valid[0].eq(True),
        #         p_complete[0].eq(False),
        #     ]
        with m.If((~buf_has_readable | ~p_ready[0]) & (c_index != 0)):
            m.d.sync += [
                p_valid[0].eq(False),
                p_complete[0].eq(False),
            ]
        # When c_index is zero, all convolution samples have been read.
        # Set up the rotors for the next sample.  (and pause the
        # pipelined calculation.)
        with m.If(c_index == 0):
            m.d.sync += [
                c_index.eq(c_index + 1),
                s_rotor.eq(s_rotor + self.R),
                r_rotor.eq(s_rotor + self.R),
                p_valid[0].eq(False),
                p_complete[0].eq(True),
            ]


        # Stage 1.
        with m.If(p_valid[1] & p_ready[1]):
            m.d.sync += [
                prod.eq(coeff * sample),
                p_complete[1].eq(p_complete[0]),
            ]

        # Stage 2.
        with m.If(p_valid[2] & p_ready[2]):
            m.d.sync += [
                acc.eq(acc + prod),
                p_complete[2].eq(p_complete[1]),
            ]

        # Stage 3.
        m.d.comb += p_ready[3].eq(~self.samples_out.full())
        m.d.sync += p_complete[3].eq(p_complete[3] | p_complete[2])
        with m.If(p_valid[3] & p_ready[3] & p_complete[2]):
            m.d.sync += [
                self.samples_out.o_valid.eq(1),
                self.samples_out.o_data.eq(acc[self.shift:]),
                acc.eq(0),
                p_complete[3].eq(False),
            ]

        with m.If(self.samples_out.sent()):
            m.d.sync += [
                self.samples_out.o_valid.eq(0),
            ]





        # # s_in_index = Signal(range(2 * N), reset=N)
        # # s_out_index = Signal(range(2 * N), reset=self.R + 1)
        # # c_index = Signal(range(N), reset=1)
        # # start_index = Signal(range(2 *  N), reset=self.R)
        # s_in_index = Signal(range(2 * N), reset=N)
        # s_out_index = Signal(range(2 * N))
        # c_index = Signal(range(N))
        # start_index = Signal(range(2 *  N))
        #
        # coeff = Signal(signed(16))
        # sample = Signal(signed(self.sample_depth))
        # prod = Signal(signed(2 * self.sample_depth))
        # acc = Signal(signed(self.acc_width))
        #
        # m = Module()
        #
        # n_full = (s_in_index - start_index - 1)[:s_in_index.shape()[0]]
        # n_avail = (s_in_index - s_out_index)[:-1]
        # print(f's_in_index shape = {s_in_index.shape()}')
        # print(f'start_index shape = {start_index.shape()}')
        # print(f'n_full shape = {n_full.shape()}')
        # print(f'n_avail shape = {n_avail.shape()}')
        # full = Signal(n_full.shape())
        # avail = Signal(n_avail.shape())
        # m.d.comb += full.eq(n_full)
        # m.d.comb += avail.eq(n_avail)
        #
        #
        # # input process stores new samples in the ring buffer.
        # # with m.If(self.samples_in.received()):
        # #     m.d.sync += [
        # #         sample_RAM[s_in_index[:-1]].eq(self.samples_in.i_data),
        # #     ]
        # with m.If(self.samples_in.received()):
        #     m.d.sync += [
        #         sample_RAM[s_in_index[:-1]].eq(self.samples_in.i_data),
        #         s_in_index.eq(s_in_index + 1),
        #     ]
        # m.d.sync += [
        #     self.samples_in.o_ready.eq(n_full < N),
        # ]
        #
        # # convolution process
        # sample_ready = Signal()
        # sample_ready = n_avail > 0
        #
        # # with m.If(c_index == 1):
        # #     with m.If(sample_ready):
        # #         m.d.sync += [
        # #             start_index.eq(start_index + self.R),
        # #             s_out_index.eq(start_index + self.R + 1),
        # #         ]
        # #     with m.Else():
        # #         with m.If(sample_ready):
        # #             m.d.sync += [
        # #                 s_out_index.eq(s_out_index + 1),
        # #          ]
        # # with m.Else():
        # #     with m.If(sample_ready):
        # #         m.d.sync += [
        # #             s_out_index.eq(s_out_index + 1),
        # #         ]
        #
        # with m.If(sample_ready):
        #     with m.If(c_index == 1):
        #         m.d.sync += [
        #             start_index.eq(start_index + self.R),
        #             s_out_index.eq(start_index + self.R + 1),
        #         ]
        #     with m.Else():
        #         m.d.sync += [
        #             s_out_index.eq(s_out_index + 1),
        #         ]
        #
        # with m.If(c_index == 2):
        #     with m.If(~self.samples_out.full()):
        #         m.d.sync += [
        #             self.samples_out.o_valid.eq(True),
        #             self.samples_out.o_data.eq(acc[self.shift:]),
        #             acc.eq(0),
        #             c_index.eq(c_index + 1),
        #         ]
        # with m.Else():
        #     with m.If(sample_ready):
        #         m.d.sync += [
        #             acc.eq(acc + prod),
        #             c_index.eq(c_index + 1),
        #         ]
        #
        # with m.If(sample_ready):
        #     m.d.sync += [
        #         prod.eq(coeff * sample),
        #     ]
        #
        # with m.If(sample_ready):
        #     m.d.sync += [
        #         coeff.eq(kernel_RAM[c_index]),
        #     ]
        #
        # with m.If(sample_ready):
        #     m.d.sync += [
        #         sample.eq(sample_RAM[s_out_index]),
        #     ]
        #
        # with m.If(self.samples_out.sent()):
        #     m.d.sync += [
        #         self.samples_out.o_valid.eq(False),
        #     ]
        # # # convolution process
        # # if c_index == 0:
        # #     if sample_ready:
        # #         start_index += R
        # #         s_out_index = start_index + R + 1
        # # else:
        # #     if sample_ready:
        # #         s_out_index += 1
        # #
        # # if c_index == 1:
        # #     if not out_full:
        # #         out_sample = acc[shift:]
        # #         out_valid = True
        # #         acc = 0
        # #         c_index += 1
        # # else
        # #     if sample_ready:
        # #         acc += prod
        # #         c_index += 1
        # #
        # # if sample_ready:
        # #     prod = coeff * sample
        # #
        # # if sample_ready:
        # #    coeff = kernel_RAM[c_index]
        # #
        # # if sample_ready:
        # #    sample = sample_RAM[s_out_index]
        #
        # # # convolution process
        # # fill = Signal(range(N + 1))
        # # m.d.comb += fill.eq(s_in_index - s_out_index)
        # # with m.FSM():
        # #
        # #     with m.State('RUN'):
        # #         # when s_out_index MSB is zero, sample is ready.
        # #         # when MSB is one, test out_idx < in_idx.
        # #         # extended_in_index = Cat(s_in_index, 1)
        # #         sample_ready = (fill > 0) & (fill <= N)
        # #         # sample_ready = s_out_index < extended_in_index
        # #         # xii = Signal.like(s_out_index)
        # #         sr = Signal()
        # #         # m.d.comb += xii.eq(extended_in_index)
        # #         m.d.comb += sr.eq(sample_ready)
        # #         with m.If(sample_ready):
        # #             m.d.sync += [
        # #                 acc.eq(acc + prod),   # sign extension is automatic
        # #                 prod.eq(coeff * sample),
        # #                 coeff.eq(kernel_RAM[c_index]),
        # #                 sample.eq(sample_RAM[s_out_index[:-1]]),
        # #                 c_index.eq(c_index + 1),
        # #                 s_out_index.eq(s_out_index + 1),
        # #             ]
        # #             with m.If(c_index == 0):
        # #                 m.next = 'DONE'
        # #         with m.If(self.samples_out.sent()):
        # #             m.d.sync += [
        # #                 self.samples_out.o_valid.eq(False),
        # #             ]
        # #
        # #     with m.State('DONE'):
        # #         with m.If(~self.samples_out.full()):
        # #             m.d.sync += [
        # #                 self.samples_out.o_valid.eq(True),
        # #                 self.samples_out.o_data.eq(acc[self.shift:]),
        # #                 c_index.eq(1),
        # #                 start_index.eq(start_index + self.R),
        # #                 # s_out_index[:-1].eq(start_index + self.R + 1),
        # #                 # s_out_index[-1].eq(0),
        # #                 s_out_index.eq(start_index + self.R + 1),
        # #                 coeff.eq(0),
        # #                 sample.eq(0),
        # #                 prod.eq(0),
        # #                 acc.eq(0),
        # #             ]
        # #             m.next = 'RUN'
        #
        #
        # # i_ready = true
        # # if received:
        # #     sample_RAM[in_index] = samples_in.i_data
        # #     in_index += 1
        # #
        # # FSM:
        # #     start:
        # #         if start_index + cv_index < in_index:  <<<<< Wrong
        # #             acc += sign_extend(prod)
        # #             prod = coeff * sample
        # #             coeff = kernel_RAM[cv_index]
        # #             sample = sample_RAM[(start_index + cv_index)[:-1]]
        # #
        # #             if cv_index + 1 == 0:
        # #                 goto done
        # #
        # #     done:
        # #         o_valid = true
        # #         o_data = acc[shift:shift + 16]
        # #         acc = 0
        # #         start_index = (start_index + R) % Mp2
        # #         cv_index = 0
        # #         prod = 0
        # #         coeff = 0
        # #         sample = 0
        # #
        # # if sent:
        # #     o_valid = false

        return m


if __name__ == '__main__':
    M = None
    # M = 14
    # cfg = SynthConfig(5.12e6, osc_oversample=4)
    cfg = SynthConfig(48e6, osc_oversample=32, out_oversample=4)
    # cfg = SynthConfig(24e6, osc_oversample=8, out_oversample=2)
    cfg.describe()
    design = Decimator(cfg, M=M)
    design.samples_in.leave_unconnected()
    design.samples_out.leave_unconnected()
    M = design.M
    N = M + 2
    R = design.R

    # Work around nMigen issue #280
    i_valid = Signal.like(design.samples_in.i_valid)
    i_data = Signal.like(design.samples_in.i_data)
    i_ready = Signal.like(design.samples_out.i_ready)
    m = Module()
    m.submodules.design = design
    m.d.comb += [
        design.samples_in.i_valid.eq(i_valid),
        design.samples_in.i_data.eq(i_data),
        design.samples_out.i_ready.eq(i_ready),
    ]

    #280 with Main(design).sim as sim:
    with Main(m).sim as sim:
        sim.add_clock(1 / cfg.clk_freq, domain='sync')
        @sim.sync_process
        def sample_in_process():

            def send_sample(x):
                #280 yield design.samples_in.i_valid.eq(True)
                #280 yield design.samples_in.i_data.eq(x)
                yield i_valid.eq(True)
                yield i_data.eq(x)
                yield
                for i in range(N+2):
                    if (yield design.samples_in.received()):
                        break
                    yield
                #280 yield design.samples_in.i_valid.eq(False)
                yield i_valid.eq(False)

            R = cfg.osc_rate // cfg.out_rate
            assert isinstance(R, int)
            yield from delay(3)
            # for i in range(200):
            #     x = i == 10 and 32767 or i
            #     x = i
            #     yield from send_sample(x)
            #     yield from delay(R - 1)
            freq = 1000
            nsamp_in = int(4 * cfg.osc_rate // freq)
            for i in range(nsamp_in):
                from math import sin, tau
                y = sin(tau * i * freq / cfg.osc_rate)
                y *= 0.95
                y = (y + 1) % 1
                y = 2 * y - 1
                y = int(32767 * y)
                yield from send_sample(y)
                yield from delay(R - 1)
            # with open('/tmp/foo') as foo:
            #     for line in foo:
            #         if line == 'end\n':
            #             break
            #         x = float(line)
            #         x = min(+1, max(-1, x))
            #         x = int(32767 * x)
            #         yield from send_sample(x)
            #         yield from delay(R - 1)

        @sim.sync_process
        def sample_out_process():

            def recv_sample():
                #280 yield design.samples_out.i_ready.eq(True)
                yield i_ready.eq(True)
                for i in range(N + 2):
                    yield
                    if (yield design.samples_out.o_valid):
                        break
                #280 yield design.samples_out.i_ready.eq(False)
                yield i_ready.eq(False)

            yield Passive()
            while True:
                yield from recv_sample()
                yield from delay(M)

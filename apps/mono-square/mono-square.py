#!/usr/bin/env nmigen

from nmigen import Cat, Elaboratable, Module, Signal, unsigned
from nmigen.build import Attrs, Pins, Resource, Subsignal
from nmigen_boards.icebreaker import ICEBreakerPlatform
from nmigen_boards.resources import UARTResource

from nmigen_lib import PLL
from nmigen_lib.pipe import Pipeline
from nmigen_lib.pipe.uart import P_UARTRx
from nmigen_lib.seven_segment.digit_pattern import DigitPattern
from nmigen_lib.seven_segment.driver import SevenSegDriver

from synth import Gate, P_I2STx, MIDIDecoder, MonoPriority
from synth import Oscillator, SynthConfig, stereo_sample_spec


class OneShot(Elaboratable):

    def __init__(self, duration):
        self.duration = duration
        self.trg = Signal()
        self.out = Signal()
        self.ports = (self.trg, self.out)

    def elaborate(self, platform):
        counter = Signal(range(-1, self.duration))
        m = Module()
        with m.If(self.trg):
            m.d.sync += [
                counter.eq(self.duration - 2),
                self.out.eq(True),
            ]
        with m.Elif(counter[-1]):
            m.d.sync += [
                self.out.eq(False),
            ]
        with m.Else():
            m.d.sync += [
                counter.eq(counter - 1),
            ]
        return m


class Top(Elaboratable):

    def elaborate(self, platform):
        clk_in_freq = platform.default_clk_frequency
        clk_freq = 2 * clk_in_freq
        clk_in_freq_mhz = clk_in_freq / 1_000_000
        clk_freq_mhz = clk_freq / 1_000_000
        osc_divisor = int(clk_freq // 46_875)

        cfg = SynthConfig(clk_freq=clk_freq, osc_divisor=osc_divisor)
        assert cfg.osc_rate == 46_875, 'change with care.'
        uart_baud = 31250
        uart_divisor = int(clk_freq // uart_baud)
        status_duration = int(0.05 * clk_freq)

        clk_pin = platform.request(platform.default_clk, dir='-')
        midi_uart_pins = platform.request('uart', 1)
        bad_led = platform.request('led_r', 0)
        good_led = platform.request('led_g', 0)
        seg7_pins = platform.request('seg7')
        i2s_pins = platform.request('i2s', 0)
        dbg_pins = platform.request('dbg')

        m = Module()
        pll = PLL(freq_in_mhz=clk_in_freq_mhz, freq_out_mhz=clk_freq_mhz)
        uart_rx = P_UARTRx(divisor=uart_divisor)
        recv_status = OneShot(duration=status_duration)
        err_status = OneShot(duration=status_duration)
        midi_decode = MIDIDecoder()
        pri = MonoPriority()
        pri.voice_note_inlet.leave_unconnected()
        ones_segs = DigitPattern()
        tens_segs = DigitPattern()
        seg7_out = SevenSegDriver(clk_freq, 100, 1)
        osc = Oscillator(cfg)
        osc.pulse_inlet.leave_unconnected()
        osc.saw_inlet.leave_unconnected()
        gate = Gate(stereo_sample_spec(cfg.osc_depth))
        gate.signal_outlet.leave_unconnected()
        i2s_tx = P_I2STx(clk_freq, cfg.out_rate)
        m.domains += pll.domain # This switches the default clk domain
                                # to the PLL-generated domain for Top
                                # and all submodules.
        m.submodules.pll = pll
        m.submodules.uart_rx = uart_rx
        m.submodules.midi = midi_decode
        m.submodules.pri = pri
        m.submodules.recv_status = recv_status
        m.submodules.err_status = err_status
        m.submodules.ones_segs = ones_segs
        m.submodules.tens_segs = tens_segs
        m.submodules.seg7_out = seg7_out
        m.submodules.osc = osc
        m.submodules.gate = gate
        m.submodules.i2s_tx = i2s_tx
        m.submodules.event_pipe = Pipeline([uart_rx, midi_decode, pri])
        m.submodules.gate_pipe = Pipeline([pri, gate])
        m.submodules.sample_pipe = Pipeline([gate, i2s_tx])

        note_valid = midi_decode.note_msg_inlet.o_valid
        note_on = midi_decode.note_msg_inlet.o_data.onoff
        osc_stereo = Cat(osc.pulse_inlet.o_data, osc.saw_inlet.o_data)

        m.d.comb += [
            pll.clk_pin.eq(clk_pin),

            uart_rx.rx_pin.eq(midi_uart_pins.rx),

            # Good LED flickers when Note On received.
            recv_status.trg.eq(note_valid & note_on),
            good_led.eq(recv_status.out),

            # Bad LED flickers when Note Off received.
            err_status.trg.eq(note_valid & ~note_on),
            bad_led.eq(err_status.out),

            ones_segs.digit_in.eq(pri.voice_note_inlet.o_data.note[:4]),
            tens_segs.digit_in.eq(pri.voice_note_inlet.o_data.note[4:]),

            seg7_out.pwm.eq(pri.voice_gate_inlet.o_data.gate),
            seg7_out.segment_patterns[0].eq(ones_segs.segments_out),
            seg7_out.segment_patterns[1].eq(tens_segs.segments_out),

            seg7_pins.eq(seg7_out.seg7),

            osc.sync_in.eq(False),
            osc.note_in.eq(pri.voice_note_inlet.o_data.note),

            # gate.signal_in.eq(osc_stereo),
            gate.signal_outlet.i_valid.eq(osc.pulse_inlet.o_valid),
            gate.signal_outlet.i_data.eq(osc_stereo),
            osc.pulse_inlet.i_ready.eq(gate.signal_outlet.o_ready),
            osc.saw_inlet.i_ready.eq(gate.signal_outlet.o_ready),

            i2s_pins.eq(i2s_tx.tx_i2s),
        ]
        return m


def assemble_platform():
    platform = ICEBreakerPlatform()
    i2s_conn = ('pmod', 0)
    seg7_conn = ('pmod', 1)
    i2s = Resource('i2s', 0,
        Subsignal('mclk', Pins('1', conn=i2s_conn, dir='o')),
        Subsignal('lrck', Pins('2', conn=i2s_conn, dir='o')),
        Subsignal('sck',  Pins('3', conn=i2s_conn, dir='o')),
        Subsignal('sd',   Pins('4', conn=i2s_conn, dir='o')),
    )
    seg7 = Resource('seg7', 0,
        Subsignal('segs', Pins('1 2 3 4 7 8 9', conn=seg7_conn, dir='o')),
        Subsignal('digit', Pins('10', conn=seg7_conn, dir='o'))
    )
    midi = UARTResource(1, rx='39', tx='40',
        attrs=Attrs(IO_STANDARD='SB_LVCMOS')
    )
    dbg = Resource('dbg', 0,
        Subsignal('dbg', Pins('7 8 9 10', conn=i2s_conn, dir='o')),
    )
    platform.add_resources((i2s, seg7, midi, dbg))
    return platform


if __name__ == '__main__':
    platform = assemble_platform()
    top = Top()
    platform.build(top, do_program=True)

#!/usr/bin/env nmigen

from nmigen import *
from nmigen.build import *
from nmigen_boards.icebreaker import ICEBreakerPlatform
from nmigen_boards.resources import UARTResource

from nmigen_lib import PLL, UARTRx
from nmigen_lib.seven_segment.digit_pattern import DigitPattern
from nmigen_lib.seven_segment.driver import SevenSegDriver
from synth import Gate, I2STx, MIDIDecoder, MonoPriority
from synth import Oscillator, SynthConfig


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
        uart_rx = UARTRx(divisor=uart_divisor)
        recv_status = OneShot(duration=status_duration)
        err_status = OneShot(duration=status_duration)
        midi_decode = MIDIDecoder()
        pri = MonoPriority()
        ones_segs = DigitPattern()
        tens_segs = DigitPattern()
        driver = SevenSegDriver(clk_freq, 100, 1)
        osc = Oscillator(cfg)
        gate0 = Gate(signed(cfg.osc_depth)) # Left channel
        gate1 = Gate(signed(cfg.osc_depth)) # Right channel
        i2s_tx = I2STx(clk_freq, cfg.out_rate)
        m.domains += pll.domain # This switches the default clk domain
                                # to the PLL-generated domain for Top
                                # and all submodules.
        m.submodules += [pll]
        m.submodules += [uart_rx, midi_decode, pri]
        m.submodules += [recv_status, err_status]
        m.submodules += [ones_segs, tens_segs, driver]
        m.submodules += [osc, gate0, gate1, i2s_tx]
        m.d.comb += [
            pll.clk_pin.eq(clk_pin),

            uart_rx.rx_pin.eq(midi_uart_pins.rx),
            dbg_pins.dbg[0].eq(midi_uart_pins.rx),
            dbg_pins.dbg[1].eq(uart_rx.rx_rdy),
            dbg_pins.dbg[2].eq(uart_rx.rx_err),
            dbg_pins.dbg[3].eq(uart_rx.dbg[0]),

            midi_decode.serial_data.eq(uart_rx.rx_data),
            midi_decode.serial_rdy.eq(uart_rx.rx_rdy),

            # Good LED flickers when Note On received.
            recv_status.trg.eq(midi_decode.note_on_rdy),
            good_led.eq(recv_status.out),

            # Bad LED flickers when Note Off received.
            err_status.trg.eq(uart_rx.rx_err),
            # err_status.trg.eq(midi_decode.note_off_rdy),
            bad_led.eq(err_status.out),

            pri.note_on_rdy.eq(midi_decode.note_on_rdy),
            pri.note_off_rdy.eq(midi_decode.note_off_rdy),
            pri.note_chan.eq(midi_decode.note_chan),
            pri.note_key.eq(midi_decode.note_key),
            pri.note_vel.eq(midi_decode.note_vel),

            ones_segs.digit_in.eq(pri.mono_key[:4]),
            tens_segs.digit_in.eq(pri.mono_key[4:]),

            driver.pwm.eq(pri.mono_gate),
            driver.segment_patterns[0].eq(ones_segs.segments_out),
            driver.segment_patterns[1].eq(tens_segs.segments_out),

            seg7_pins.eq(driver.seg7),

            osc.sync_in.eq(False),
            osc.note_in.eq(pri.mono_key),
            # dbg_pins.dbg[0].eq(osc.saw_out[1]),

            gate0.signal_in.eq(osc.pulse_out),
            gate1.signal_in.eq(osc.saw_out),
            gate0.gate_in.eq(pri.mono_gate),
            gate1.gate_in.eq(pri.mono_gate),
            # dbg_pins.dbg[1].eq(gate1.signal_out[1]),
            # dbg_pins.dbg[0].eq(gate1.signal_in[1]),

            i2s_tx.tx_stb.eq(True),
            i2s_tx.tx_samples[0].eq(gate0.signal_out),
            i2s_tx.tx_samples[1].eq(gate1.signal_out),

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

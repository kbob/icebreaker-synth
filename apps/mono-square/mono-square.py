#!/usr/bin/env nmigen

from nmigen import *
from nmigen.build import *
from nmigen_boards.icebreaker import ICEBreakerPlatform
from nmigen_boards.resources import UARTResource

from nmigen_lib import PLL, UARTRx
from nmigen_lib.seven_segment.digit_pattern import DigitPattern
from nmigen_lib.seven_segment.driver import SevenSegDriver
from synth import MIDIDecoder, MonoPriority, Oscillator, Gate, I2STx

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
        default_clk_freq = platform.default_clk_frequency
        clk_freq = 4 * default_clk_freq
        cfg = SynthConfig(clk_freq=clk_freq, osc_divisor=1024)
        uart_baud = 31250
        uart_divisor = int(clk_freq // uart_baud)
        status_duration = int(0.05 * clk_freq)

        uart_pins = platform.request('uart', 1)
        bad_led = platform.request('led_r', 0)
        good_led = platform.request('led_g', 0)
        seg7_pins = platform.request('seg7')

        m = Module()
        pll = PLL()
        uart_rx = UARTRx(divisor=uart_divisor)
        recv_status = OneShot(duration=status_duration)
        err_status = OneShot(duration=status_duration)
        midi_decode = MIDIDecoder()
        pri = MonoPriority()
        ones_segs = DigitPattern()
        tens_segs = DigitPattern()
        driver = SevenSegDriver(clk_freq, 100, 1)
        osc = Oscillator(cfg)
        gate = Gate()
        i2s_tx = I2STx()
        m.submodules += [pll, osc, gate, i2s_tx]
        m.submodules += [uart_rx, recv_status, err_status]
        m.submodules += [midi_decode, pri]
        m.submodules += [ones_segs, tens_segs, driver]
        m.d.comb += [
            uart_rx.rx_pin.eq(uart_pins.rx),
            good_led.eq(recv_status.out),
            recv_status.trg.eq(midi_decode.note_on_rdy),
            err_status.trg.eq(midi_decode.note_off_rdy),
            bad_led.eq(err_status.out),
            midi_decode.serial_data.eq(uart_rx.rx_data),
            midi_decode.serial_rdy.eq(uart_rx.rx_rdy),
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
        ]
        return m


def assemble_platform():
    platform = ICEBreakerPlatform()
    seg7_conn = ('pmod', 1)
    seg7 = Resource('seg7', 0,
        Subsignal('segs', Pins('1 2 3 4 7 8 9', conn=seg7_conn, dir='o')),
        Subsignal('digit', Pins('10', conn=seg7_conn, dir='o'))
        )
    midi = UARTResource(1, rx='39', tx='40',
        attrs=Attrs(IO_STANDARD='SB_LVCMOS'))
    platform.add_resources((seg7, midi))
    return platform

if __name__ == '__main__':
    platform = assemble_platform()
    top = Top()
    platform.build(top, do_program=True)

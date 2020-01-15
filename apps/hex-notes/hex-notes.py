#!/usr/bin/env nmigen

from nmigen import Elaboratable, Module, Signal
from nmigen.build import Attrs, Pins, Resource, Subsignal
from nmigen_boards.icebreaker import ICEBreakerPlatform
from nmigen_boards.resources import UARTResource

from nmigen_lib.pipe import Pipeline
from nmigen_lib.pipe.uart import P_UARTRx
from nmigen_lib.seven_segment.digit_pattern import DigitPattern
from nmigen_lib.seven_segment.driver import SevenSegDriver
from synth import MIDIDecoder, MonoPriority

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
        clk_freq = platform.default_clk_frequency
        uart_baud = 31250
        uart_divisor = int(clk_freq // uart_baud)
        status_duration = int(0.05 * clk_freq)

        uart_pins = platform.request('uart', 1)
        bad_led = platform.request('led_r', 0)
        good_led = platform.request('led_g', 0)
        seg7_pins = platform.request('seg7')

        m = Module()
        uart_rx = P_UARTRx(divisor=uart_divisor)
        recv_status = OneShot(duration=status_duration)
        err_status = OneShot(duration=status_duration)
        midi_decode = MIDIDecoder()
        pri = MonoPriority()
        pri.voice_note_inlet.leave_unconnected()
        pri.voice_gate_inlet.leave_unconnected()
        ones_segs = DigitPattern()
        tens_segs = DigitPattern()
        driver = SevenSegDriver(clk_freq, 100, 1)
        m.submodules.uart_rx = uart_rx
        m.submodules.recv_status = recv_status
        m.submodules.err_status = err_status
        m.submodules.midi = midi_decode
        m.submodules.pri = pri
        m.submodules.ones_segs = ones_segs
        m.submodules.tens_segs = tens_segs
        m.submodules.driver = driver
        m.submodules.pipeline = Pipeline([uart_rx, midi_decode, pri])

        note_valid = midi_decode.note_msg_out.o_valid
        note_on = midi_decode.note_msg_out.o_data.onoff

        m.d.comb += [
            uart_rx.rx_pin.eq(uart_pins.rx),
            recv_status.trg.eq(note_valid & note_on),
            err_status.trg.eq(note_valid & ~note_on),
            good_led.eq(recv_status.out),
            bad_led.eq(err_status.out),
            ones_segs.digit_in.eq(pri.voice_note_inlet.o_data.note[:4]),
            tens_segs.digit_in.eq(pri.voice_note_inlet.o_data.note[4:]),
            driver.pwm.eq(pri.voice_gate_inlet.o_data.gate),
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

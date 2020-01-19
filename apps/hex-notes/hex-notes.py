#!/usr/bin/env nmigen

from nmigen import Elaboratable, Module, Signal
from nmigen.build import Attrs, Pins, Resource, Subsignal
from nmigen_boards.icebreaker import ICEBreakerPlatform
from nmigen_boards.resources import UARTResource

from nmigen_lib import HexDisplay, OneShot
from nmigen_lib.pipe import Pipeline
from nmigen_lib.pipe.uart import P_UARTRx
from synth import MIDIDecoder, MonoPriority


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
        pri.voice_note_out.leave_unconnected()
        pri.voice_gate_out.leave_unconnected()
        hex_display = HexDisplay(clk_freq, pwm_width=1)
        m.submodules.uart_rx = uart_rx
        m.submodules.recv_status = recv_status
        m.submodules.err_status = err_status
        m.submodules.midi = midi_decode
        m.submodules.pri = pri
        m.submodules.HexDisplay = hex_display
        m.submodules.pipeline = Pipeline([uart_rx, midi_decode, pri])

        note_valid = midi_decode.note_msg_out.o_valid
        note_on = midi_decode.note_msg_out.o_data.onoff

        m.d.comb += [
            uart_rx.rx_pin.eq(uart_pins.rx),
            recv_status.i_trg.eq(note_valid & note_on),
            err_status.i_trg.eq(note_valid & ~note_on),
            good_led.eq(recv_status.o_pulse),
            bad_led.eq(err_status.o_pulse),
            hex_display.i_data.eq(pri.voice_note_out.o_data.note),
            hex_display.i_pwm.eq(pri.voice_gate_out.o_data.gate),
            seg7_pins.eq(hex_display.o_seg7),
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

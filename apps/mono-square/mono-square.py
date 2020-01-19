#!/usr/bin/env nmigen

from nmigen import Cat, Elaboratable, Module, Signal, unsigned
from nmigen.build import Attrs, Pins, Resource, Subsignal
from nmigen_boards.icebreaker import ICEBreakerPlatform
from nmigen_boards.resources import UARTResource

from nmigen_lib import HexDisplay, OneShot, PLL
from nmigen_lib.pipe import Pipeline
from nmigen_lib.pipe.uart import P_UARTRx

from synth import ChannelPair, Gate, P_I2STx, MIDIDecoder, MonoPriority
from synth import Oscillator, SynthConfig, stereo_sample_spec


class Top(Elaboratable):

    def elaborate(self, platform):
        clk_in_freq = platform.default_clk_frequency
        cfg = SynthConfig(
            clk_freq=clk_in_freq * 4,
            osc_oversample=4,
            out_oversample=4,
        )
        cfg.set_build_options()
        cfg.describe()

        clk_in_freq_mhz = clk_in_freq / 1_000_000
        clk_freq_mhz = cfg.clk_freq / 1_000_000

        uart_baud = 31250
        uart_divisor = int(cfg.clk_freq // uart_baud)
        status_duration = int(0.05 * cfg.clk_freq)

        clk_pin = platform.request(platform.default_clk, dir='-')
        midi_uart_pins = platform.request('uart', 1)
        bad_led = platform.request('led_r', 0)
        good_led = platform.request('led_g', 0)
        seg7_pins = platform.request('seg7')
        i2s_pins = platform.request('i2s', 0)
        dbg_pins = platform.request('dbg')

        m = Module()

        m.submodules.pll = pll = PLL(
            freq_in_mhz=clk_in_freq_mhz,
            freq_out_mhz=clk_freq_mhz,
        )
        m.submodules.uart_rx = uart_rx = P_UARTRx(divisor=uart_divisor)
        m.submodules.midi = midi_decode = MIDIDecoder()
        m.submodules.pri = pri = MonoPriority()
        m.submodules.osc = osc = Oscillator(cfg)
        m.submodules.pair = pair = ChannelPair(cfg.osc_depth)
        m.submodules.gate = gate = Gate(stereo_sample_spec(cfg.osc_depth))
        m.submodules.i2s_tx = i2s_tx = P_I2STx(cfg)
        m.submodules.recv_status = recv_status = OneShot(status_duration)
        m.submodules.err_status = err_status = OneShot(status_duration)
        m.submodules.hex_display = hex_display = HexDisplay(
            cfg.clk_freq,
            pwm_width=1,
        )

        m.domains += pll.domain # This switches the default clk domain
                                # to the PLL-generated domain for Top
                                # and all submodules.

        # connect modules with pipes.
        m.submodules.event_pipe = Pipeline([uart_rx, midi_decode, pri, osc])
        m.submodules.gate_pipe = Pipeline([pri, gate])
        m.submodules.pulse_pipe = Pipeline([osc.pulse_out, pair.left_in])
        m.submodules.saw_pipe = Pipeline([osc.saw_out, pair.right_in])
        m.submodules.sample_pipe = Pipeline([pair, gate, i2s_tx])

        note_valid = midi_decode.note_msg_out.o_valid
        note_on = midi_decode.note_msg_out.o_data.onoff

        m.d.comb += [
            # Connect external pins.
            pll.clk_pin.eq(clk_pin),
            uart_rx.rx_pin.eq(midi_uart_pins.rx),
            i2s_pins.eq(i2s_tx.tx_i2s),

            # Good LED flickers when Note On received.
            recv_status.i_trg.eq(note_valid & note_on),
            good_led.eq(recv_status.o_pulse),

            # Bad LED flickers when Note Off received.
            err_status.i_trg.eq(note_valid & ~note_on),
            bad_led.eq(err_status.o_pulse),

            # Hex display shows current MIDI note.
            hex_display.i_data.eq(pri.voice_note_out.o_data.note),
            hex_display.i_pwm.eq(pri.voice_gate_out.o_data.gate),
            seg7_pins.eq(hex_display.o_seg7),
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

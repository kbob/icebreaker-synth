#!/usr/bin/env nmigen

from collections import namedtuple

from nmigen import *
from nmigen.asserts import Assert
from nmigen.back.pysim import Passive

from nmigen_lib.pipe import PipeSpec
from nmigen_lib.util import Main, delay


note_msg_spec = PipeSpec((
    ('onoff', unsigned(1)),
    ('channel', unsigned(4)),
    ('note', unsigned(7)),
    ('velocity', unsigned(7)),
))


class MIDIDecoder(Elaboratable):

    def __init__(self):
        self.serial_in = PipeSpec(8).outlet()
        self.note_msg_out = note_msg_spec.inlet()

    def elaborate(self, platform):

        def is_message_start(byte):
            # any byte with the high bit set
            return byte[7] != 0

        def is_voice_status(byte):
            # Voice Category: 0x80 - 0xEF
            return byte[7] & (byte[4:8] != 0xF)

        def is_note_off(byte):
            # 0x80 - 0x8F
            return byte[4:8] == 0x8

        def is_note_on(byte):
            # 0x90 - 0x9F
            return byte[4:8] == 0x9

        def is_poly_key_pressure(byte):
            # 0xA0 - 0xAF
            return byte[4:8] == 0xA

        def is_control_change(byte):
            # 0xB0 - 0xBF
            return byte[4:8] == 0xB

        def is_program_change(byte):
            # 0xC0 - 0xCF
            return byte[4:8] == 0xC

        def is_channel_pressure(byte):
            # 0xD0 - 0xDF
            return byte[4:8] == 0xD

        def is_pitch_bend_change(byte):
            # 0xE0 - 0xEF
            return byte[4:8] == 0xE

        def is_system_common_status(byte):
            # System Commmon Category: 0xF0 - 0xF7
            return byte[3:8] == 0b11110

        i_data = self.serial_in.i_data
        o_note = self.note_msg_out.o_data
        o_note_valid = self.note_msg_out.o_valid
        status_byte = Signal(8)
        status_valid = Signal()
        data_last = Signal()
        data_index = Signal()
        data_byte_1 = Signal(8)

        m = Module()
        m.d.comb += [
            self.serial_in.o_ready.eq(True),
        ]
        with m.If(self.note_msg_out.sent()):
            m.d.sync += [
                o_note_valid.eq(False),
            ]
        with m.If(self.serial_in.received()):
            with m.If(is_message_start(i_data)):
                with m.If(is_voice_status(i_data)):
                    m.d.sync += [
                        status_byte.eq(i_data),
                        status_valid.eq(True),
                        data_index.eq(0),
                    ]
                    with m.If(is_note_off(i_data)):
                        m.d.sync += [
                            data_last.eq(1),
                        ]
                    with m.If(is_note_on(i_data)):
                        m.d.sync += [
                            data_last.eq(1),
                        ]
                    with m.If(is_poly_key_pressure(i_data)):
                        m.d.sync += [
                            data_last.eq(1),
                        ]
                    with m.If(is_control_change(i_data)):
                        m.d.sync += [
                            data_last.eq(1),
                        ]
                    with m.If(is_program_change(i_data)):
                        m.d.sync += [
                            data_last.eq(0),
                        ]
                    with m.If(is_channel_pressure(i_data)):
                        m.d.sync += [
                            data_last.eq(0),
                        ]
                    with m.If(is_pitch_bend_change(i_data)):
                        m.d.sync += [
                            data_last.eq(1),
                        ]
                with m.Elif(is_system_common_status(i_data)):
                    m.d.sync += [
                        status_valid.eq(False),
                     ]
                # else this is a complete real-time message.
            with m.Else():
                with m.If(status_valid):
                    with m.If((data_index == 0) & (data_last == 1)):
                        # First data byte of three-byte message
                        m.d.sync += [
                            data_byte_1.eq(i_data),
                            data_index.eq(1),
                        ]
                    with m.Elif((data_index == 1) & (data_last == 1)):
                        # Second data byte of three-byte message:
                        # three-byte message is complete.
                        m.d.sync += [
                            data_index.eq(0),
                        ]
                        channel = status_byte[:4]
                        key = data_byte_1[:7]
                        velocity = i_data[:7]

                        with m.If(is_note_off(status_byte)):
                            m.d.sync += [
                                o_note_valid.eq(True),
                                o_note.onoff.eq(False),
                                o_note.channel.eq(channel),
                                o_note.note.eq(key),
                                o_note.velocity.eq(velocity),
                            ]
                        with m.If(is_note_on(status_byte)):
                            m.d.sync += [
                                o_note_valid.eq(True),
                                o_note.onoff.eq(velocity != 0),
                                o_note.channel.eq(channel),
                                o_note.note.eq(key),
                                o_note.velocity.eq(velocity),
                            ]
                        # other three-byte messages
                    with m.Else():
                        Assert((data_index == 0) & (data_last == 0))
                        # two-byte message is complete.
        return m


if __name__ == '__main__':
    design = MIDIDecoder()
    design.serial_in.leave_unconnected()
    design.note_msg_out.leave_unconnected()

    # Workaround nMigen issue #280
    m = Module()
    m.submodules.design = design
    i_valid = Signal()
    i_data = Signal(8)
    i_note_ready = Signal()
    m.d.comb += [
        design.serial_in.i_valid.eq(i_valid),
        design.serial_in.i_data.eq(i_data),
        design.note_msg_out.i_ready.eq(i_note_ready),
    ]

    #280 with Main(design).sim as sim:
    with Main(m).sim as sim:
        @sim.sync_process
        def data_source():
            class Pause: pass
            data = [
                0x93, 60, 64,       # note on C4
                Pause,
                67, 96,             # note on G4 (running status)
                Pause,
                0x83, 60, 32,       # note off C4
                0x93, 67, 0,        # note off G4 (note on w/velocity 0)
            ]
            for i, d in enumerate(data):
                if d is Pause:
                    yield from delay(5)
                else:
                    #280 yield design.serial_in.i_data.eq(d)
                    #280 yield design.serial_in.i_valid.eq(True)
                    yield i_data.eq(d)
                    yield i_valid.eq(True)
                    yield
                    #280 yield design.serial_in.i_valid.eq(False)
                    yield i_valid.eq(False)
                    yield from delay(i % 3)
            yield from delay(5)

        @sim.sync_process
        def note_sink():
            NoteMsg = namedtuple('NoteMsg', 'onoff channel note velocity')
            expected = [
                NoteMsg(True, 3, 60, 64),
                NoteMsg(True, 3, 67, 96),
                NoteMsg(False, 3, 60, 32),
                NoteMsg(False, 3, 67, 0),
            ]
            expected_index = 0
            yield Passive()
            #280
            yield i_note_ready.eq(False)
            while True:
                valid = yield design.note_msg_out.o_valid
                #280
                ready = yield i_note_ready
                if valid and not ready:
                    yield from delay(expected_index)
                    #280
                    yield i_note_ready.eq(True)
                elif valid and ready:
                    #280
                    yield i_note_ready.eq(False)
                    actual = NoteMsg(
                        (yield design.note_msg_out.o_data.onoff),
                        (yield design.note_msg_out.o_data.channel),
                        (yield design.note_msg_out.o_data.note),
                        (yield design.note_msg_out.o_data.velocity),
                    )
                    assert expected_index < len(expected)
                    assert actual == expected[expected_index], (
                        f'expected {expected[expected_index]}, got {actual}'
                    )
                    expected_index += 1
                yield

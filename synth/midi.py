#!/usr/bin/env nmigen

from nmigen import *
from nmigen.asserts import *

from nmigen_lib.pipe import PipeSpec
from nmigen_lib.util import Main, delay


note_onoff_spec = PipeSpec((
    ('chan', unsigned(4)),
    ('key', unsigned(7)),
    ('vel', unsigned(7)),
))


class MIDIDecoder(Elaboratable):

    def __init__(self):
        self.serial_outlet = PipeSpec(8).outlet()
        # self.note_on_inlet = note_onoff_spec.inlet()
        # self.note_off_inlet = note_onoff_spec.inlet()
        # self.serial_data = Signal(8)
        # self.serial_rdy = Signal()
        self.note_on_rdy = Signal()
        self.note_off_rdy = Signal()
        self.note_chan = Signal(4)
        self.note_key = Signal(7)
        self.note_vel = Signal(7)
        # self.ports = [sig
        #               for sig in self.__dict__.values()
        #               if isinstance(sig, Signal)]

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

        def is_system_common_status(byte):
            # System Commmon Category: 0xF0 - 0xF7
            return byte[3:8] == 0b11110
            # return (byte & 0xF8) == 0xF0

        i_data = self.serial_outlet.i_data
        # note_off_data = self.note_off_inlet.o_data
        # note_on_data = self.note_on_inlet.o_data
        status_byte = Signal(8)
        status_valid = Signal()
        data_last = Signal()
        data_index = Signal()
        data_byte_1 = Signal(8)

        m = Module()
        m.d.comb += [
            self.serial_outlet.o_ready.eq(True),
        ]
        m.d.sync += [
            self.note_on_rdy.eq(False),
            self.note_off_rdy.eq(False),
            # self.note_on_inlet.o_valid.eq(False),
            # self.note_off_inlet.o_valid.eq(False),
        ]
        # with m.If(self.serial_rdy):
        with m.If(self.serial_outlet.received()):
            with m.If(is_message_start(i_data)):
                with m.If(is_voice_status(i_data)):
                    m.d.sync += [
                        status_byte.eq(i_data),
                        status_valid.eq(True),
                    ]
                    with m.If(is_note_off(i_data)):
                        m.d.sync += [
                            data_last.eq(1),
                        ]
                    with m.If(is_note_on(i_data)):
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
                        # # Or ...
                        # channel = status_byte[:4]
                        # key = data_byte_1[:7]
                        # velocity = i_data[:7]
                        channel = Signal(4)
                        key = Signal(7)
                        velocity = Signal(7)
                        m.d.comb += [
                            channel.eq(status_byte[:4]),
                            key.eq(data_byte_1[:7]),
                            velocity.eq(i_data[:7]),
                        ]

                        with m.If(is_note_off(status_byte)):
                            m.d.sync += [
                                self.note_off_rdy.eq(True),
                                self.note_chan.eq(channel),
                                self.note_key.eq(key),
                                self.note_vel.eq(velocity),
                                # self.note_off_inlet.o_valid.eq(True),
                                # note_off_data.chan.eq(channel),
                                # note_off_data.key.eq(key),
                                # note_off_data.vel.eq(velocity),
                            ]
                        with m.If(is_note_on(status_byte)):
                            m.d.sync += [
                                self.note_on_rdy.eq(velocity != 0),
                                self.note_off_rdy.eq(velocity == 0),
                                self.note_chan.eq(channel),
                                self.note_key.eq(key),
                                self.note_vel.eq(velocity),
                            ]
                        # other three-byte messages
                    with m.Else():
                        Assert((data_index == 0) & (data_last == 0))
                        # two-byte message is complete.
        return m


if __name__ == '__main__':
    design = MIDIDecoder()

    # Workaround nMigen issue #280
    m = Module()
    m.submodules.design = design
    i_valid = Signal()
    i_data = Signal(8)
    m.d.comb += [
        design.serial_outlet.i_valid.eq(i_valid),
        design.serial_outlet.i_data.eq(i_data),
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
                    # yield design.serial_data.eq(d)
                    # yield design.serial_rdy.eq(True)
                    #280 yield design.serial_outlet.i_data.eq(d)
                    #280 yield design.serial_outlet.i_valid.eq(True)
                    yield i_data.eq(d)
                    yield i_valid.eq(True)
                    yield
                    # yield design.serial_rdy.eq(False)
                    #280 yield design.serial_outlet.i_valid.eq(False)
                    yield i_valid.eq(False)
                    yield from delay(i % 3)
            yield from delay(2)

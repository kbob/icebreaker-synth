#!/usr/bin/env nmigen

from nmigen import *
from nmigen.asserts import *
from nmigen_lib.util import delay
from nmigen_lib.util.main import Main

class MIDIDecoder(Elaboratable):

    def __init__(self):
        self.serial_data = Signal(8)
        self.serial_rdy = Signal()
        self.note_on_rdy = Signal()
        self.note_off_rdy = Signal()
        self.note_chan = Signal(4)
        self.note_key = Signal(7)
        self.note_vel = Signal(7)
        self.ports = [sig
                      for sig in self.__dict__.values()
                      if isinstance(sig, Signal)]

    def elaborate(self, platform):

        def is_message_start(byte):
            return byte[7] != 0

        def is_voice_status(byte):
            # Voice Category 0x80 to 0xEF
            return byte[7] & (byte[4:8] != 0xF)

        def is_note_off(byte):
            return (byte & 0xF0) == 0x80

        def is_note_on(byte):
            return (byte & 0xF0) == 0x90

        def is_system_common_status(byte):
            # System Commmons Category
            return (byte & 0xF8) == 0xF0

        status_byte = Signal(8)
        status_valid = Signal()
        data_last = Signal()
        data_index = Signal()
        data_byte_1 = Signal(8)

        m = Module()
        m.d.sync += [
            self.note_on_rdy.eq(False),
            self.note_off_rdy.eq(False),
        ]
        with m.If(self.serial_rdy):
            with m.If(is_message_start(self.serial_data)):
                with m.If(is_voice_status(self.serial_data)):
                    m.d.sync += [
                        status_byte.eq(self.serial_data),
                        status_valid.eq(True),
                    ]
                    with m.If(is_note_off(self.serial_data)):
                        m.d.sync += [
                            data_last.eq(1),
                        ]
                    with m.If(is_note_on(self.serial_data)):
                        m.d.sync += [
                            data_last.eq(1),
                        ]
                with m.Elif(is_system_common_status(self.serial_data)):
                    m.d.sync += [
                        status_valid.eq(False)
                    ]
                # else this is a complete real-time message.
            with m.Else():
                with m.If(status_valid):
                    with m.If((data_index == 0) & (data_last == 1)):
                        # First data byte of three-byte message
                        m.d.sync += [
                            data_byte_1.eq(self.serial_data),
                            data_index.eq(1),
                        ]
                    with m.Elif((data_index == 1) & (data_last == 1)):
                        # Second data byte of three-byte message:
                        # three-byte message is complete.
                        m.d.sync += [
                            data_index.eq(0),
                        ]
                        channel = Signal(4)
                        key = Signal(7)
                        velocity = Signal(7)
                        m.d.comb += [
                            channel.eq(status_byte[:4]),
                            key.eq(data_byte_1[:7]),
                            velocity.eq(self.serial_data[:7]),
                        ]

                        with m.If(is_note_off(status_byte)):
                            m.d.sync += [
                                self.note_off_rdy.eq(True),
                                self.note_chan.eq(channel),
                                self.note_key.eq(key),
                                self.note_vel.eq(velocity),
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
                        ... # two-byte message is complete.

            # if is_message_start(self.serial_data):
            #     if is_voice_status:
            #         status_byte = self.serial_data
            #         status_valid = True
            #         data_index = 0
            #         if is_note_off:
            #             data_last = 1
            #         if is_note_on:
            #             data_last = 1
            #     elif is_system_common:
            #         status_valid = False
            #         next = NOT_MESSAGE
            # else:
            #     if status_valid:
            #         if (data_index == 0) & (data_last == 1):
            #             data_byte_1 = self.serial_data
            #             data_index = 1
            #         elif (data_index == 1) & (data_last == 1):
            #             data_index = 0
            #             if is_note_off(status_byte):
            #                 self.note_off_rdy = True
            #                 self.note_chan = status_byte[:4]
            #                 self.note_key = date_byte_1[:6]
            #                 self.note_on_
            #                 self.note_onoff = False
            #                 self.note_vel = serial.data[:6]
            #             if is_note_on(status_byte):
            #                 self.note_rdy = True
            #                 self.note_chan = status_byte[:4]
            #                 self.note_key = date_byte_1[:6]
            #                 self.note_onoff = (velocity != 0)
            #                 self.note_vel = serial.data[:6]
            #             ... # more three-byte messages
            #         else:
            #             m.Assert((data_index == 0) & (data_last == 0))
            #             ... # two-byte messages

        return m


if __name__ == '__main__':
    design = MIDIDecoder()
    with Main(design).sim as sim:
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
                    yield design.serial_data.eq(d)
                    yield design.serial_rdy.eq(True)
                    yield
                    yield design.serial_rdy.eq(False)
                    yield from delay(i % 3)
            yield from delay(2)

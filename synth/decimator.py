#!/usr/bin/env nmigen


on reset:
    ram[:] = 0
    output = 0
on trig:
    store sample in ram[index]
    inc index
    clear accumulator
    nsamp = M-1
while nsamp >= 0:
    accum += kern[nsamp] + ram[nsamp + index]
    nsamp -= a
if nsamp == -1:
    output = accum[16:32]
    valid = True
if ack:
    valid = False

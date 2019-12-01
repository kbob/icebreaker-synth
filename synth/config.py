#!/usr/bin/env nmigen

from inspect import isdatadescriptor
from numbers import Complex

MIN_SAMPLE_RATE = 40_000

class SynthConfig:

    def __init__(self, clk_freq, osc_divisor,
                 osc_depth=16, out_depth=16,
                 min_freq_depth=11, max_freq_depth=16):
        self.clk_freq = int(clk_freq)
        assert self.clk_freq == clk_freq
        self.osc_divisor = osc_divisor
        out_divisor = osc_divisor
        while clk_freq / out_divisor >= 2 * MIN_SAMPLE_RATE:
            out_divisor *= 2
        self.out_divisor = out_divisor
        self.osc_depth = osc_depth
        self.out_depth = out_depth
        self.min_freq_depth = min_freq_depth
        self.max_freq_depth = max_freq_depth

    def describe(self):
        print('SynthConfig:')
        fields = {k: v
                  for (k, v) in self.__dict__.items()
                  if isinstance(v, Complex)}
        fields.update({k: getattr(self, k)
                       for (k, v) in type(self).__dict__.items()
                       if not k.startswith('_') and isdatadescriptor(v)})
        w = max(len(f) for f in fields)
        for key in sorted(fields):
            print(f'    {key:{w}} = {fields[key]:10,}')
        print()

    @property
    def out_rate(self):
        return self.clk_freq // self.out_divisor

    @property
    def osc_rate(self):
        return self.clk_freq // self.osc_divisor


if __name__ == '__main__':
    cfg = SynthConfig(48_000_000.0, 32)
    cfg.describe()
    cfg1 = SynthConfig(12_000_000.0, 256)
    cfg1.describe()

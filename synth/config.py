#!/usr/bin/env nmigen

import os
from warnings import catch_warnings, warn

from inspect import isdatadescriptor
from numbers import Complex


MIN_SAMPLE_RATE = 40_000


class SynthConfig:

    def __init__(self, clk_freq,
                 osc_oversample=1, osc_depth=16,
                 out_oversample=1, out_depth=16, out_channels=2,
                 min_freq_depth=11, max_freq_depth=16):
        assert out_oversample in {1, 2, 4}
        base_rate = int(clk_freq)
        while base_rate // 2 >= MIN_SAMPLE_RATE:
            base_rate //= 2
        self.clk_freq = clk_freq
        self.osc_rate = osc_oversample * base_rate
        self.osc_depth = osc_depth
        self.out_rate = out_oversample * base_rate
        self.out_depth = out_depth
        self.out_channels = out_channels
        self.min_freq_depth = min_freq_depth
        self.max_freq_depth = max_freq_depth
        self.build_options = {}

    @property
    def osc_divisor(self):
        div = int(self.clk_freq) // self.osc_rate
        assert isinstance(div, int)
        return div

    def set_build_options(self):
        clk_freq_mhz = self.clk_freq / 1_000_000
        self._set_build_option('NMIGEN_synth_opts', '-dsp')
        self._set_build_option('NMIGEN_nextpnr_opts', f'--freq {clk_freq_mhz}')

    def _set_build_option(self, name, value):
        if name in os.environ:
            old_value = os.environ[name]
            warn(f'{name} is already set to "{old_value}"', stacklevel=2)
            self.build_options[name] = old_value
        else:
            os.environ[name] = value
            self.build_options[name] = value

    def describe(self):
        opts_label = 'build_options'
        print('SynthConfig:')
        fields = {k: v
                  for (k, v) in self.__dict__.items()
                  if isinstance(v, Complex)}
        fields.update({k: getattr(self, k)
                       for (k, v) in type(self).__dict__.items()
                       if not k.startswith('_') and isdatadescriptor(v)})
        w = max(len(f) for f in list(fields) + [opts_label])
        for key in sorted(fields):
            print(f'    {key:{w}} = {fields[key]:#10,}')
        wo = w + 7
        if self.build_options:
            print(f'    {opts_label:{w}} = {{')
            wo = w + 6
            for (k, v) in self.build_options.items():
                print(f'    {"":{wo}}{k} = "{v}"')
            print(f'    {"":{w}}   }}')
        else:
            print(f'    {opts_label:{w}} = {{}}')
        print()


if __name__ == '__main__':
    cfg = SynthConfig(48_000_000.0, osc_oversample=32)
    cfg.set_build_options()
    cfg.describe()
    cfg1 = SynthConfig(12_000_000.0, osc_oversample=1)
    with catch_warnings(record=True) as w:
        cfg1.set_build_options()
        assert w
    cfg1.describe()

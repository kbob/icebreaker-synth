import sys

# Work around the warning
# RuntimeWarning: 'synth.xxx' found in sys.modules after import of packge...

if sys.argv[:1] == ['-m']:
    __all__ = []
else:
    from .config   import SynthConfig
    from .gate     import Gate
    from .i2s      import I2S, P_I2STx, I2STx, I2SRx, stereo_sample_spec
    from .midi     import MIDIDecoder
    from .osc      import Oscillator, mono_sample_spec
    from .priority import MonoPriority
    from .util     import MIDI_note_to_freq

    __all__ = [
               'Gate',
               'I2S',
               'I2SRx',
               'I2STx',
               'MIDIDecoder',
               'MIDI_note_to_freq',
               'MonoPriority',
               'Oscillator',
               'P_I2STx',
               'SynthConfig',
               'mono_sample_spec',
               'stereo_sample_spec',
    ]

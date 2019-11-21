#include <assert.h>
#include <math.h>
#include <stdio.h>

#define Fs 44100.0
#define F0    20.0

#define DUR    10.0 // seconds

#define SAMPLES ((int)(DUR * Fs))

static FILE *f;

static void start(void)
{
    f = fopen("/tmp/foo", "w");
    assert(f);
}

static void emit(float sample)
{
    fprintf(f, "%g\n", sample);
}

static void finish(void)
{
    fputs("end\n", f);
    fclose(f);
}

int main()
{
    start();
    float phase = 0.0;
    const float inc = F0 / Fs;
    for (int i = 0; i < SAMPLES; i++) {
        emit(1.0 - 2.0 * phase);
        //emit(sinf(2. * M_PI * phase));
        // emit(phase < 0.5 ? +1.0 : -1.0);
        phase += inc;
        if (phase >= 1.0)
            phase -= 1.0;
    }
    finish();
}

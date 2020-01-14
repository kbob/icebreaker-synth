#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>

#define M_TAU (2.0 * M_PI)

#define Fs   44100.0
#define FUND  (440.0 / 4)

#define FUND0  (440.0 / 4)
#define FUND1  (32 * 440.0)

#define DURATION 1.0 // seconds
// #define DURATION (2.0 / FUND)

#define NSAMP ((size_t)(DURATION * Fs))

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

// Code stolen directly from
// http://www.earlevel.com/main/2003/03/02/the-digital-state-variable-filter/

void sin_osc(float Fc)
{
    float f = M_TAU * Fc / Fs;
    float sinZ = 0.0;
    float cosZ = 1.0;
    for (size_t i = 0; i < NSAMP; i++) {
        emit(sinZ);
        // emit(sinZ < 0 ? -1. : +1.);
        sinZ += f * cosZ;
        cosZ -= f * sinZ;
    }
}

void int16_sin_osc(float Fc)
{
    const int16_t GAIN = 32700;
    const int16_t OFFSET = -8;
    float f = M_TAU * Fc / Fs;
    uint16_t i_f = (int16_t)(65536 * f);
    // printf("i_f = %d\n", i_f);
    int16_t i_sinZ = GAIN * 0.0;
    int16_t i_cosZ = GAIN * 1.0;
    for (size_t i = 0; i < NSAMP; i++) {
        float a = (float)(i_sinZ + OFFSET) / (float)GAIN;
        emit(a);
        i_sinZ += ((int32_t)i_f * (int32_t)i_cosZ) >> 16;
        i_cosZ -= ((int32_t)i_f * (int32_t)i_sinZ) >> 16;
        // double e = sin(f * i);
        // e *= GAIN; e = (double)(int)e / (double)GAIN;
        // emit(4000.0 * (a - e));
        // emit(a - e);
        // emit(e);
    }
}

void int32_sin_osc(double Fc)
{
    const int32_t GAIN = 1 << 30;
    const int32_t OFFSET = 0;
    double f = M_TAU * Fc / Fs;
    uint32_t i_f = (int32_t)(4294967296.0 * f);
    printf("i_f = %d\n", i_f);
    int32_t i_sinZ = GAIN * 0.0;
    int32_t i_cosZ = GAIN * 1.0;
    for (size_t i = 0; i < NSAMP; i++) {
        double a = (double)(i_sinZ + OFFSET) / (double)GAIN;
        emit(a);
        i_sinZ += ((int64_t)i_f * (int64_t)i_cosZ) >> 32;
        i_cosZ -= ((int64_t)i_f * (int64_t)i_sinZ) >> 32;
        // double e = sin(f * i);
        // e *= GAIN; e = (double)(int)e / (double)GAIN;
        // emit(4000.0 * (a - e));
        // emit(a - e);
        // emit(e);
    }
}

void sin_sweep_osc(float Fc0, float Fc1)
{
    float LF0 = log(Fc0);
    float LF1 = log(Fc1);
    float sinZ = 0.0;
    float cosZ = 1.0;
    for (size_t i = 0; i < NSAMP; i++) {
        float frac = (float)i / (float)NSAMP;
        float LF = LF0 + frac * (LF1 - LF0);
        float F = exp(LF);
        if (0 && F > Fs / 8) {
            emit(sinZ);
            // emit(sinZ < 0 ? -1. : +1.);
            F /= 4;
            float f = M_TAU * F / Fs;
            sinZ += f * cosZ;
            cosZ -= f * sinZ;
            sinZ += f * cosZ;
            cosZ -= f * sinZ;
            sinZ += f * cosZ;
            cosZ -= f * sinZ;
            sinZ += f * cosZ;
            cosZ -= f * sinZ;
        } else {
            emit(sinZ);
            // emit(sinZ < 0 ? -1. : +1.);
            float f = M_TAU * F / Fs;
            sinZ += f * cosZ;
            cosZ -= f * sinZ;
        }
    }
}

int main()
{
    start();
    sin_osc(FUND);
    // int16_sin_osc(FUND);
    // int32_sin_osc(FUND);
    // sin_sweep_osc(FUND0, FUND1);
    finish();
}

#include <assert.h>
#include <math.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>

#define OVERSAMPLE 32

#define ZOOM
#define Z0 1725
#define Z1 (Z0 + 512)

#define Fs0     44100.0
#define Fs1        (Fs0 / OVERSAMPLE)
//#define F0        500.0
#define F0          250.0
#define FC     (20000.0 / OVERSAMPLE)

#define DUR         0.1 // seconds

#define NSAMP0 ((size_t)(DUR * Fs0))
#define NSAMP1 ((size_t)(DUR * Fs1))

float orig[NSAMP0];
float deci[NSAMP1];
float intp[NSAMP0];

const int M = 254;
const size_t dkernel_size = M + 1;
const size_t ikernel_size = M + 1;
float dkernel[dkernel_size];
float ikernel[ikernel_size];

static void simple_saw(float *restrict samples, size_t size,
                       float freq, float Fs)
{
    const float inc = freq / Fs;
    float phase = 0.0;
    for (size_t i = 0; i < size; i++) {
        samples[i] = 1.0 - 2.0 * phase;
        phase += inc;
        if (phase >= 1.0)
            phase -= 1.0;
    }
}

static void write_data(const float *restrict samples, size_t size, bool fix_gain)
{
    FILE *f = fopen("/tmp/foo", "w");
    if (!f) {
        perror("/tmp/foo");
        exit(1);
    }
    float gain = 1.0;
    if (fix_gain) {
        float max = 0.0;
        for (size_t i = 0; i < size; i++)
            if (max < fabsf(samples[i]))
                max = fabs(samples[i]);
        gain /= max;
    }
#ifdef ZOOM
    for (size_t i = Z0; i < size && i < Z1; i++)
#else
    for (size_t i = 0; i < size; i++)
#endif
        fprintf(f, "%g\n", samples[i] * gain);
    fputs("end\n", f);
    fclose(f);
}

static inline double sinc(double x)
{
    if (x == 0.0)
        return 1.0;
    else
        return sin(M_PI * x) / (M_PI * x);
}

static inline double blackman(int i, int M)
{
    double a0 = 7938. / 18608.,
           a1 = 9240. / 18608.,
           a2 = 1430. / 18608.;

    return a0 - a1 * cos(2 * M_PI * i / M) + a2 * cos(4 * M_PI * i / M);
}

static void make_kernel(int M, float Fc, float Fs, float gain,
                        float *restrict kernel_out, size_t kernel_size)
{
    assert(M % 2 == 0 && "M must be even");
    assert(kernel_size == M + 1 && "kernel size must be M + 1");
    double BW = 4 / M;
    double Fcf = (Fc / Fs) + BW / 2; // Fc as a fraction of Fs
    for (int i = 0; i < kernel_size; i++) {
        kernel_out[i] = sinc(2 * Fcf * (i - M/2)) * blackman(i, M);
    }
    double sum = 0.0;
    for (size_t i = 0; i < kernel_size; i++)
        sum += kernel_out[i];
    gain /= sum;
    printf("M = %d, Fc = %g, Fcf = %g, sum = %g, gain = %g\n",
           M, Fc, Fcf, sum, gain);
    for (size_t i = 0; i < kernel_size; i++)
        kernel_out[i] *= gain;
}

static void decimate(const float *restrict in, size_t in_size,
                     float *restrict out, size_t out_size)
{
    assert(out_size >= in_size / OVERSAMPLE);
    for (size_t i = 0; i < out_size; i++) {
        const float *inp = in + OVERSAMPLE * i;
        size_t n = dkernel_size;
        if (n > in_size - OVERSAMPLE * i)
            n = in_size - OVERSAMPLE * i;
        float sum = 0.0;
        for (size_t j = 0; j < n; j++) {
            sum += inp[j] * dkernel[j];
        }
        out[i] = sum;
    }
}

static void interpolate(const float *restrict in, size_t in_size,
                        float *restrict out, size_t out_size)
{
    assert(out_size >= in_size * OVERSAMPLE);
    for (size_t i = 0; i < out_size; i++) {
        size_t j = OVERSAMPLE - i % OVERSAMPLE - 1;
        size_t n = ikernel_size;
        if (n > out_size - i)
            n = out_size - i;
        float sum = 0.0;
        for ( ; j < n; j += OVERSAMPLE) {
            sum += ikernel[j] * in[(i + j) / OVERSAMPLE];
        }
        out[i] = sum;
    }
}

int main()
{
    printf("Fs0 = %g; Fs1 = %g\n", Fs0, Fs1);
    printf("Nq0 = %g; Nq1 = %g\n", Fs0 / 2, Fs1 / 2);
    printf("FC = %g\n", FC);
    printf("DUR = %g, NSAMP0 = %zu, NSAMP1 = %zu\n",
           DUR, NSAMP0, NSAMP1);

   make_kernel(M, FC, Fs0, 1.0, dkernel, dkernel_size);
   make_kernel(M, FC, Fs0, OVERSAMPLE, ikernel, ikernel_size);

    simple_saw(orig, NSAMP0, F0, Fs0);
    decimate(orig, NSAMP0, deci, NSAMP1);
    interpolate(deci, NSAMP1, intp, NSAMP0);
    // write_data(orig, NSAMP0, false);
    // write_data(deci, NSAMP1, true);
    write_data(intp, NSAMP0, false);
    return 0;
}

#include <math.h>
#include <stdio.h>
#include <stdlib.h>

#define M_TAU (2.0 * M_PI)

#define Fs 44100.0
#define NYQUIST (Fs / 2)
#define MIDI_NOTE 0x6c
// #define MIDI_NOTE (69 - 24)
#define CONCERT_A_MIDI_NOTE 69
#define CONCERT_A_FREQ 440.0
#define DURATION 10.0
// #define DURATION 0.005
#define NSAMP ((int)(DURATION * Fs))

double square(double x, double fund)
{
    double y = 0;
    int nharm = floor(NYQUIST / fund);
    // printf("nharm = %d\n", nharm);
    for (int h = 1; h <= nharm; h += 2)
        y += sin(h * M_TAU * x) / h;
    return y;
}

double saw(double x, double fund)
{
    double y = 0;
    int nharm = floor(NYQUIST / fund);
    // printf("nharm = %d\n", nharm);
    for (int h = 1; h <= nharm; h++)
        y += sin(h * M_TAU * x) / h;
    return 0.5 * y;
}

int main()
{
    double fund = CONCERT_A_FREQ * pow(2.0, (MIDI_NOTE - 69) / 12.0);
    printf("fund = %g\n", fund);

    FILE *f = fopen("/tmp/foo", "w");
    if (!f)
        perror("/tmp/foo"), exit(1);

    for (int i = 0; i < NSAMP; i++) {
        double x = fund / Fs * i;
        double y = square(x, fund);
        // double y = saw(x, fund);
        fprintf(f, "%g\n", y);
    }
    fprintf(f, "end\n");
    fclose(f);
    return 0;
}

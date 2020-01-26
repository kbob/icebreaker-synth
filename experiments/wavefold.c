#include <math.h>
#include <stdio.h>
#include <stdlib.h>

#define M_TAU (2 * M_PI)

#define Fs 44100.
#define F0 110.
#define DURATION 5.15
#define NSAMP ((size_t)(Fs * DURATION))
#define G0 0.7
#define G1 6.

double sine(double t, double f)
{
    return sin(M_TAU * f * t);
}

double triangle(double t, double f)
{
    double y = 0;
    int nh = Fs / 2 / f;
    nh = 4;
    double sign = +1;
    for (int h = 1; h <= nh; h += 2) {
        y += sign * sin(M_TAU * h * f * t) / (h * h);
        sign = -sign;
    }
    return y;
}

double fold(double y)
{
    double sign = y < 0 ? -1 : +1;
    double a = fabs(y);
    double b = floor(a);
    double c = a - b;
    double d;
    switch ((int)b % 4) {

    case 0:
        d = c;
        break;

    case 1:
        d = 1 - c;
        break;

    case 2:
        d = -c;
        break;

    case 3:
        d = c - 1;
        break;
    }
    return sign * d;
}

int main()
{
    FILE *f = fopen("/tmp/foo", "w");
    if (!f) {
        perror("/tmp/foo");
        exit(1);
    }

    for (size_t i = 0; i < NSAMP; i++) {
        double t = i / Fs;
        // double y = triangle(t, F0);
        double y = sine(t, F0);
        y *= (((double)i / NSAMP) * (G1 - G0) + G0);
        y = fold(y);
        fprintf(f, "%g\n", y);
    }

    fprintf(f, "end\n");
    fclose(f);
    return 0;
}

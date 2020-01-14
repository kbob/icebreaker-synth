#include <assert.h>
#include <stdio.h>

#include "fft.h"

static double tweak(double x)
{
    if (fabs(x) < 1.0e-10)
        x = 0;
    return x;
}

void t0(void)
{
    const size_t N = 32;
    double x[N], xx[N];
    double Xre[N / 2 + 1];
    double Xim[N / 2 + 1];
    int r;

    x[0] = 32;
    for (size_t i = 1; i < N; i++) {
        x[i] = 0;
    }

    r = double_real_DFT_1D(N, x, Xre, Xim);
    assert(r == 0);
    for (size_t k = 0; k < N / 2 + 1; k++) {
        printf("%2zu: %7g + %7gi\n", k, Xre[k], Xim[k]);
    }
    putchar('\n');

    r = double_real_iDFT_1D(N, Xre, Xim, xx);
    assert(r == 0);
    for (size_t i = 0; i < N; i++) {
        printf("%2zu: %7g\n", i, tweak(x[i]));
    }
}

int main()
{
    t0();
    return 0;
}

#include "fft.h"

#include <math.h>
#define M_TAU (2.0 * M_PI)

int double_complex_DFT_1D(size_t N,
                          const double complex x[N],
                          const double complex X[N])
{
}

int double_real_DFT_1D(size_t N,
                       const double x[N],
                       double Xre[N / 2 + 1],
                       double Xim[N / 2 + 1])
{
    if (N % 2) {
        return -EINVAL;
    }

    for (size_t k = 0; k < N / 2 + 1; k++) {
        Xre[k] = 0;
        Xim[k] = 0;
        for (size_t i = 0; i < N; i++) {
            Xre[k] += x[i] * cos(M_TAU * k * i / N);
            Xim[k] -= x[i] * sin(M_TAU * k * i / N);
        }
    }

    return 0;                   // success
}

int double_real_iDFT_1D(size_t N,
                        const double Xre[N / 2 + 1],
                        const double Xim[N / 2 + 1],
                        double x[N])
{
    if (N % 2) {
        return -EINVAL;
    }

    // Correct the amplitudes.
    double Xre_[N / 2 + 1];
    double Xim_[N / 2 + 1];
    for (size_t k = 0; k < N / 2 + 1; k++) {
        Xre_[k] = Xre[k] / (N / 2);
        Xim_[k] = -Xim[k] / (N / 2);
    }
    Xre_[0] /= 2;
    Xre_[N / 2] /= 2;

    for (size_t i = 0; i < N; i++) {
        x[i] = 0;
        for (size_t k = 0; k < N / 2 + 1; k++) {
            x[i] += Xre_[k] * cos(M_TAU * k * i / N);
            x[i] += Xim_[k] * sin(M_TAU * k * i / N);
        }
    }

    return 0;                   // success
}


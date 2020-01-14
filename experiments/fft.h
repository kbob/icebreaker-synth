#ifndef FFT_included
#define FFT_included

#include <errno.h>
#include <complex.h>
#include <stddef.h>
#include <stdint.h>

// Types: double, float, fix0_31 fix0_15
// Domains: complex, real
// Operations: DFT, iDFT, FFT, iFFT
// Dimensions: 1D, 2D, nD

typedef int32_t fix0_31;
typedef int16_t fix0_15;

extern int double_complex_DFT_1D(size_t N,
                                 const double complex x[N],
                                 const double complex X[N]);

extern int float_complex_DFT_1D(size_t N,
                                const float complex x[N],
                                const float complex X[N]);

extern int double_real_DFT_1D(size_t N,
                              const double x[N],
                              double Xre[N],
                              double Xim[N]);

extern int double_real_iDFT_1D(size_t N,
                               const double Xre[N],
                               const double Xim[N],
                               double x[N]);

#endif /* !FFT_included */

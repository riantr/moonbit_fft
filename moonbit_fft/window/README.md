# moonbit_fft/window

The window functions that a transform is usually fed with, as a subpackage of
`riantr/moonbit_fft`.

```moonbit
import { "riantr/moonbit_fft" : "fft", "riantr/moonbit_fft/window" : "window" }

let w = window.hanning(n, periodic=true)     // Array[Double], n coefficients
let x = ...                                  // 2 * n floats, interleaved
window.apply_window_floats(x, w)             // multiply, in place
let spectrum = fft.fft(x)
```

`hanning`, `hamming`, `blackman`, `bartlett`, `flattop` and `kaiser` (which takes
a `beta`), plus `bessel_i0`, the application helpers `apply_window` and
`apply_window_floats`, the bridge `to_floats`, and `window_2d`, the separable
window of an image.

## The convention

Every window takes `periodic? : Bool = false`.

* `false` is the **symmetric** window of `numpy`, which divides the argument by
  `n - 1`; its two ends are the same, and it is what a plot of a window shows.
* `true` is the **periodic** window, which divides by `n` and is the symmetric
  window of `n + 1` points with the last one dropped. It is the one that belongs
  to a transform: the symmetric window leaves a step between the last sample and
  the first, which shows up as leakage in the spectrum.

The default is the symmetric one because every package of the MoonBit ecosystem
writes that one and `numpy.hanning` is that one, so the numbers match what a
reader expects; a transform wants `periodic = true`, and the documents of the
functions say so.

A window of one point is `[1]` in both conventions: a window that zeroes the only
sample it has is not a window.

## Where the coefficients come from

The Java original that the rest of the module is verified against has no window
at all, so these functions are **not** part of the port and the oracle cannot
hold them. Their reference is `numpy` for the five closed forms and `scipy` for
the flat top window:

```
python tools/gen_windows.py     # writes window_wbtest.mbt from numpy and scipy
cd moonbit_fft ; moon fmt
```

The two commands reproduce `window_wbtest.mbt` byte for byte, and that file is
the test that runs on every target: it holds the coefficients of both references
at five lengths, symmetric and periodic, to `1e-15` (`1e-13` for Kaiser, whose
reference goes through a Bessel function summed in a different order).

## What this package is not

It is not a signal processing library: there is no window design beyond these
six, no spectral estimate, no short time transform. It exists so that a caller
of `moonbit_fft` can weight its samples before a transform without leaving the
module, and so that an **image** can be weighted in both of its dimensions, which
is the one thing the packages of the ecosystem do not offer - their windows are
one dimensional.

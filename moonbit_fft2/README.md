# moonbit_fft2

A MoonBit port of the N-dimensional FFT algorithm of
[`imglib2-fft`](https://github.com/imglib/imglib2-algorithm-fft)
(`net.imglib2.algorithm.fft2`), including the legacy
[`edu.mines.jtk.dsp`](https://maven.scijava.org/content/repositories/public/edu/mines/mines-jtk/)
JTransforms kernels it is built on.

The original project ships as Java bytecode only, so the port was written
against the disassembly of that bytecode and validated against it: the
Java original is used as an oracle, its output is captured as golden data
and replayed by `moon test` (see *Verification* below).

## Data model

| Type | Meaning |
| --- | --- |
| `RealImage` | real valued N-dimensional image, `Float` samples |
| `ComplexImage` | complex valued N-dimensional image, interleaved `(real, imaginary)` `Float` pairs |
| `Interval` | axis aligned range of positions, one `(min, max)` pair per dimension |

The samples of an image are stored in the linear order of `net.imglib2`:
the **first** dimension is contiguous, i.e. the linear index of the element
at position `p` is `p[0] + p[1] * dims[0] + p[2] * dims[0] * dims[1] + ...`
(see `linear_strides`).  The origin of every image is `(0, 0, ...)`.

## API

### One dimensional transforms

```moonbit
let fft = FftReal::new(8)          // real valued, 8 samples
fft.real_to_complex(-1, rx, cy)     // rx: 8 reals, cy: 10 floats (5 bins)
fft.complex_to_real(1, cy, ry)     // cy: 10 floats, ry: 8 reals

let cfft = FftComplex::new(8)
cfft.complex_to_complex(-1, cx, cy) // cx/cy: 16 floats (8 complex values)
```

`sign` selects the direction: `-1` is the forward transform
`X[k] = sum_j x[j] * exp(-2*pi*i*j*k/n)`, `1` is the **unnormalised**
inverse `X[k] = sum_j x[j] * exp(+2*pi*i*j*k/n)`.  The inverse is not
divided by `n`, exactly like `edu.mines.jtk.dsp.FftComplex`; the scaling is
the job of the `scale` flag of the higher level functions.

`real_to_complex` produces the `nfft / 2 + 1` bins of the spectrum; the
first and the last one are real.  `complex_to_real` expects such a half
spectrum and returns `nfft` real samples, scaled by `nfft` (again because
the inverse transform is unnormalised).

### Transform sizes

The original uses **two different** length tables, and the port reproduces
both of them.

`edu.mines.jtk.dsp.Pfacc` holds the table of the valid transform lengths
(`nfft_valid`), the smallest valid length `>= n` (`nfft_small`) and the
cheapest length that is not much larger than `n` (`nfft_fast`).  A valid
length is `2^a * 3^b * 5^c * 7^d * 11^e * 13^f` with `a <= 4`, `b <= 2` and
`c, d, e, f <= 1`, which gives the 240 lengths of the original tables.
`edu.mines.jtk.dsp.FftComplex` uses exactly this table, so `nfft_small` and
`nfft_fast` are its `nfftSmall` and `nfftFast`.

`edu.mines.jtk.dsp.FftReal` does **not**: a real transform of length `n` is
built on a half length complex transform, so it uses twice the length of
the complex transform of `(n + 1) / 2`:

```moonbit
nfft_small_real(n) == 2 * nfft_small((n + 1) / 2)
nfft_fast_real(n)  == 2 * nfft_fast((n + 1) / 2)
```

The two tables disagree for most lengths, e.g. `nfft_fast_real(32) == 32`
while `nfft_fast(32) == 36`, and the difference is visible in the shape of
the result: a 32 samples wide real image has a spectrum of 17 bins, not of
19.  `nfft_valid_real(n)` reports whether `n` is a valid real transform
length, i.e. whether it is even and whether `n / 2` is a valid complex
length.

### Per dimension transforms

```moonbit
real_to_complex(input, output, range, dim, scale) -> Bool
complex_to_real(input, output, range, dim, scale) -> Bool
complex_to_complex(data, dim, forward, scale) -> Bool
```

These are the ports of `FFTMethods.realToComplex`,
`FFTMethods.complexToReal` and `FFTMethods.complexToComplex`.  `range`
optionally crops the output; it selects the bins of the transform that are
written and the number of samples that are written.  The functions return
`false` when the sizes of the two images are not compatible (the Java
original throws in that case).

`complex_to_real` derives the number of real samples from the *input*, not
from the output: it is `2 * (input.dims[dim] - 1)`, exactly like the Java
original.  The output may be smaller, in that case `range` selects the part
of the result that is written and the written lines start at the origin of
the output image.

### Whole image transforms

```moonbit
fft_real_to_complex(input) -> ComplexImage
fft_real_to_complex_with_fill(input, fill) -> ComplexImage
fft_complex_to_complex_forward(data) -> Unit
fft_complex_to_complex_inverse(data) -> Unit
fft_complex_to_real(input) -> RealImage
fft_complex_to_real_inplace(input, output) -> Unit
fft_complex_to_real_unpad(input, output_dims) -> RealImage
```

These are the ports of `FFT.realToComplex`,
`FFT.complexToComplexForward`, `FFT.complexToComplexInverse`,
`FFT.complexToReal` and `FFT.complexToRealUnpad`.  The forward transform
zero pads the input to the nearest supported size, keeping the original
data centred (`padding_interval_centered`); the inverse transform removes
the padding again (`unpadding_interval_centered`).

`fft_complex_to_real` is the port of the *padded* variant of
`FFT.complexToReal`, and it is the one function of the port that **fails**
instead of returning a result.  The original reads the padded input through
a view of the input image, which is *not* extended, so as soon as the
extent of the result differs from the extent of the input, that view
reaches outside the image and the original throws an
`IndexOutOfBoundsException` (or, in the multi dimensional case, catches it
internally and prints a stack trace, leaving a half written result).  The
port refuses those extents instead, `fft_complex_to_real_supported(dims)`
tells whether an extent is one of the supported ones.  The other two
variants, `fft_complex_to_real_inplace` and `fft_complex_to_real_unpad`,
correspond to the original variants that do not pad and are not affected.

`fft_real_to_complex_with_fill` is the port of the original overload
`FFT.realToComplex(input, oobs, factory)` with a constant out of bounds
strategy: the padding is filled with `fill` instead of with zero.  The
default overload of the original extends the input with a constant of zero,
which is what `fft_real_to_complex` does.

### Helpers

```moonbit
padding_interval_centered(input, padding) -> Interval
unpadding_interval_centered(input, dims) -> Interval
dimensions_real_to_complex_fast(dims, complex_sizes, real_sizes) -> Unit
dimensions_complex_to_real_fast(dims, complex_sizes, real_sizes) -> Unit
dimensions_complex_to_complex_fast(dims, sizes) -> Unit
dimensions_real_to_complex_small(dims, complex_sizes, real_sizes) -> Unit
dimensions_complex_to_real_small(dims, complex_sizes, real_sizes) -> Unit
dimensions_complex_to_complex_small(dims, sizes) -> Unit
verify_real_to_complex_fft_dimensions(real_size, complex_size) -> Bool
verify_complex_to_complex_fft_dimensions(size, other) -> Bool
complex_conjugate(data) -> Unit
```

The `*_fast` helpers mirror the `dimensions*Fast` methods of the original,
the `*_small` helpers mirror its `dimensions*Small` methods, which pick the
smallest supported length instead of the cheapest one.

## Numerical behaviour

The Java original evaluates the transform in single precision with the prime
factor algorithm of `edu.mines.jtk.dsp.Pfacc`.  The port reproduces that
algorithm: the length is split into **pairwise coprime factors** - the same
greedy split over the list `16, 13, 11, 9, 8, 7, 5, 4, 3, 2` that the original
uses - and every factor selects a small kernel.  Because the factors are
coprime, the stages carry no twiddle factor at all, and the twist of the
original, which rotates the output of the small transform, is in the roots of
unity of the small transform instead of in its indices.  The small transform
of a stage is therefore evaluated in place, with no permutation of the array.

For the small transforms the port uses the symmetry of the roots of unity - the
inputs are paired, `A_s = x_s + x_{r-s}` and `B_s = x_s - x_{r-s}`, and the
output `p` is

```
X[p] = x_0 + sum over s of (A_s * cos(2 pi kfac s p / r) - i * B_s * sin(2 pi kfac s p / r))
```

which costs a quarter of the multiplications and a quarter of the additions
of the direct evaluation.  The accumulation of the port is done in **double**
precision and rounded back to single precision at the end, so the difference
to the original is dominated by the rounding error of the original rather than
by the error of the port.

The measured result over the whole verification suite is a largest
deviation of about one unit in the last place of a `float`, i.e. **14 % of
the tolerance** that the parity tests allow (`0.142` as the ratio between the
observed deviation and the tolerance, measured with
`python tools\measure_deviation.py`).  The tests therefore compare
with a relative tolerance of `1e-6`, measured against the magnitude of the
whole result rather than against a single sample: a sample that happens to
be close to zero still carries the rounding error of the whole transform,
so a per sample relative tolerance would be meaningless.

The model of the algorithm, in Python, is checked against `numpy.fft` for
every valid length by `../tools/verify_goodthomas.py`; the worst relative
error over the 240 valid lengths is `9.4e-16`.  That model is the reference of
the implementation: it was fitted against the intermediate state of the
original, which was dumped by an instrumented copy of `Pfacc.java`.

The pre and post processing of the real valued transforms (the halving of
the input, the special treatment of the first and the last bin, the
rotation of the spectrum and the recurrence of the twiddle factors) is a
faithful port of `edu.mines.jtk.dsp.FftReal` and was verified against the
disassembled original.

## Performance

The transform kernel is the prime factor algorithm of the original: the
length is split into pairwise coprime factors, and every factor is applied as
a stage of specialised butterflies.  The roots of unity of the stages and the
work buffers are held in a `FftPlan` that is cached globally, so a transform
of an already used length allocates nothing and evaluates no trigonometric
function.  The plans are bounded by the total number of elements they hold
(`plan_cache_budget`), not by their number.  The butterflies of the stages are
generated by `../tools/gen_kernels.py`; their small transform uses the symmetry
of the roots of unity, see *Numerical behaviour*.

The measured result against the original Java implementation, with the
**release** build: the complex to complex transform of `n = 32 760` takes
<!--v:C2C_MS-->0.9<!--/v--> ms in the port and 0.25 ms in the original, which is
<!--v:C2C_RATIO-->3.7<!--/v-->x.  The port was **five orders of magnitude** slower
than the original before the kernel was rewritten; the rewrite of the kernel
into a mixed radix one and then into the prime factor algorithm of the
original brought it down to that.  The gap is the price of the runtime rather
than of the algorithm - a single array element access costs about 0.67 ns in
MoonBit against about 0.15 ns on the JVM, and a *textbook* radix-2 FFT of
`n = 32768` already needs 1.0 ms here.  That was measured rather than assumed:
the small transforms of the odd radices were rewritten to use a quarter of the
multiplications, and the port got
**<!--v:KERNEL_RANGE-->1.83x to 2.77x for the long transforms, and 0.97x to 1.22x for the short ones<!--/v-->**
faster for it, and the prime factor rewrite of the kernel got it another
**<!--v:GT_RANGE-->1.03x to 1.40x<!--/v-->** faster.  The full comparison, including
the spread of the measurements, is in [`../BENCHMARK.md`](../BENCHMARK.md).

## Deviations from the Java original

1. **Transform kernel** - the prime factor algorithm of `Pfacc` with double
   precision accumulation instead of the single precision accumulation of the
   original, see *Numerical behaviour*.  The algorithm is the same one and the
   stages are the same ones, but the butterflies of the port evaluate the
   small transforms with the symmetry of the roots of unity for every radix,
   where the original does it for the odd ones only, so the two do not
   accumulate in the same order and their results differ by the rounding error
   of the original.
2. **Threading** - the Java original spreads the lines of an image over a
   thread pool, the port is single threaded.  The `ExecutorService` and
   `numThreads` overloads of the original have no counterpart in the port,
   they only choose the thread pool.  The transform plans are kept in a
   global cache, so the module is **not** safe to use from several threads at
   the same time: a transform of a length that is already cached would share
   the work buffers of its plan with the other thread.
3. **Image factories** - the original overloads that take an `ImgFactory`
   create the result image themselves.  The port returns the result
   directly, so those overloads have no counterpart.  The same holds for
   the `OutOfBoundsFactory` overloads of `FFT.realToComplex` with a
   non constant strategy (mirror, wrap, ...): they extend the input with a
   coordinate dependent rule, which the data model of the port cannot
   express.  The constant strategy is ported, see
   `fft_real_to_complex_with_fill`.
4. **Dimension of `complex_to_real`** - the Java
   `FFTMethods.computeComplexToReal1dFFT` reads and writes along
   dimension `0` regardless of the `dim` argument it is given; the port
   uses `dim`.  For `dim = 0`, which is the only case the original
   supports, the behaviour is identical.
5. **Error handling** - unsupported sizes make the Java code throw, the
   port returns `false` from the per dimension transforms and aborts in the
   `FftComplex::new` / `FftReal::new` constructors.  The one exception is
   `fft_complex_to_real`, see *Whole image transforms*.
6. **Scaling flag** - the Java overload
   `FFTMethods.complexToComplex(data, dim, forward)` chooses the scaling
   from the direction (forward: no scaling, inverse: divide by the length).
   The port always takes the flag explicitly.

## Verification

`moon test` runs three groups of tests, 663 in total:

* `fft2_wbtest.mbt` - 28 hand written unit tests of the individual
  functions, including the two length tables and the refusal of the
  unsupported lengths.
* `kernel_wbtest.mbt` - 6 tests of the transform kernel itself: it has to
  reproduce the direct `O(n^2)` evaluation of the transform for 90 lengths
  and for both directions, the forward and the inverse transform have to undo
  each other at **every** valid length of the original, a transform must not
  depend on the transforms that ran before it, the plan of a length has to be
  built once and then reused, the factors of a length have to be pairwise
  coprime - which is the property that keeps the stages free of twiddle
  factors - and the composite butterflies of the radices `4, 8, 9, 16` have to
  reproduce the direct evaluation of the small transform.
* `parity_wbtest.mbt` - 629 generated parity tests.  Every expectation in
  this file is the output of the **original Java bytecode**, captured by
  the oracle in `../tools/java/Oracle.java`; the port has to reproduce it
  within a relative tolerance of `1e-6`.

The parity cases cover

* the per dimension transforms `FFTMethods.realToComplex`,
  `FFTMethods.complexToComplex` and `FFTMethods.complexToReal`, in one,
  two and three dimensions and along different axes,
* the whole image transforms `FFT.realToComplex`,
  `FFT.complexToComplexForward`, `FFT.complexToComplexInverse`,
  `FFT.complexToReal` (both the in place and the padded variant) and
  `FFT.complexToRealUnpad`,
* the helpers `paddingIntervalCentered`, `unpaddingIntervalCentered` and
  the `dimensions*Fast` and `dimensions*Small` methods,
* the four length tables of the original for every length from 1 to 128,
  checked exactly,
* the sizes that a wrong choice of the transform length gets wrong: a 32
  samples wide image, whose spectrum has 17 and not 19 bins, and the odd
  length 5, which is padded to 6,
* the forward transform with a constant out of bounds strategy,
* **every length of the first dimension from 1 to 64** for the dimension
  helpers, for the per dimension transforms and for the whole image
  transforms.  This sweep is what makes the difference between the two
  length tables visible: the hand picked sizes of an earlier revision of
  this suite happened to agree between the two tables and could not tell
  them apart,
* the lengths that the original refuses, both the ones whose half length
  is no valid complex length and the ones whose extent the original cannot
  read without running out of the image.  The oracle records the failures
  of the original and the port has to reproduce them.

To regenerate the golden data and the parity tests:

```powershell
# 1. deterministic test inputs
python tools\gen_cases.py --out build\cases

# 2. lay the original bytecode out under its package path, so that the
#    oracle can be compiled
python tools\stage_classes.py

# 3. run the original Java classes and capture their output
javac -nowarn -encoding UTF-8 `
  -cp "build\classes;tools\lib\imglib2-6.1.0.jar;tools\lib\mines-jtk-20151125.jar" `
  -d build\oracle tools\java\Oracle.java
java -cp "build\oracle;build\classes;tools\lib\imglib2-6.1.0.jar;tools\lib\mines-jtk-20151125.jar" `
  Oracle build\cases\manifest.txt build\cases\java

# 4. turn the golden data into a MoonBit test
python tools\gen_parity.py --cases build\cases --out moonbit_fft2\parity_wbtest.mbt

# 5. run the tests and refresh the published interface file
cd moonbit_fft2 ; moon fmt ; moon check --deny-warn ; moon test ; moon info
```

A fresh clone only needs the tracked files for `moon test`, because the
expectations of the parity tests are inlined in `parity_wbtest.mbt`.  The
steps above regenerate the golden data from the original bytecode and need a
JDK 11 in addition.

The numerical margin of the comparison can be measured with

```powershell
python tools\measure_deviation.py
```

It instruments the generated parity test, runs it and reports the largest
ratio between the observed deviation and the tolerance that the test
allows; the ratio is currently about `0.14`.

A green suite is only worth something if it can turn red.  The negative
control `../tools/negative_control.py` breaks the kernel of the transform on
purpose - for the cosines and the sines of the roots of unity, for the twist
of a stage, for the number of its butterflies, for the plan cache, for the
pairing of the inputs of the symmetric small transform and for the positions
of the butterflies - and checks that the suite fails; it restores the file
afterwards and verifies its checksum.  It also runs a *stress* control in the
other direction: with a tiny plan cache budget the cache drops and rebuilds
its plans over and over again, and the suite has to stay green, because that
is not a defect but a different memory budget.

```powershell
python tools\negative_control.py
```

The model of the algorithm, in Python, is a second, independent check of the
same thing: `../tools/verify_goodthomas.py` evaluates the prime factor
transform in Python and compares it with `numpy.fft` for every valid length of
the original.

```powershell
python tools\verify_goodthomas.py
```

## License

Apache-2.0, like the original project.

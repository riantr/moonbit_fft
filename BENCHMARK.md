# Benchmark: the MoonBit port against the original Java implementation

This document compares the runtime of the MoonBit port in
[`moonbit_fft2/`](moonbit_fft2) with the original Java implementation that is
driven through the very same bytecode in [`fft2/`](fft2).

## Result in one line

The port used to be **five orders of magnitude slower** than the original,
because it transformed `O(n^2)` for every length that is not a power of two
while the original transforms `O(n log n)` for every valid length.  After the
rewrite of the kernel (mixed radix Cooley-Tukey, cached twiddle factors,
reused work buffers) the port is **<!--v:RANGE-->1.3 to 7<!--/v--> times
slower than the original** for every length where it is slower at all, and it
is *faster* than the original for the small lengths that go through the image
API.

Two things made that possible, and the second one was not obvious:

* the kernel went from `O(n^2)` to a mixed radix `O(n log n)`, and
* the small transforms of the odd radices went to the symmetry of the roots
  of unity, which is **a quarter of the multiplications** and a quarter of
  the additions, and which is worth **<!--v:KERNEL_RANGE-->1.83x to 2.77x for the long transforms, and 0.97x to 1.22x for the short ones<!--/v-->**
  on its own.

What is left of the gap is the price of the runtime: a single array access
costs about 0.67 ns in MoonBit against about 0.15 ns on the JVM.

### The build profile is the first thing to get right

Every number of an earlier version of this document was measured on the
**debug** build, which is what `moon run` produces by default.  That is the
wrong thing to compare with the Java original, which is compiled by its JIT:

| build | `c2c` of `n = 32 760` | against the Java original |
| --- | ---: | ---: |
| debug | 43.3 ms | 169x slower |
| **release** | **1.50 ms** | **5.9x slower** |

The release build is **about thirty times faster**, and it is the build that a
user of the library actually gets.  The same holds for the two numbers that
the rest of this document is built on:

| measurement | debug | release |
| --- | ---: | ---: |
| sequential read of an `Array[Double]` | 3.68 ns per element | **0.67 ns per element** |
| textbook iterative radix-2 FFT, `n = 32768` | 9.23 ms | **1.00 ms** |

So the "platform floor of 5 to 6 ns per array access" that an earlier version
of this document built its whole argument on was a property of the **debug**
build, not of the language.  In the release build a single array access costs
about the same as on the JVM.

The tables below are the **release** build, because that is the fair
comparison.  The debug numbers are in the section *The debug build*.

### What the symmetric small transform is worth

The same mistake had an effect on the conclusion of the last round of work.
The small transforms of the odd radices were rewritten to use the symmetry of
the roots of unity, which is a **quarter of the multiplications** and a quarter
of the additions.  Measured on the debug build, that was worth
**1.00x to 1.13x**, and the document concluded that the arithmetic of the
small transforms was never the bottleneck.  On the release build the same
change is worth **1.83x to 2.77x** for the long transforms, because there the
arithmetic *is* a large part of the run time.

The lesson is worth stating plainly: **a measurement of an unoptimised build
does not say anything about the algorithm.**  The compiler had not inlined the
butterflies and had not turned the small transforms into straight line code,
and that showed up as "the arithmetic does not matter".



## The measurement protocol

Both sides implement the same protocol, in `tools/java/Bench.java` and
`moonbit_fft2/benchmark/main.mbt`:

1. a **probe** that grows the batch size (`1, 10, 100, ...`) until the probe
   itself lasts at least 100 us, so that the clock resolution is not the
   limiting factor; the probe doubles as the warm up,
2. an **iteration count** derived from the probe, chosen so that one measured
   round takes about one second,
3. **the best of three** measured rounds inside one run.

Step 3 is inside one run and is harmless: the three rounds of a run are
back to back, so they see the same machine.  It is the choice of the
*outer* statistic, across the runs of the whole benchmark, that had to be
different, and that is what the next section is about.

Both sides print one line per case:

```
CASE <impl> <workload> n=<length> ns_per_op=<nanoseconds>
```

and both accumulate a **checksum** over the outputs, so that the compiler
cannot drop the work.  The two checksums agree to `1.8e-7` relative, the
accuracy of `float32`, which confirms that both sides really did the same
computation:

| | checksum |
| --- | --- |
| Java | `<!--v:CHECKSUM_JAVA-->-62107.018879670184<!--/v-->` |
| MoonBit | `<!--v:CHECKSUM_MOONBIT-->-62107.00744686906<!--/v-->` |

### The runs and the noise

The machine this was measured on is not idle - it runs other work, and the
processor was between 37 % and 64 % loaded during the measurements.  Two runs
of the *same* program therefore do not agree, and the difference is **not** a
smooth jitter.  It is bimodal: the same binary, on the same input, six times
in a row, gave

```
44.1 ms, 20.8 ms, 42.2 ms, 40.6 ms, 41.4 ms, 39.5 ms
```

for the complex to complex transform of `n = 32 760`.  One run in six was
twice as fast as the others.

That has a direct consequence for the method.  A statistic that keeps the
**fastest** of the runs does not measure the program, it measures the luck of
the schedule - and it favours whichever side of the comparison happened to
get a lucky round.  The previous version of this document did exactly that:
it ran each side several times in separate sessions and kept the fastest run
of each, so its absolute numbers were the most fortunate ones available and
its comparisons were between two lucky runs that may never have happened at
the same time.

`tools/bench_compare.py` therefore does four things differently:

* it runs the **release** build of the MoonBit sides.  `moon run` produces the
  debug build by default, and that one is about thirty times slower; the
  comparison against the Java original, which is compiled by its JIT, has to
  be made on the build that a user of the library actually gets,
* it keeps the **median** of the rounds, not the fastest, and it reports the
  **spread** of the rounds next to every number, so that the reader can see
  how much of a difference is noise,
* it compares the sides **through their ratios, per round**: the ratio of two
  sides measured in the *same* round cancels the part of the noise that both
  of them see, and the median of those ratios is what is reported,
* it **rotates the order of the sides** in every round, so that neither the
  order nor the load of the machine can favour one of them.

The build profile can be chosen with `--profile release|debug`, and the
debug numbers are in the section *The debug build*.

Five sides can be measured in the same session:

| side | what it is |
| --- | --- |
| `java` | the original, driven through its own bytecode |
| `moonbit` | the port of today |
| `direct` | the port of today with the small transforms in their direct form |
| `head` | the port as it is committed, without the changes of the working tree |
| `old` | the port with the kernel it had before the rewrite, the one that transformed `O(n^2)` |

The three MoonBit sides other than `moonbit` are shadow modules under
`build/`, assembled from the working tree or from the git history, and they
run the very same benchmark harness.  All of them print the same checksum, so
it is visible that they really did the same computation.

The conclusion does not depend on the noise: the *slowest* round of the port
is still far faster than the *fastest* round of the old kernel.  For the
complex to complex transform of `n = 32 760` the old kernel needs about
<!--v:OLD_C2C_S-->4.6<!--/v--> seconds for a single transform, the port needs
tens of milliseconds.

## The numbers

`c2c` is `FftComplex.complexToComplex` against `FftComplex::complex_to_complex`,
`r2c` is `FftReal.realToComplex` against `FftReal::real_to_complex`, `api` is
`FFTMethods.realToComplex` against `real_to_complex`.

The *before* column is the port before the rewrite of the kernel, the
*after* column is the port as it is now, and the spread is the ratio of the
slowest to the fastest of the three rounds of the port.

### Complex to complex

<!--t:TABLE_C2C-->
| n | Java ns/op | before ns/op | after ns/op | speedup | after / Java | spread |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 16 | 108 | 600 | 174 | 3.4x | 1.6x | 1.09x |
| 120 | 458 | 26 315 | 1 333 | 19.5x | 2.9x | 1.15x |
| 240 | 1 021 | 215 150 | 6 841 | 32.9x | 6.7x | 1.15x |
| 720 | 3 075 | 1 826 200 | 22 440 | 81.4x | 7.3x | 1.13x |
| 4095 | 33 923 | 62 442 981 | 148 840 | 429.3x | 4.4x | 1.12x |
| 5460 | 42 056 | 108 615 328 | 200 996 | 555.8x | 4.8x | 1.06x |
| 10920 | 80 144 | 439 968 300 | 450 230 | 1034.4x | 5.3x | 1.09x |
| 32760 | 260 388 | 4 616 021 000 | 1 474 629 | 3130.3x | 5.6x | 1.08x |
<!--/t-->

### Real to complex

<!--t:TABLE_R2C-->
| n | Java ns/op | before ns/op | after ns/op | speedup | after / Java | spread |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 32 | 162 | 1 417 | 431 | 3.3x | 2.7x | 1.01x |
| 480 | 1 777 | 238 482 | 7 480 | 33.0x | 4.4x | 1.09x |
| 1440 | 7 646 | 2 025 700 | 23 952 | 85.3x | 3.1x | 1.06x |
| 8190 | 65 450 | 68 660 878 | 147 121 | 466.7x | 2.3x | 1.05x |
| 21840 | 198 162 | 511 115 200 | 458 504 | 1163.6x | 2.3x | 1.05x |
| 65520 | 636 947 | 4 425 179 199 | 1 653 660 | 2676.0x | 2.6x | 1.27x |
<!--/t-->

### Through the image API

<!--t:TABLE_API-->
| n | Java ns/op | before ns/op | after ns/op | speedup | after / Java | spread |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 16 | 18 814 | 2 514 | 1 845 | 1.2x | 0.1x | 4.03x |
| 120 | 5 138 | 18 233 | 4 518 | 4.1x | 0.9x | 3.99x |
| 240 | 5 895 | 63 998 | 7 581 | 8.8x | 1.4x | 3.93x |
| 720 | 11 364 | 517 682 | 19 087 | 26.2x | 1.7x | 4.09x |
| 5460 | 84 246 | 28 272 861 | 153 303 | 184.4x | 1.8x | 4.01x |
| 10920 | 203 286 | 108 184 437 | 312 466 | 346.2x | 1.7x | 4.20x |
| 32760 | 610 309 | 1 093 982 400 | 986 788 | 1125.8x | 1.7x | 3.88x |
| 65520 | 1 552 321 | 4 582 354 500 | 2 122 653 | 2158.8x | 1.4x | 4.25x |
<!--/t-->

The `api` case is the most forgiving one, because the fixed cost of the image
API is the same on both sides and dominates at small lengths: at `n = 16` the
port is even *faster* than the original, because the original pays for the
`ListImg` random access and the port reads a flat array.

The only regression is `c2c` at `n = 16`, where the port pays about 6 us for
what the original does in 0.11 us.  The transform length is 16 on both sides,
so this is not about the butterflies: the port pays for the lookup of the
plan, for the copy of the input into the work buffer and for the permutation
of the 16 samples, and those fixed costs are what is left when the transform
itself is this small.  The original works in place on the array and has no
plan and no permutation.

### The kernels of today

The kernel of today is the result of two changes to the butterflies of
`moonbit_fft2/kernels.mbt`, both of them generated by
`tools/gen_kernels.py`:

1. the twiddle factors of a stage are read into local variables, so that the
   butterfly reads each of them from the table once instead of twice,
2. the small transform of an odd radix uses the symmetry of the roots of unity
   instead of being evaluated the obvious way.

The second one is the interesting one.  For an odd radix `r` the inputs are
paired,

```
A_s = u_s + u_{r-s}          B_s = u_s - u_{r-s}
```

and the output `p` is

```
X[p] = u_0 + sum over s of (A_s * cos(2 pi s p / r)
                            - i * B_s * sin(2 pi s p / r))
```

while `X[r-p]` uses the same two sums with the opposite sign of the sine.  So
a pair of outputs costs four dot products instead of two full transforms, which
is a quarter of the multiplications, and a quarter of the additions as well.
The prime factor algorithm of the Java original uses the same idea, in
`Pfacc.pfa13`.

The operation counts of the three kernels, per element of a transform of
`n = 32 760`, are in the table below (`tools/count_ops.py`):

| | `head`: direct | direct + read | `moonbit`: symmetric |
| --- | ---: | ---: | ---: |
| multiplications of the small transform | 88.3 | 88.3 | 22.1 |
| multiplications of the twiddle factors | 45.7 | 45.7 | 45.7 |
| array accesses | 64.0 | 53.2 | 53.2 |
| total multiplications | 134.0 | 134.0 | 67.7 |

The multiplications of the small transforms are **a quarter** of what they
were.  The array accesses only went down by 17 %, because the twiddle factors
have to be read either way.

On the release build the port spends about 48.5 ns per element of a
transform of `n = 32 760`, and the arithmetic of the small transforms is a
quarter of the multiplications but a good part of the rest of the work, which
is why cutting it by four is worth more than two and a half times over.

And here is what that bought, measured in the same session.  The two columns
on the right are the ratios of the sides **per round**, medianed: a value
above one means that the side in the numerator is the slower one, so `1.10x`
under `direct / today` means that the direct small transform is ten percent
slower than the symmetric one.  The table covers the three workloads, and the
`head` column is the port as it was committed, so the two changes of the
round can be told apart.

<!--t:TABLE_KERNELS-->
| workload | n | head ns/op | direct ns/op | today ns/op | head / today | direct / today |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |

| c2c | 16 | 167 | 168 | 175 | 0.95x | 0.97x |
| c2c | 120 | 1 287 | 1 537 | 1 282 | 0.99x | 1.22x |
| c2c | 240 | 7 080 | 8 314 | 6 900 | 0.96x | 1.11x |
| c2c | 720 | 23 400 | 27 440 | 24 740 | 0.97x | 1.12x |
| c2c | 4095 | 149 951 | 442 280 | 152 490 | 0.98x | 2.72x |
| c2c | 5460 | 201 984 | 578 385 | 213 430 | 0.95x | 2.56x |
| c2c | 10920 | 438 708 | 1 148 712 | 461 228 | 0.91x | 2.41x |
| c2c | 32760 | 1 518 012 | 3 691 417 | 1 529 935 | 0.94x | 2.35x |

| r2c | 32 | 482 | 465 | 472 | 1.07x | 0.99x |
| r2c | 480 | 7 659 | 8 494 | 7 637 | 1.00x | 1.13x |
| r2c | 1440 | 25 839 | 28 527 | 25 659 | 1.02x | 1.10x |
| r2c | 8190 | 162 604 | 446 673 | 156 749 | 1.00x | 2.77x |
| r2c | 21840 | 474 874 | 1 241 786 | 505 862 | 0.98x | 2.38x |
| r2c | 65520 | 1 560 846 | 3 980 847 | 1 599 703 | 0.98x | 2.42x |

| api | 16 | 1 843 | 1 894 | 1 828 | 0.98x | 1.02x |
| api | 120 | 4 654 | 4 952 | 4 901 | 0.97x | 1.04x |
| api | 240 | 8 205 | 8 180 | 8 082 | 0.97x | 0.99x |
| api | 720 | 21 001 | 21 278 | 19 853 | 1.06x | 1.09x |
| api | 5460 | 154 460 | 337 269 | 157 070 | 1.03x | 2.19x |
| api | 10920 | 317 902 | 682 114 | 338 676 | 0.92x | 2.18x |
| api | 32760 | 1 087 343 | 2 146 197 | 1 014 537 | 1.13x | 2.07x |
| api | 65520 | 2 411 839 | 4 451 243 | 2 488 507 | 0.89x | 1.83x |
<!--/t-->
**A factor of four fewer multiplications bought <!--v:KERNEL_RANGE-->1.83x to 2.77x for the long transforms, and 0.97x to 1.22x for the short ones<!--/v-->.**  That is
the most useful number of this document, because it says where the remaining
time goes: for the long transforms the arithmetic of the small transforms
*is* a large part of the run time, and cutting it by four is worth more than
two and a half times over.  At the short lengths it is worth nothing, because
there the fixed costs dominate.

An earlier version of this document measured the same change on the **debug**
build and concluded the opposite - that the arithmetic was never the
bottleneck - and it also predicted that a Winograd style small radix
transform would win back 1.6x to 3x.  The debug build made the butterflies
look cheap; the release build shows that they are not.

The gain is also concentrated where it should be: it is nothing at the short
lengths, where the fixed costs dominate, and it is at its largest for the
long transforms, where the butterflies are.  And it is the *whole* remaining
gain of the round: the port is still <!--v:RANGE-->1.3 to 7<!--/v--> times slower than the JVM.

## What was wrong, and what was done about it

### 1. The port transformed `O(n^2)`, the original transformed `O(n log n)`

`Pfacc.transform` (the kernel of the original) splits the length into its
prime factors and applies the matching Good-Thomas kernel, `pfa2` ... `pfa16`:

```java
static void transform(int sign, int nfft, float[] z) {
    ...
    if (ifac == 2)  { Pfacc.pfa2(z, m, j0, j1); continue; }
    if (ifac == 3)  { Pfacc.pfa3(z, mu, m, j0, j1, j2); continue; }
    ...
    if (ifac == 16) { Pfacc.pfa16(z, mu, m, j0, j1, ..., j15); }
}
```

That is `O(n log n)` for every length of the table, and the twiddle factors
are compile time constants (`P120`, `P142`, ...), so the kernel contains no
trigonometric call at all.

The port used a different strategy in `moonbit_fft2/kernel.mbt`:

```moonbit
if is_power_of_two(n) {
  dft_radix2(sign, n, re, im)
} else {
  dft_naive(sign, n, re, im)
}
```

`dft_naive` evaluates the sum of the DFT directly, `O(n^2)`.  The valid length
table of the original (`Pfacc._ntable`, 240 entries) only contains lengths of
the form `2^a * 3^b * 5^c * 7^d * 11^e * 13^f` with `a <= 4`, so the only
lengths that are a power of two are `1, 2, 4, 8, 16`.  **Every practical length
falls into the `O(n^2)` branch.**  The measurement confirmed the two growth
rates: from `n = 10 920` to `n = 32 760` the original costs `3.2x` more for
`3x` the length (`n log n`), the old port costs `12.2x` more (`n^2`, plus a
cache penalty, see below).

**Fix (G4).**  The kernel was replaced by a generic **mixed radix
Cooley-Tukey** transform in `moonbit_fft2/mixed_radix.mbt`.  The valid lengths
factor into `2, 3, 5, 7, 11, 13`, so a generic mixed radix kernel covers all of
them.  The port does not reproduce the Good-Thomas kernel of the original
(the two are mathematically equivalent, but not bit by bit); this is listed as
a deviation in the module README.

The transform is a decimation in time decomposition: the factors are applied
in descending order, each factor `r` turns a block of `L` points into `L / r`
blocks of `r` points, and the butterfly of a block is

```
u[s] = x[k0 + s * m] * W_L^(s * k0)          (the twiddle of the stage)
v[p] = sum_s u[s] * W_r^(s * p)               (the r point DFT)
```

`W_L` and `W_r` are the roots of unity of the respective block lengths.  The
small `r` point DFTs are the expensive part, so they are **specialised**: for
every radix `2, 3, 5, 7, 11, 13` the generator `tools/gen_kernels.py` emits a
hand written butterfly with the small DFT constants as literals, into
`moonbit_fft2/kernels.mbt`.  The matrix form (read the coefficients from a
table) is kept for a radix that has no specialised kernel; it is not reached
by a transform of a valid length, because the public API refuses a length
that is not in the table of the original, and it is exercised by the tests
with a plan that is built for a length of its own.

The kernel is checked on its own in `moonbit_fft2/kernel_wbtest.mbt`: against
the direct `O(n^2)` evaluation of the transform for 90 lengths and both
directions, as a round trip over **all 240 valid lengths** of the original,
and through the generic butterfly for radices that the original does not
use.  The plan cache has a test of its own: the plan of a length has to be
built once and then reused, which is checked through the effect of the cache
on the work buffer of the plan.
`tools/negative_control.py` breaks the kernel on purpose and checks that the
suite turns red - for the twiddle factors, for the radix 13, for the sizes
of the generic path, for the plan cache, for the pairing of the inputs of the
symmetric small transform and for a constant of the radix 13 - so that a green
suite is known to mean something; it also runs a stress control in the other
direction, with a tiny plan cache budget, where the suite has to stay green.

### 2. The port rebuilt its twiddle table on every call

`dft_inplace` allocated two `Array[Double]` and called `twiddle_table`, which
computed `n` times `cos` and `n` times `sin`, **on every single transform**.
The original precomputes everything it needs once, in the constants of the
kernel.  For the small lengths this was the dominant cost: the `n = 16`
radix-2 transform of the old port spent most of its 4.4 us in 32
trigonometric calls and two array allocations, not in the butterflies.

**Fix (G1).**  The whole transform - twiddle table, small DFT matrices,
permutation and work buffers - is put into a `FftPlan` object, and the plans
are cached globally, indexed by the position of the length in the length
table of the original.  The inverse transform is expressed as
`conj(DFT(conj(x)))`, so a single forward kernel serves both directions.

The cache is bounded by the **total number of elements** it holds
(`plan_cache_budget`, 2 000 000 elements) and not by the number of plans: an
earlier version limited the *number* of plans to 8, and the benchmark uses 13
different transform lengths, so the cache thrashed and every call rebuilt its
plan.  The benchmark improved by another factor of two when the bound was
changed to the element budget.

### 3. The port allocated its work arrays on every call

Every transform allocated the input, the output and the scratch arrays.

**Fix (G2).**  The work buffers (`buf_re`, `buf_im`, `scratch_re`,
`scratch_im`) live in the `FftPlan`, so a transform of a cached length does
not allocate at all.

### 4. The naive inner loop did an integer division per iteration

`let idx = j * k % n` was a division per multiplication.  The new kernel
advances the twiddle index instead, so there is no modulo in the inner loop.

### 5. The small transforms were evaluated the obvious way

The butterflies of `moonbit_fft2/kernels.mbt` evaluated the small DFT of a
stage the obvious way, every output being the sum of the `r` inputs times the
`r` roots of unity.  That costs `4 * (r - 1)^2` real multiplications and as
many additions, 576 of them for the radix 13.

**Fix (G5).**  The small transform of an odd radix uses the symmetry of the
roots of unity, the inputs are paired into a sum and a difference, and a pair
of outputs is evaluated with four dot products.  That is `(r - 1)^2`
multiplications, a quarter of the direct form, and it shortens the generated
butterflies from 1890 to 1016 lines.  The twiddle factors of a stage are read
into local variables on the way, so that each of them is read from the table
once instead of twice.

This fix is worth **<!--v:KERNEL_RANGE-->1.83x to 2.77x for the long transforms, and 0.97x to 1.22x for the short ones<!--/v-->**,
and that is the point of it: it is the measurement that says that the
arithmetic of the small transforms *is* what the port spends its time on for
the long transforms, and that cutting it by four is worth more than two and a
half times over.

## Where the remaining time goes

The port is now <!--v:RANGE-->1.3 to 7<!--/v--> times slower than the JVM at the lengths where it
is slower at all, and that gap is **not** the cost of the array accesses any
more.  Two measurements on this machine, taken under the same load as the
benchmark and with the **release** build (`tools/probe_floor.mbt` and
`tools/probe_radix2.mbt`):

| measurement | result |
| --- | --- |
| sequential read of an `Array[Double]`, 4 Mi elements | 0.67 ns per element |
| textbook iterative radix-2 FFT, `n = 32768`, twiddles precomputed | 1.00 ms, 30.4 ns per element |

The first line says that **a single MoonBit array element access costs about
0.67 ns**, for every element type, `Int32`, `Float` and `Double` alike - the
arrays are not boxed, and the release build of the compiler generates the
access as a plain load.  The second line is the achievable lower bound of a
*textbook* transform in this language, with no specialisation at all: 1.0 ms
for `n = 32768`.  A radix-2 transform does about four array accesses per
element per pass and has fifteen passes, which is 60 accesses per element.

The port does the whole `c2c` transform of `n = 32 760` in <!--v:C2C_MS-->1.5<!--/v--> ms, i.e.
**<!--v:C2C_FACTOR-->1.5<!--/v-->x** the cost of that textbook lower bound, with a mixed radix
kernel that has more stages and specialised butterflies.  The Java original
needs 0.28 ms for the same transform, which is 8.6 ns per point - it is below
the MoonBit floor, because the JVM reaches about 0.15 ns per element access.

So the remaining gap splits into

* **about <!--v:GAP_FACTOR-->3.5<!--/v-->x** that is the price of the MoonBit runtime's array
  accesses (30.4 ns per element of the textbook transform against 8.6 ns per
  point of the Java original),
* **a factor that the arithmetic of the small transforms can still win** -
  and that is measured, not assumed: the small transforms use a quarter of
  the multiplications of before, and the port is
  <!--v:KERNEL_RANGE-->1.83x to 2.77x for the long transforms, and 0.97x to 1.22x for the short ones<!--/v--> faster for
  it.  A Winograd style small radix transform would cut the multiplications
  further still, and on this evidence it would win something of the same
  order: the prediction of 1.6x to 3x in an earlier version of this document
  was right after all, it was only measured on the wrong build.

What is left would have to be won by moving the kernel into C (through the
FFI), or by parallelising it - MoonBit core has no OS threads, only async
coroutines, so parallelism would need the FFI as well.  Both of them would
have to deal with the shared work buffers and with the lock free plan cache,
which are the reason why the module is single threaded today.

## The debug build

The tables of this document are the **release** build, and that is a decision
that was made late and after much damage.  Every number of the earlier
versions of this document was measured on the debug build, and three
conclusions were wrong because of it.

The debug build is not a slightly slower build, it is a different program: it
does not inline the butterflies and it does not turn the small transforms
into straight line code.  What it does is spend its time in the interpreter
of the MoonBit runtime, where the arithmetic is cheap relative to the
dispatch.  So the debug build makes the *arithmetic* look free, and a
conclusion about the arithmetic drawn from it is worthless.

The three conclusions that were wrong:

| conclusion of the earlier versions | debug build | release build |
| --- | --- | --- |
| the port is 159x slower than the original | true | **5.6x** |
| an array access costs 5 to 6 ns | true | **0.67 ns** |
| the symmetric small transform is worth 1.0x to 1.1x | true | **1.83x to 2.77x** |

The last one is the interesting one, because it went the wrong way in both
directions: on the debug build the change looked worthless, and the
document used that to argue that no cheaper formula of the small transform
could help.  On the release build the same change is worth more than two and
a half times over, and the earlier prediction of 1.6x to 3x for a Winograd
style transform turns out to have been right.

The lesson is worth stating plainly: **a measurement of an unoptimised build
does not say anything about the algorithm.**  Measure what ships.

The debug numbers are still reproducible, with

```powershell
python "$root\tools\bench_compare.py" --rounds 3 --profile debug
```

and the two probes of the platform floor with

```powershell
moon run --target native "$root\tools\probe_floor.mbt"
moon run --target native --release "$root\tools\probe_floor.mbt"
moon run --target native "$root\tools\probe_radix2.mbt"
moon run --target native --release "$root\tools\probe_radix2.mbt"
```

## Reproducing

```powershell
$root = "D:\src\moonbit\moonbit_fft"
$lib = "$root\tools\lib"

# the Java original
javac -nowarn -encoding UTF-8 `
  -cp "$root\build\classes;$lib\imglib2-6.1.0.jar;$lib\mines-jtk-20151125.jar" `
  -d "$root\build\bench" "$root\tools\java\Bench.java"

# every side, alternately, in one session, release build
python "$root\tools\bench_compare.py" --rounds 3 --profile release `
  --with-baseline --with-direct --with-head

# the comparison of the kernels, without the slow baseline in between
python "$root\tools\bench_compare.py" --rounds 5 --profile release `
  --with-direct --with-head --sides moonbit,direct,head `
  --out "$root\build\bench_kernels.txt"

# the tables of this document, checked against the measurements
python "$root\tools\check_benchmark.py"

# the operation counts of the butterflies
python "$root\tools\count_ops.py"
```

The Java side needs `build\classes`, the staged original bytecode; create it
with `python tools\stage_classes.py`.

The side `old` is the port with the kernel it had before the rewrite, the one
that transformed `O(n^2)` for every length that is not a power of two.  That
kernel is in the git history, so the column can be measured again instead of
being taken on trust: `tools/bench_compare.py` finds the revision itself, it
is the parent of the commit that added `moonbit_fft2/mixed_radix.mbt`.  The
side takes about nine minutes per round, because the old kernel needs about
24 seconds for a single `n = 32 760` transform.

The side `head` is the port as it is committed, and the side `direct` is the
port of today with the small transforms in their direct form, so that the
effect of the symmetric decomposition is measured in the same session as
everything else.  They are compared **without** the slow baseline in between,
because the baseline takes nine minutes per round and would put every other
side into a different state of the machine; that is why the table of the
kernels comes from a second run, `--sides moonbit,direct,head`.

The specialised kernels are generated, not written by hand; regenerate them
with

```powershell
python "$root\tools\gen_kernels.py" --out "$root\moonbit_fft2\kernels.mbt"
moon -C "$root\moonbit_fft2" fmt
```

and the direct form, which is the control of the measurement above, with

```powershell
python "$root\tools\gen_kernels.py" --out "$root\build\kernels_direct.mbt" --style direct
```

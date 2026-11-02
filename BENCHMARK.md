# Benchmark: the MoonBit port against the original Java implementation

This document compares the runtime of the MoonBit port in
[`moonbit_fft2/`](moonbit_fft2) with the original Java implementation that is
driven through the very same bytecode in [`fft2/`](fft2).

## Result in one line

The port used to be **five orders of magnitude slower** than the original,
because it transformed `O(n^2)` for every length that is not a power of two
while the original transforms `O(n log n)` for every valid length.  After the
rewrite of the kernel (mixed radix Cooley-Tukey, cached twiddle factors,
reused work buffers) the port is **<!--v:RANGE-->6.9 to 261<!--/v--> times
slower than the original** for every length where it is slower at all, and it
is *faster* than the original for the small lengths that go through the image
API.

The remaining gap is the price of the runtime, not of the algorithm.  The last
round of work made that concrete: the small transforms of the odd radices were
rewritten so that they use **a quarter of the multiplications**, and the port
got **<!--v:KERNEL_RANGE-->0.98x to 1.13x<!--/v-->** faster - the arithmetic
was never the bottleneck.  What is left is the cost of the array accesses of
the MoonBit runtime, about 5 to 6 ns per element access, against about 0.15 ns
on the JVM.

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

`tools/bench_compare.py` therefore does three things differently:

* it keeps the **median** of the rounds, not the fastest, and it reports the
  **spread** of the rounds next to every number, so that the reader can see
  how much of a difference is noise,
* it compares the sides **through their ratios, per round**: the ratio of two
  sides measured in the *same* round cancels the part of the noise that both
  of them see, and the median of those ratios is what is reported,
* it **rotates the order of the sides** in every round, so that neither the
  order nor the load of the machine can favour one of them.

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
<!--v:OLD_C2C_S-->28.6<!--/v--> seconds for a single transform, the port needs
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
| 16 | 107 | 4 596 | 5 882 | 0.8x | 55.9x | 1.03x |
| 120 | 470 | 371 757 | 94 868 | 3.9x | 193.2x | 1.70x |
| 240 | 1 047 | 1 426 101 | 231 113 | 6.2x | 223.7x | 1.12x |
| 720 | 3 031 | 12 265 620 | 791 455 | 15.5x | 263.0x | 1.13x |
| 4095 | 27 914 | 395 838 899 | 3 783 388 | 105.4x | 139.1x | 1.66x |
| 5460 | 38 788 | 716 781 600 | 5 479 248 | 130.2x | 141.9x | 1.05x |
| 10920 | 78 016 | 2 676 233 300 | 12 601 725 | 204.9x | 161.5x | 1.12x |
| 32760 | 256 742 | 28 603 303 500 | 42 755 153 | 669.0x | 159.6x | 1.16x |
<!--/t-->

### Real to complex

<!--t:TABLE_R2C-->
| n | Java ns/op | before ns/op | after ns/op | speedup | after / Java | spread |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 32 | 155 | 8 195 | 13 432 | 0.6x | 84.9x | 1.11x |
| 480 | 2 388 | 1 446 157 | 251 082 | 5.8x | 105.3x | 1.06x |
| 1440 | 7 930 | 12 646 326 | 890 085 | 14.6x | 112.7x | 1.14x |
| 8190 | 74 723 | 399 833 550 | 3 727 130 | 113.4x | 49.9x | 1.10x |
| 21840 | 202 988 | 2 941 028 400 | 12 986 513 | 226.5x | 66.5x | 2.08x |
| 65520 | 651 196 | 27 549 032 800 | 45 304 418 | 617.6x | 74.4x | 4.08x |
<!--/t-->

### Through the image API

<!--t:TABLE_API-->
| n | Java ns/op | before ns/op | after ns/op | speedup | after / Java | spread |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 16 | 32 293 | 9 397 | 10 990 | 0.8x | 0.3x | 3.57x |
| 120 | 8 443 | 120 718 | 58 336 | 2.0x | 8.1x | 2.96x |
| 240 | 5 643 | 417 330 | 125 283 | 3.0x | 22.7x | 3.20x |
| 720 | 11 360 | 3 168 234 | 393 014 | 7.9x | 36.0x | 3.81x |
| 5460 | 89 517 | 179 335 560 | 2 569 628 | 68.5x | 30.6x | 3.56x |
| 10920 | 229 638 | 728 611 800 | 5 940 706 | 120.8x | 29.5x | 3.35x |
| 32760 | 885 475 | 6 797 098 700 | 19 477 071 | 349.0x | 25.5x | 3.51x |
| 65520 | 1 559 666 | 27 023 012 900 | 44 527 261 | 561.8x | 32.0x | 3.98x |
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

| c2c | 16 | 5 909 | 5 782 | 5 706 | 1.04x | 1.01x |
| c2c | 120 | 113 168 | 108 139 | 104 327 | 1.03x | 1.04x |
| c2c | 240 | 233 622 | 224 717 | 223 845 | 1.03x | 1.00x |
| c2c | 720 | 804 342 | 784 569 | 781 992 | 1.02x | 1.00x |
| c2c | 4095 | 4 146 170 | 4 022 271 | 3 629 243 | 1.15x | 1.12x |
| c2c | 5460 | 6 048 707 | 5 689 115 | 5 298 976 | 1.16x | 1.10x |
| c2c | 10920 | 14 068 363 | 13 027 590 | 12 153 100 | 1.14x | 1.11x |
| c2c | 32760 | 46 791 937 | 44 223 326 | 42 442 459 | 1.10x | 1.04x |

| r2c | 32 | 13 328 | 12 925 | 12 913 | 1.04x | 1.00x |
| r2c | 480 | 251 036 | 240 610 | 235 218 | 1.07x | 1.04x |
| r2c | 1440 | 848 989 | 814 765 | 798 970 | 1.03x | 0.99x |
| r2c | 8190 | 4 191 166 | 3 848 279 | 3 441 852 | 1.21x | 1.12x |
| r2c | 21840 | 14 482 283 | 13 353 961 | 12 241 143 | 1.18x | 1.10x |
| r2c | 65520 | 48 822 515 | 45 716 031 | 41 887 212 | 1.20x | 1.10x |

| api | 16 | 10 650 | 10 151 | 10 172 | 1.07x | 1.00x |
| api | 120 | 63 644 | 55 080 | 54 998 | 1.12x | 1.00x |
| api | 240 | 123 637 | 118 340 | 117 376 | 1.07x | 0.98x |
| api | 720 | 414 964 | 393 381 | 387 174 | 1.11x | 1.06x |
| api | 5460 | 2 991 241 | 2 795 624 | 2 632 840 | 1.20x | 1.10x |
| api | 10920 | 6 808 596 | 6 691 877 | 5 962 412 | 1.19x | 1.12x |
| api | 32760 | 22 969 526 | 22 614 964 | 19 631 722 | 1.16x | 1.13x |
| api | 65520 | 52 244 219 | 49 094 246 | 43 466 077 | 1.20x | 1.10x |
<!--/t-->
**A factor of four fewer multiplications bought <!--v:KERNEL_RANGE-->0.98x to 1.13x<!--/v-->.**  That is
the most useful number of this document, because it says where the remaining
time goes: not into the arithmetic of the small transforms, but into the array
accesses of the runtime.  An earlier version of this document predicted that a
Winograd style small radix transform would win back 1.6x to 3x on the same
ground; the measurement above is what says that the prediction was wrong.

The gain is also concentrated where it should be: it is nothing at the short
lengths, where the fixed costs dominate, and it is at its largest for the
long transforms, where the butterflies are.  And it is the *whole* remaining
gain of the round: the port is still <!--v:RANGE-->6.9 to 261<!--/v--> times slower than the JVM.

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

This fix is worth **<!--v:KERNEL_RANGE-->0.98x to 1.13x<!--/v-->** and not more, and that is the point of
it: it is the measurement that shows that the arithmetic of the small
transforms is not what the port spends its time on.

## Where the remaining time goes

The port is now <!--v:RANGE-->6.9 to 261<!--/v--> times slower than the JVM at the lengths where it
is slower at all, and that gap is **not** algorithmic any more.  Three
measurements on this machine, taken under the same load as the benchmark:

| measurement | result |
| --- | --- |
| sequential read of an `Array[Double]`, 32760 elements | 5.88 ns per element |
| read of an `Array[Double]` of 8192 elements (resident in the cache) | 6.20 ns per element |
| textbook iterative radix-2 FFT, `n = 32768`, twiddles precomputed | 11.29 ms, 344 ns per element |

The second line is the platform floor: **a single MoonBit array element
access costs about 5 to 6 ns** (roughly 15 to 18 cycles), for every element
type, `Int32`, `Float` and `Double` alike - the arrays are not boxed.  The
third line is the achievable lower bound of a *textbook* transform in this
language, with no specialisation at all: 11.3 ms for `n = 32768`.  A radix-2
transform does about four array accesses per element per pass and has fifteen
passes, which is 60 accesses per element, and 60 times 5.9 ns is the 344 ns
that are measured.

The port does the whole `c2c` transform of `n = 32 760` in <!--v:C2C_MS-->42.8<!--/v--> ms, i.e.
**<!--v:C2C_FACTOR-->3.8<!--/v-->x** the cost of that textbook lower bound, with a mixed radix
kernel that has more stages and specialised butterflies.  The Java original
needs 0.28 ms for the same transform, which is 8.6 ns per point - it is below
the MoonBit floor, because the JVM reaches about 0.15 ns per element access.

So the remaining gap splits into

* **about <!--v:GAP_FACTOR-->40<!--/v-->x** that is the price of the MoonBit runtime's array
  accesses (344 ns per element of the textbook transform against 8.6 ns per
  point of the Java original),
* **nothing that a cheaper formula of the small transform can win back** - and
  that is measured, not assumed: the small transforms use a quarter of the
  multiplications of before, and the port is only <!--v:KERNEL_RANGE-->0.98x to 1.13x<!--/v--> faster for
  it.  An earlier version of this document predicted that a Winograd style
  small radix transform would win back 1.6x to 3x; that prediction was wrong,
  and the measurement above is what says so.

What is left would have to be won by moving the kernel into C (through the
FFI), or by parallelising it - MoonBit core has no OS threads, only async
coroutines, so parallelism would need the FFI as well.  Both of them would
have to deal with the shared work buffers and with the lock free plan cache,
which are the reason why the module is single threaded today.

## Reproducing

```powershell
$root = "D:\src\moonbit\moonbit_fft"
$lib = "$root\tools\lib"

# the Java original
javac -nowarn -encoding UTF-8 `
  -cp "$root\build\classes;$lib\imglib2-6.1.0.jar;$lib\mines-jtk-20151125.jar" `
  -d "$root\build\bench" "$root\tools\java\Bench.java"

# every side, alternately, in one session
python "$root\tools\bench_compare.py" --rounds 3 `
  --with-baseline --with-direct --with-head

# the comparison of the kernels, without the slow baseline in between
python "$root\tools\bench_compare.py" --rounds 5 `
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

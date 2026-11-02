# Benchmark: the MoonBit port against the original Java implementation

This document compares the runtime of the MoonBit port in
[`moonbit_fft2/`](moonbit_fft2) with the original Java implementation that is
driven through the very same bytecode in [`fft2/`](fft2).

## Result in one line

The port used to be **five orders of magnitude slower** than the original,
because it transformed `O(n^2)` for every length that is not a power of two
while the original transforms `O(n log n)` for every valid length.  After the
rewrite of the kernel (mixed radix Cooley-Tukey, cached twiddle factors,
reused work buffers) the port is **within a factor of 9.6 to 158** of the
original for every length that matters, and it is *faster* than the original
for the small lengths that go through the image API.

The remaining gap is the price of the runtime, not of the algorithm: it is
dominated by the cost of the array accesses of the MoonBit runtime (about 5
to 6 ns per element access, measured), while the JVM does the same accesses
in about 0.15 ns.

## The measurement protocol

Both sides implement the same protocol, in `tools/java/Bench.java` and
`moonbit_fft2/benchmark/main.mbt`:

1. a **probe** that grows the batch size (`1, 10, 100, ...`) until the probe
   itself lasts at least 100 us, so that the clock resolution is not the
   limiting factor; the probe doubles as the warm up,
2. an **iteration count** derived from the probe, chosen so that one measured
   round takes about one second,
3. **the best of three** measured rounds inside one run.

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
| Java | `-62107.018879670184` |
| MoonBit | `-62107.00744686906` |

### The runs and the noise

The machine this was measured on is not idle - it runs other work, and the
processor was between 37 % and 64 % loaded during the measurements.  The
individual runs of the port therefore differ a lot, and the difference is
**not** uniform over the table: it is the fixed overhead of the small cases
that suffers the most, because a fixed cost is what the load adds to.

To take that out of the comparison, **both sides were run several times and
the fastest result per case was kept** (`tools/merge_bench.py`):

* the Java side: 3 runs, the fastest per case; the spread over the runs is
  between 1.0x and 4.2x per case,
* the MoonBit side: 5 runs, the fastest per case; the spread over the runs is
  between 1.2x and 5.1x per case,
* the old kernel: 3 runs, the fastest per case; the spread is up to 7.8x.
  Two of them are the runs of the port before the rewrite and one was
  measured again from the git history, with `tools/bench_baseline.py`.  All
  three measure the same program: the two historical runs and the
  reproduction agree in shape, and every run that carries the checksum prints
  the same value.

The numbers below are these fastest results, so they pair the best run of the
port with the best run of the original.  That is the most favourable
comparison for the port, and a reader who prefers the pessimistic end of the
spread should expect the ratio to move by a factor of several in either
direction.

The conclusion does not depend on that: the *slowest* run of the port is
still far faster than the *fastest* run of the old kernel.  For the complex
to complex transform of `n = 32 760` the slowest port run took 70.5 ms and
the fastest old run took 34.7 s, which is a factor of **493** in the worst
case for the port and 1 158 in the best one.

## The numbers

`c2c` is `FftComplex.complexToComplex` against `FftComplex::complex_to_complex`,
`r2c` is `FftReal.realToComplex` against `FftReal::real_to_complex`, `api` is
`FFTMethods.realToComplex` against `real_to_complex`.

The *before* column is the port before the rewrite of the kernel, the
*after* column is the port as it is now.

### Complex to complex

| n | Java ns/op | MoonBit before ns/op | MoonBit after ns/op | speedup | after / Java |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 16 | 115 | 4 390 | 7 347 | 0.6x | 63.9x |
| 120 | 487 | 320 788 | 71 828 | 4.5x | 147.5x |
| 240 | 1 067 | 1 328 024 | 147 328 | 9.0x | 138.1x |
| 720 | 3 412 | 12 152 108 | 537 976 | 22.6x | 157.7x |
| 4 095 | 30 129 | 373 232 450 | 2 849 099 | 131.0x | 94.6x |
| 5 460 | 42 701 | 672 324 900 | 4 065 406 | 165.4x | 95.2x |
| 10 920 | 88 708 | 2 857 858 900 | 9 147 006 | 312.4x | 103.1x |
| 32 760 | 281 191 | 34 746 693 300 | **29 999 635** | **1 158.2x** | 106.7x |

### Real to complex

| n | Java ns/op | MoonBit before ns/op | MoonBit after ns/op | speedup | after / Java |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 32 | 168 | 12 087 | 8 712 | 1.4x | 51.9x |
| 480 | 2 106 | 1 804 711 | 164 967 | 10.9x | 78.3x |
| 1 440 | 8 234 | 8 738 204 | 531 702 | 16.4x | 64.6x |
| 8 190 | 73 057 | 304 473 933 | 3 296 111 | 92.4x | 45.1x |
| 21 840 | 215 616 | 2 193 405 800 | 9 748 115 | 225.0x | 45.2x |
| 65 520 | 686 113 | 29 131 586 400 | **30 884 145** | **943.3x** | 45.0x |

### Through the image API

| n | Java ns/op | MoonBit before ns/op | MoonBit after ns/op | speedup | after / Java |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 16 | 25 151 | 9 418 | 8 722 | 1.1x | 0.3x |
| 120 | 4 174 | 127 472 | 40 096 | 3.2x | 9.6x |
| 240 | 5 756 | 392 899 | 90 203 | 4.4x | 15.7x |
| 720 | 11 964 | 3 211 268 | 314 167 | 10.2x | 26.3x |
| 5 460 | 93 701 | 196 074 450 | 2 133 814 | 91.9x | 22.8x |
| 10 920 | 202 713 | 917 636 000 | 4 645 541 | 197.5x | 22.9x |
| 32 760 | 702 668 | 6 845 123 300 | 17 720 253 | 386.3x | 25.2x |
| 65 520 | 1 493 525 | 27 165 519 300 | **43 021 738** | **631.4x** | 28.8x |

The `api` case is the most forgiving one, because the fixed cost of the image
API is the same on both sides and dominates at small lengths: at `n = 16` the
port is even *faster* than the original, because the original pays for the
`ListImg` random access and the port reads a flat array.

The only regression is `c2c` at `n = 16`, where the port pays 7.3 us for what
the original does in 0.12 us.  The transform length is 16 on both sides, so
this is not about the butterflies: the port pays for the lookup of the plan,
for the copy of the input into the work buffer and for the permutation of the
16 samples, and those fixed costs are what is left when the transform itself
is this small.  The original works in place on the array and has no plan and
no permutation.

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
table) is kept as a fallback for a radix that has no specialised kernel.

The kernel is checked on its own in `moonbit_fft2/kernel_wbtest.mbt`: against
the direct `O(n^2)` evaluation of the transform for 90 lengths and both
directions, as a round trip over **all 240 valid lengths** of the original,
and through the generic butterfly for radices that the original does not
use.  The plan cache has a test of its own: the plan of a length has to be
built once and then reused, which is checked through the effect of the cache
on the work buffer of the plan.
`tools/negative_control.py` breaks the kernel on purpose and checks that the
suite turns red - for the twiddle factors, for the radix 13, for the sizes
of the generic path and for the plan cache - so that a green suite is known
to mean something; it also runs a stress control in the other direction,
with a tiny plan cache budget, where the suite has to stay green.

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

## Where the remaining time goes

The port is now 9.6x to 158x slower than the JVM, and that gap is **not**
algorithmic any more.  Three measurements on this machine, taken under the
same load as the benchmark:

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

The port does the whole `c2c` transform of `n = 32 760` in 30.0 ms, i.e.
**2.7x** the cost of that textbook lower bound, with a mixed radix kernel
that has more stages and specialised butterflies.  The Java original needs
0.28 ms for the same transform, which is 8.6 ns per point - it is below the
MoonBit floor, because the JVM reaches about 0.15 ns per element access.

So the remaining gap splits into

* **about 1.6x to 3x** that a Winograd style small radix DFT could win back:
  the `r` point DFTs are evaluated with `r^2` complex multiplications (37 per
  element for the radices used here), Winograd reduces that to about 6,
* **about 40x** that is the price of the MoonBit runtime's array accesses
  (344 ns per element of the textbook transform against 8.6 ns per point of
  the Java original).

The first is a constant factor that a careful implementation can win; the
second is the price of the platform and can only be won by moving the kernel
into C (through the FFI), or by parallelising it - MoonBit core has no OS
threads, only async coroutines, so parallelism would need the FFI as well.
Both of them would have to deal with the shared work buffers and with the
lock free plan cache, which are the reason why the module is single threaded
today.

## Reproducing

```powershell
$root = "D:\src\moonbit\moonbit_fft"
$lib = "$root\tools\lib"

# the Java original
javac -nowarn -encoding UTF-8 `
  -cp "$root\build\classes;$lib\imglib2-6.1.0.jar;$lib\mines-jtk-20151125.jar" `
  -d "$root\build\bench" "$root\tools\java\Bench.java"
java -cp "$root\build\bench;$root\build\classes;$lib\imglib2-6.1.0.jar;$lib\mines-jtk-20151125.jar" `
  Bench > "$root\build\bench_java.txt"

# the MoonBit port
moon -C "$root\moonbit_fft2" run --target native ./benchmark > "$root\build\bench_moonbit.txt"

# the fastest of several runs of each side
python "$root\tools\merge_bench.py" "$root\build\bench_java*.txt" > "$root\build\bench_java_merged.txt"
python "$root\tools\merge_bench.py" "$root\build\bench_moonbit*.txt" > "$root\build\bench_moonbit_merged.txt"

# the table
python "$root\tools\compare_bench.py" "$root\build\bench_java_merged.txt" "$root\build\bench_moonbit_merged.txt"
```

The Java side needs `build\classes`, the staged original bytecode; create it
with `python tools\stage_classes.py`.

### Reproducing the *before* column

The *before* column is the port with the old kernel - the one that
transformed `O(n^2)` for every length that is not a power of two.  That
kernel is in the git history, so the column can be measured again instead of
being taken on trust:

```powershell
python "$root\tools\bench_baseline.py" --rev HEAD --out "$root\build\bench_moonbit_head.txt"
```

The script assembles a shadow module under `build/oldmodule` from the current
module, replaces the two files that the kernel rewrite touched with the ones
of the given revision and runs the benchmark of the port there.  It takes
about fifteen minutes, because the old kernel needs 35 s for a single
`n = 32 760` transform.

The MoonBit side now takes a few minutes instead of a quarter of an hour:
the `O(n^2)` path of the old port needed 35 s for a single `n = 32 760`
transform, and the benchmark runs it five times; the mixed radix kernel needs
30 ms for the same transform.

The specialised kernels are generated, not written by hand; regenerate them
with

```powershell
python "$root\tools\gen_kernels.py" --out "$root\moonbit_fft2\kernels.mbt"
moon -C "$root\moonbit_fft2" fmt
```

The tables of this document are checked against the measurements, so that
they cannot drift away from the runs they claim to show:

```powershell
python "$root\tools\check_benchmark.py"
```

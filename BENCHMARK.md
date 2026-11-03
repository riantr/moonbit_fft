# Benchmark: the MoonBit port against the original Java implementation

This document compares the runtime of the MoonBit port in
[`moonbit_fft2/`](moonbit_fft2) with the original Java implementation that is
driven through the very same bytecode in [`fft2/`](fft2).

## Result in one line

The port used to be **five orders of magnitude slower** than the original,
because it transformed `O(n^2)` for every length that is not a power of two
while the original transforms `O(n log n)` for every valid length.  After the
rewrite of the kernel (mixed radix Cooley-Tukey, cached twiddle factors,
reused work buffers) and after the second rewrite, which replaced it by the
**prime factor algorithm of the original itself**, the port is
**<!--v:RANGE-->1.1 to 5<!--/v--> times slower than the original** for every length
where it is slower at all, and it is *at parity* with the original for the
long transforms that go through the image API.

Three things made that possible, and the third one was not obvious:

* the kernel went from `O(n^2)` to a mixed radix `O(n log n)`,
* the small transforms of the odd radices went to the symmetry of the roots
  of unity, which is **a quarter of the multiplications** and a quarter of
  the additions, and which is worth **<!--v:KERNEL_RANGE-->1.83x to 2.77x for the long transforms, and 0.97x to 1.22x for the short ones<!--/v-->**
  on its own,
* and the length was finally split the way the original splits it, into
  **pairwise coprime factors**, which removes the twiddle factors between the
  stages altogether.  That is worth
  **<!--v:GT_RANGE-->1.03x to 1.40x<!--/v-->**, and it is the reason why the port
  now needs **fewer array accesses than the original itself**, where the
  committed port needed twice as many.

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
| MoonBit | `<!--v:CHECKSUM_MOONBIT-->-62107.00744685416<!--/v-->` |

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
<!--v:OLD_C2C_S-->4.1<!--/v--> seconds for a single transform, the port needs
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
| 16 | 105 | 566 | 134 | 4.2x | 1.3x | 1.03x |
| 120 | 429 | 25 620 | 942 | 27.3x | 2.1x | 1.04x |
| 240 | 1 048 | 198 731 | 4 432 | 44.9x | 4.2x | 2.09x |
| 720 | 3 016 | 1 703 640 | 14 549 | 116.9x | 4.8x | 1.70x |
| 4095 | 26 094 | 56 101 494 | 100 184 | 560.0x | 3.9x | 1.97x |
| 5460 | 38 644 | 98 628 390 | 137 686 | 729.7x | 3.6x | 2.07x |
| 10920 | 80 295 | 415 069 650 | 289 650 | 1433.0x | 3.6x | 2.10x |
| 32760 | 253 861 | 4 133 978 900 | 940 273 | 4341.5x | 3.8x | 2.09x |
<!--/t-->

### Real to complex

<!--t:TABLE_R2C-->
| n | Java ns/op | before ns/op | after ns/op | speedup | after / Java | spread |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 32 | 149 | 1 332 | 310 | 4.5x | 2.1x | 1.88x |
| 480 | 1 584 | 198 993 | 5 128 | 39.0x | 3.2x | 2.07x |
| 1440 | 7 300 | 1 716 555 | 16 462 | 104.3x | 2.2x | 1.79x |
| 8190 | 61 522 | 56 672 172 | 111 359 | 508.9x | 1.8x | 2.04x |
| 21840 | 179 446 | 417 781 450 | 311 814 | 1332.8x | 1.7x | 2.03x |
| 65520 | 595 216 | 4 078 435 100 | 1 022 627 | 3975.0x | 1.7x | 2.06x |
<!--/t-->

### Through the image API

<!--t:TABLE_API-->
| n | Java ns/op | before ns/op | after ns/op | speedup | after / Java | spread |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 16 | 19 763 | 2 276 | 1 527 | 1.4x | 0.1x | 1.95x |
| 120 | 9 256 | 16 728 | 3 266 | 5.1x | 0.4x | 1.07x |
| 240 | 4 967 | 55 975 | 5 381 | 10.4x | 1.1x | 1.04x |
| 720 | 10 524 | 438 088 | 14 158 | 31.1x | 1.3x | 1.02x |
| 5460 | 80 938 | 24 981 687 | 118 692 | 206.7x | 1.5x | 1.05x |
| 10920 | 174 327 | 99 947 470 | 245 082 | 407.8x | 1.4x | 1.03x |
| 32760 | 701 666 | 973 604 200 | 764 046 | 1262.7x | 1.1x | 1.09x |
| 65520 | 1 572 274 | 4 032 145 000 | 1 545 634 | 2635.2x | 1.0x | 1.03x |
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

### The kernels of the committed port

The kernel of the committed port is the result of two changes to the
butterflies of `moonbit_fft2/kernels.mbt`, both of them generated by
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
long transforms, where the butterflies are.

### The prime factor algorithm of the original

The second rewrite of the kernel did not make the port faster by a clever
trick, it made it faster by **using the algorithm of the original**.

`Pfacc.transform` does not split the length into prime factors, it splits it
into **pairwise coprime factors**: it walks the list
`16, 13, 11, 9, 8, 7, 5, 4, 3, 2` and takes every factor that divides the
length.  For `n = 32 760` that gives

```
13 * 9 * 8 * 7 * 5
```

five stages, and the factors are pairwise coprime.  A mixed radix transform
of the same length needs eight stages (`13 * 7 * 5 * 3 * 3 * 2 * 2 * 2`) and
carries a twiddle factor from one stage into the next.  The prime factor
algorithm does not carry any, and that is where most of its advantage comes
from: with coprime factors the stages act on different coordinates of the
transform, so they need no twiddle factors at all.

The port had been doing the mixed radix thing all along, and the two are not
the same.  The mixed radix transform of `n = 32 760` needed **43.7
multiplications and 42.8 array accesses per element**; the prime factor
algorithm of the original needs **21.4 and 30.0**, and the port now needs
**29.1 and 20.0**.

The structure of one stage is this.  The stage has the radix `r`, the length
is `n` and `m = n / r` is the number of butterflies of the stage.  The value
`kfac` is the inverse of `m` modulo `r`; it is the **twist** of the stage.
The butterfly of the round `i` takes its `r` values from the positions

```
p[t] = m * ((t * kfac) mod r)      for t = 0 .. r - 1
```

applies a discrete Fourier transform of the size `r` to them, in which the
roots of unity are raised to the power `kfac`, and writes the result back to
the same positions.  The twist is in the **roots of unity and not in the
indices**, so the small transform needs no permutation at all, and the
positions of the next round follow from the ones of the current one: every
offset loses `kfac` and wraps around, which is one comparison and one
conditional addition per value.

That model was found by instrumenting the original, not by guessing it: the
decompiled `Pfacc.java` was run with a probe that dumps the intermediate
state of every stage, and the Python model was fitted against those dumps
until it reproduced them for every length.  The model is checked against
`numpy.fft` for every valid length by `tools/verify_goodthomas.py`, and the
worst relative error over the 240 valid lengths is **9.4e-16**.

The operation counts of the two sides, per element of a transform of
`n = 32 760`, are in the table below.  `tools/count_ops.py` counts the
generated MoonBit kernels and the decompiled Java kernels, the multiplications
and the additions of the values and the accesses of the array:

| | the original | the port |
| --- | ---: | ---: |
| multiplications | 21.4 | 29.1 |
| additions | 49.5 | 55.4 |
| floating point operations | 70.9 | 84.5 |
| array accesses | 30.0 | 20.0 |

The port does **more** arithmetic than the original, because the small
transform of an even radix uses the symmetry of the roots of unity as well,
which the original does for the odd radices only.  It does **fewer** array
accesses, because it keeps the values of a butterfly in local variables where
the original reads them from the array again.  The arithmetic of the port is
within a factor of **1.19** of the arithmetic of the original, and its array
accesses are a third cheaper.

And here is what it bought, measured in the same session.  The `head` side is
the port as it is committed, the `today` side is the port of the working
tree, and the ratio is taken per round and then medianed, so that the part of
the noise that both sides see cancels out.  A value above one under
`head / today` means that the committed port is the slower one.

<!--t:TABLE_GOODTHOMAS-->
| workload | n | Java ns/op | head ns/op | today ns/op | head / today | today / Java |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| c2c | 16 | 105 | 164 | 134 | 1.22x | 1.28x |
| c2c | 120 | 429 | 1 240 | 942 | 1.34x | 2.15x |
| c2c | 240 | 1 048 | 6 136 | 4 432 | 1.37x | 4.19x |
| c2c | 720 | 3 016 | 20 600 | 14 549 | 1.40x | 4.76x |
| c2c | 4095 | 26 094 | 128 806 | 100 184 | 1.29x | 3.92x |
| c2c | 5460 | 38 644 | 178 324 | 137 686 | 1.34x | 3.56x |
| c2c | 10920 | 80 295 | 387 823 | 289 650 | 1.32x | 3.61x |
| c2c | 32760 | 253 861 | 1 295 814 | 940 273 | 1.38x | 3.75x |

| r2c | 32 | 149 | 401 | 310 | 1.27x | 2.14x |
| r2c | 480 | 1 584 | 6 832 | 5 128 | 1.34x | 3.24x |
| r2c | 1440 | 7 300 | 22 560 | 16 462 | 1.35x | 2.23x |
| r2c | 8190 | 61 522 | 139 751 | 111 359 | 1.24x | 1.81x |
| r2c | 21840 | 179 446 | 413 603 | 311 814 | 1.33x | 1.74x |
| r2c | 65520 | 595 216 | 1 398 954 | 1 022 627 | 1.36x | 1.73x |

| api | 16 | 19 763 | 1 608 | 1 527 | 1.03x | 0.07x |
| api | 120 | 9 256 | 3 649 | 3 266 | 1.11x | 0.35x |
| api | 240 | 4 967 | 6 190 | 5 381 | 1.15x | 1.10x |
| api | 720 | 10 524 | 17 104 | 14 158 | 1.22x | 1.35x |
| api | 5460 | 80 938 | 130 861 | 118 692 | 1.10x | 1.49x |
| api | 10920 | 174 327 | 277 784 | 245 082 | 1.13x | 1.39x |
| api | 32760 | 701 666 | 873 500 | 764 046 | 1.14x | 1.11x |
| api | 65520 | 1 572 274 | 1 902 731 | 1 545 634 | 1.24x | 0.99x |
<!--/t-->

**The prime factor rewrite bought <!--v:GT_RANGE-->1.03x to 1.40x<!--/v-->.**  It is the
largest gain since the kernel was rewritten at all, and it is the one that
brings the port closest to the original: at the long lengths of the `api`
workload the port is now *at parity* with the original, and at the long
lengths of the `c2c` workload it is **3.8x** slower, against **5.2x** before
the rewrite.

The two facts that make the rewrite pay are worth stating separately, because
they are the two halves of the whole idea:

* **no twiddle factors between the stages.**  The mixed radix kernel of the
  committed port spends 45.7 multiplications per element on the twiddle
  factors of its stages, and the prime factor algorithm spends none of them.
* **no permutation of the output.**  The twist of the original rotates the
  output of the small transform, and the mixed radix kernel had to undo that
  with a permutation of the whole array, four accesses per element.  In the
  prime factor algorithm the twist is in the roots of unity, so the small
  transform writes its result where it read its input.

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
them.

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
`moonbit_fft2/kernels.mbt`.

**Fix (G6).**  The mixed radix transform was replaced by the **prime factor
algorithm of the original**, in the section *The prime factor algorithm of the
original* above.  The port now reproduces the algorithm of the original
instead of an equivalent one: the length is split into pairwise coprime
factors, the stages carry no twiddle factor and the small transform needs no
permutation.  The deviation that the module README used to list - that the
port does not reproduce the Good-Thomas kernel of the original - is gone; what
is left of it is the double precision accumulation.

The kernel is checked on its own in `moonbit_fft2/kernel_wbtest.mbt`: against
the direct `O(n^2)` evaluation of the transform for 90 lengths and both
directions, as a round trip over **all 240 valid lengths** of the original,
and against the composite butterflies of the radices `4, 8, 9, 16` for a set of
lengths.  The factors of a length have to be pairwise coprime, which is the
property that makes the stages free of twiddle factors, and that is a test of
its own.  The plan cache has a test of its own: the plan of a length has to be
built once and then reused, which is checked through the effect of the cache
on the work buffer of the plan.
`tools/negative_control.py` breaks the kernel on purpose and checks that the
suite turns red - for the cosines and the sines of the roots of unity, for the
twist of a stage, for the number of its butterflies, for the plan cache, for
the pairing of the inputs of the symmetric small transform and for the
positions of the butterflies - so that a green suite is known to mean
something; it also runs a stress control in the other direction, with a tiny
plan cache budget, where the suite has to stay green.  Seven controls, all of
them red, and the stress control green.

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

The prime factor rewrite of the kernel (G6) keeps that symmetry and adds the
twist of the stage to it, so the small transform of a stage is the same
symmetric form with the roots of unity raised to the power of the twist.

## Where the remaining time goes

The port is now <!--v:RANGE-->1.1 to 5<!--/v--> times slower than the JVM at the lengths where it
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

The port does the whole `c2c` transform of `n = 32 760` in <!--v:C2C_MS-->0.9<!--/v--> ms, i.e.
**<!--v:C2C_FACTOR-->0.9<!--/v-->x** the cost of that textbook lower bound, with a prime factor
kernel that has fewer stages than a mixed radix one and specialised
butterflies.  The Java original needs 0.25 ms for the same transform, which is
7.7 ns per point - it is below the MoonBit floor, because the JVM reaches
about 0.15 ns per element access.

So the remaining gap splits into

* **about <!--v:GAP_FACTOR-->3.5<!--/v-->x** that is the price of the MoonBit runtime's array
  accesses (30.4 ns per element of the textbook transform against 7.7 ns per
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
| the port is 159x slower than the original | true | **3.6x** |
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
python "$root\tools\bench_compare.py" --rounds 5 --profile release `
  --with-baseline --with-head --sides java,moonbit,head,old

# the comparison of the kernels, without the slow baseline in between
python "$root\tools\bench_compare.py" --rounds 5 --profile release `
  --with-direct --with-head --sides moonbit,direct,head `
  --out "$root\build\bench_kernels.txt"

# the tables of this document, checked against the measurements
python "$root\tools\check_benchmark.py"

# the operation counts of the butterflies, on both sides
python "$root\tools\count_ops.py"

# the model of the prime factor algorithm, checked against numpy
python "$root\tools\verify_goodthomas.py"
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
port with the small transforms in their direct form, so that the effect of
the symmetric decomposition is measured in the same session as everything
else.  They are compared **without** the slow baseline in between, because the
baseline takes nine minutes per round and would put every other side into a
different state of the machine; that is why the table of the kernels comes
from a second run, `--sides moonbit,direct,head`.

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

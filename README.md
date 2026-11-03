# moonbit_fft

A MoonBit port of the `fft2` algorithm of
[`imglib2-fft`](https://github.com/imglib/imglib2-algorithm-fft)
(`net.imglib2.algorithm.fft2`), the N-dimensional FFT of `net.imglib2`
images that is built on the legacy `edu.mines.jtk.dsp` JTransforms
kernels.

The port itself lives in [`moonbit_fft2/`](moonbit_fft2) and is a
self-contained MoonBit module; its documentation, API description and
list of deviations from the Java original are in
[`moonbit_fft2/README.md`](moonbit_fft2/README.md).

## Repository layout

| Path | Content | Tracked |
| --- | --- | --- |
| `fft2/` | the **original** Java bytecode of `net.imglib2.algorithm.fft2` (`FFT`, `FFTMethods`), the oracle of this port | yes |
| `moonbit_fft2/` | the MoonBit module `riantr/moonbit_fft2` | yes |
| `moonbit_fft2/benchmark/` | the benchmark of the port, the counterpart of `tools/java/Bench.java` | yes |
| `tools/java/Oracle.java` | harness that drives the original bytecode and dumps its results as golden data | yes |
| `tools/java/Bench.java` | benchmark of the original Java implementation | yes |
| `tools/gen_cases.py` | generates the deterministic test inputs and the manifest | yes |
| `tools/gen_parity.py` | turns the golden data into the generated MoonBit parity test | yes |
| `tools/measure_deviation.py` | measures the numerical margin between the port and the original | yes |
| `tools/gen_tables.py` | generates `moonbit_fft2/tables.mbt` from the transform length tables of the original | yes |
| `tools/gen_java_kernels.py` | translates the small radix butterflies of the original into `moonbit_fft2/kernels.mbt` | yes |
| `tools/solve_constants.py` | solves the constants of the butterflies in double precision | yes |
| `tools/verify_goodthomas.py` | checks the model of the prime factor algorithm of the original against `numpy.fft` | yes |
| `tools/count_ops.py` | counts the multiplications, the additions and the accesses of both sides | yes |
| `tools/count_live_values.py` | counts the values that are alive at the same time in one butterfly | yes |
| `tools/stage_classes.py` | lays the original bytecode out under its package path, so that the oracle can be compiled | yes |
| `tools/decompile.py` | decompiles the bytecode of the original into readable Java, out of the jar of `tools/lib` | yes |
| `tools/compare_bench.py` | joins the results of the two benchmarks into one table | yes |
| `tools/merge_bench.py` | merges several runs of a benchmark, keeping the fastest result per case | yes |
| `tools/bench_baseline.py` | measures the port as it was before the kernel was rewritten, from a revision of the git history | yes |
| `tools/check_benchmark.py` | checks that the tables of `BENCHMARK.md` agree with the benchmark results | yes |
| `tools/publish_bench.py` | copies the measurements of the rounds into the tracked `bench` directory | yes |
| `tools/negative_control.py` | breaks the kernel of the transform on purpose and checks that the test suite turns red | yes |
| `tools/lib/` | the jars the oracle needs: `imglib2-6.1.0.jar`, `mines-jtk-20151125.jar` and the decompiler `cfr-0.152.jar` | yes |
| `javap_*.txt` | the disassembly of the original classes and of the JTransforms kernels | yes |
| `BENCHMARK.md` | the runtime comparison of the port against the original Java implementation | yes |
| `bench/` | the measurements of the rounds, one file per round, so that the tables of `BENCHMARK.md` can be checked | yes |
| `tools/_tmp/` | the upstream sources of `imglib2-fft`, fetched for reference | no, local only |
| `build/` | generated artefacts: the compiled oracle, the test cases, the golden data, the decompiled sources | no, local only |

The tracked `moonbit_fft2/parity_wbtest.mbt` carries every expectation of the
parity tests inline, so `moon test` works on a fresh clone without the
generated data of `build/`.  The golden data itself is reproduced by the
pipeline below.

The jars of `tools/lib/` that are **not** tracked are the JTransforms
artifacts and an older `edu.mines:mines-jtk`: the JTransforms jars were only
fetched during the investigation of the kernel.  The three jars that the
verification needs are tracked: `imglib2-6.1.0.jar` holds the library that the
original bytecode of `fft2/` depends on, `mines-jtk-20151125.jar` holds the
JTransforms kernel that the original calls, and `cfr-0.152.jar` is the
decompiler that turns that kernel back into readable Java.

## How the port was built

The upstream project publishes compiled classes only, so the semantics of
`FFT`, `FFTMethods` and of the `edu.mines.jtk.dsp` kernels were recovered
from the bytecode:

* `javap -p -c -constants -s` on the original classes produced the
  disassembly in `javap_*.txt`;
* the decompiler CFR (in `tools/lib`) turned the same classes back into
  readable Java (`build/fft2src`, `build/jtsrc`), which was used to
  confirm the reading of the disassembly; `python tools\decompile.py` rebuilds
  the sources of `build/jtsrc` from the jar of the original, so that the
  translation of the butterflies can be repeated on a fresh clone;
* the upstream sources of `imglib2-fft` (`tools/_tmp/upstream_*.java`)
  were fetched for comparison - note that they are *not* identical to the
  shipped bytecode, the bytecode is the reference.

The port was then validated against the original: the oracle runs the
original classes over deterministic inputs and writes the raw `float32`
results, and the generated test `moonbit_fft2/parity_wbtest.mbt` replays
them against the MoonBit implementation.  The suite currently holds 629
parity cases, 28 hand written unit tests and 6 tests of the transform
kernel, 663 in total; all of them pass.

Two details of the original are worth pointing out, because both are easy to
get wrong and neither is visible in the upstream sources:

* the real valued transforms do **not** use the same length table as the
  complex valued ones.  A real transform of length `n` is built on a half
  length complex transform, so `FftReal.nfftFast(n)` is twice the length of
  the complex transform of `(n + 1) / 2`.  The two tables disagree for most
  lengths, so the choice of the transform length changes the shape of the
  result;
* the padded variant of `FFT.complexToReal` reads its input through a view
  that is not extended.  Whenever the extent of the result differs from the
  extent of the input, that view reaches outside the image and the original
  fails with an `IndexOutOfBoundsException`.

The parity suite therefore sweeps **every length of the first dimension from
1 to 64** and checks the four length tables of the original exactly, for
every length from 1 to 128.  The oracle records the failures of the
original as well, so that the port has to fail in the same places.

## Reproducing the verification

```powershell
# deterministic inputs
python tools\gen_cases.py --out build\cases

# the original bytecode has to be laid out under its package path first
python tools\stage_classes.py

# golden data from the original Java classes
$lib = "tools\lib"
javac -nowarn -encoding UTF-8 `
  -cp "build\classes;$lib\imglib2-6.1.0.jar;$lib\mines-jtk-20151125.jar" `
  -d build\oracle tools\java\Oracle.java
java -cp "build\oracle;build\classes;$lib\imglib2-6.1.0.jar;$lib\mines-jtk-20151125.jar" `
  Oracle build\cases\manifest.txt build\cases\java

# generated parity test
python tools\gen_parity.py --cases build\cases --out moonbit_fft2\parity_wbtest.mbt

# build and test the port
cd moonbit_fft2
moon fmt
moon check --deny-warn
moon test
moon info          # refresh the published interface file
```

Requires a JDK 11 (the original classes are Java 8), Python with NumPy
and the MoonBit toolchain (`moon` 0.1.20261012 or newer).

The butterflies of the port are generated, not written by hand: they are the
factorisations of the original, translated out of the decompiled `Pfacc.java`.
The decompiled sources are rebuilt from the jar of the original with

```powershell
python tools\decompile.py
```

and the kernels with

```powershell
python tools\gen_java_kernels.py --out moonbit_fft2\kernels.mbt
moon -C moonbit_fft2 fmt
```

Both scripts are needed by the tools that read the original, and they tell
what to run when the decompiled sources are missing.

## Runtime comparison

[`BENCHMARK.md`](BENCHMARK.md) compares the runtime of the port with the
runtime of the original, using the same measurement protocol on both sides.
The short version: the port used to be five orders of magnitude slower for
every length that matters, because the original transforms `O(n log n)` with
a mixed radix PFA kernel while the port transformed `O(n^2)` for every length
that is not a power of two - and the length table of the original caps the
power of two at `2^4`.

The port now uses the **prime factor algorithm of the original**: the length
is split into pairwise coprime factors, every factor selects a small kernel,
and the stages carry no twiddle factor at all.  The `n = 32 760` complex to
complex transform went from **<!--v:OLD_C2C_S-->4.2<!--/v--> s to <!--v:C2C_MS-->0.9<!--/v--> ms**
(<!--v:C2C_SPEEDUP-->4890<!--/v-->x), and the port is now between <!--v:RANGE-->1.0 to 4<!--/v--> times slower than
the JVM at the lengths where it is slower at all.

Two details of the measurement matter as much as the numbers.  The benchmark
runs the **release** build, because `moon run` produces the debug build by
default and that one is about thirty times slower - the debug build would
make the port look 169x slower than the original instead of 3.6x.  And the
noise of a busy machine is bimodal, so a "keep the fastest run" statistic
measures the luck of the schedule rather than the program; `BENCHMARK.md`
describes the protocol that replaces it - the median of the rounds, the
ratios taken per round, and the order of the sides rotated in every round.

The small transforms of the odd radices use the symmetry of the roots of
unity, which is a quarter of the multiplications and a quarter of the
additions, and which is worth
**<!--v:KERNEL_RANGE-->1.83x to 2.77x for the long transforms, and 0.97x to 1.22x for the short ones<!--/v-->**
- the arithmetic of the butterflies *is* a large part of the run time of the
long transforms.  The prime factor rewrite of the kernel, which removed the
twiddle factors between the stages and the permutation of the output, was
worth another **<!--v:GT_RANGE-->1.03x to 1.40x<!--/v-->**, and the rewrite of the butterflies
by the **factorisations of the original** was worth
**<!--v:ORIG_RANGE-->1.00x to 1.20x<!--/v-->**.  The port now does the same number of
multiplications, of additions and of array accesses per element as the
original, so what is left of the gap is the price of the runtime: a single
array element access costs about 0.67 ns in MoonBit, against about 0.15 ns on
the JVM.

## License

Apache-2.0, like the original project.

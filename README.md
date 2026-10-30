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
| `tools/java/Oracle.java` | harness that drives the original bytecode and dumps its results as golden data | yes |
| `tools/gen_cases.py` | generates the deterministic test inputs and the manifest | yes |
| `tools/gen_parity.py` | turns the golden data into the generated MoonBit parity test | yes |
| `tools/measure_deviation.py` | measures the numerical margin between the port and the original | yes |
| `tools/gen_tables.py` | generates `moonbit_fft2/tables.mbt` from the transform length tables of the original | yes |
| `tools/lib/` | the jars the oracle needs: `imglib2-6.1.0.jar`, `mines-jtk-20151125.jar` and the decompiler `cfr-0.152.jar` | yes |
| `javap_*.txt` | the disassembly of the original classes and of the JTransforms kernels | yes |
| `tools/_tmp/` | the upstream sources of `imglib2-fft`, fetched for reference | no, local only |
| `build/` | generated artefacts: the compiled oracle, the test cases, the golden data, the decompiled sources | no, local only |

The tracked `moonbit_fft2/parity_wbtest.mbt` carries every expectation of the
parity tests inline, so `moon test` works on a fresh clone without the
generated data of `build/`.  The golden data itself is reproduced by the
pipeline below.

The jars of `tools/lib/` that are not tracked are the JTransforms artifacts
and an older `edu.mines:mines-jtk`: the original depends on
`edu.mines:mines-jtk`, and the JTransforms jars were only fetched during the
investigation of the kernel.

## How the port was built

The upstream project publishes compiled classes only, so the semantics of
`FFT`, `FFTMethods` and of the `edu.mines.jtk.dsp` kernels were recovered
from the bytecode:

* `javap -p -c -constants -s` on the original classes produced the
  disassembly in `javap_*.txt`;
* the decompiler CFR (in `tools/lib`) turned the same classes back into
  readable Java (`build/fft2src`, `build/jtsrc`), which was used to
  confirm the reading of the disassembly;
* the upstream sources of `imglib2-fft` (`tools/_tmp/upstream_*.java`)
  were fetched for comparison - note that they are *not* identical to the
  shipped bytecode, the bytecode is the reference.

The port was then validated against the original: the oracle runs the
original classes over deterministic inputs and writes the raw `float32`
results, and the generated test `moonbit_fft2/parity_wbtest.mbt` replays
them against the MoonBit implementation.  The suite currently holds 629
parity cases and 28 unit tests, 657 in total; all of them pass.

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

## License

Apache-2.0, like the original project.

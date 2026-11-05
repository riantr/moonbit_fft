# `v128probe` — the SIMD fast paths of the native backend

A probe of one question: **can MoonBit source reach the SIMD units of the
x86-64 machine the port runs on, and how wide does it get?** The answer, as
measured with `moon 0.1.20261102 (ea07287 2026-11-02)` on an
`i7-12700` (Alder Lake, AVX2 + FMA3, AVX-512 fused off), is *yes, but only
128 bit wide, and only behind an undocumented build knob* — and, on the
butterfly of this port, *slower than the scalar code* (1.2516x the time of the
scalar side, bit for bit identical results). This directory keeps the probe,
the paired measurement and the evidence in the repository so that the finding
can be reproduced instead of retold.

## What the probe measures

`cmd/main/main.mbt` evaluates the complex product that the transform needs
(see `stage_r4_mu3` of `kernels.mbt`), in the "structure of arrays" layout
that fits the transform's `re` / `im` buffers: the real parts of two complex
numbers travel in one vector, their imaginary parts in another one. A complex
product is then

```
re' = ar * br - ai * bi
im' = ar * bi + ai * br
```

which is four multiplies and two additions on vectors, that is **two complex
products per six instructions** instead of the twelve scalar instructions of
the same work. The probe checks that the two lanes reproduce the scalar
product bit for bit, and prints `PASS`.

## The knob

The MoonBit native backend lowers the `v128` primitives to the `Moonbit_simd_*`
calls of `$MOON_HOME/include/moonbit_simd.h`, and that header picks between
the hardware macros and the scalar fallback on `MOONBIT_V128_SSE2`, which
`moonbit.h` defines only when `__SSE2__` is defined. **MSVC does not define
`__SSE2__`**, so the default build of every native target takes the scalar
fallback — that is the origin of the "v128 is 75x slower than scalar" figure
measured earlier in this project, and not a property of the intrinsics.

The gate is opened by passing the define through the package — together with
`/O2`, because `cc-flags` replaces the defaults instead of adding to them, see
the trap below:

```
options(
  is_main: true,
  link: { "native": { "cc-flags": "/O2 /utf-8 /wd4819 /D__SSE2__" } },
)
```

`moon build` itself offers no way to pass a C flag; its command line carries
`/O2 /MT` and no `/arch:` at all. The `link.native.cc-flags` field is the only
injection point. Note that `moon.pkg.json` is no longer accepted by this
toolchain — `moon fmt` migrates it to the `moon.pkg` syntax above.

## Verifying that the fast path is the one that was emitted

```
moon -C tools/v128probe build --target native --release
tools/v128probe/_build/native/release/build/cmd/main/main.exe
dumpbin /disasm tools/v128probe/_build/native/release/build/cmd/main/main.exe > d.txt
findstr /C:"addpd" /C:"mulpd" /C:"subpd" d.txt
```

With the define the disassembly holds `mulpd` (4), `addpd` (1) and `subpd`
(1) — exactly the six instructions of the two complex products. Without it
those counts are zero and the program runs the scalar fallback.

## The boundaries, as measured

1. **The width is 128 bit.** `moonbit_simd.h` has no `_mm256` and no AVX
   branch at all (0 occurrences), only NEON and SSE2. Adding `/arch:AVX2`
   would change the encoding of the same `_mm_*` intrinsics, not the width:
   two doubles per instruction is the ceiling from MoonBit source today.
2. **A body-less primitive panics.** `fn f(a : V128, b : V128) -> V128 =
   "%v128.f64x2_add"` is emitted as `moonbit_panic()` by the C backend (four
   consecutive calls in the generated `main.c`), and the program dies with
   `PanicError` at the first use. Only the `@v128` functions of
   `moonbitlang/core/v128`, which carry a scalar body next to the
   `#intrinsic` attribute, are usable.
3. **The LLVM backend is not available.** `moon build --target llvm` answers
   `LLVM backend is experimental and only supported on nightly moonbit
   toolchain` and fails with `toolchain is incomplete: missing prelude.mi for
   target llvm`. That backend is the only one that could map `V128` onto
   vector IR instead of the C runtime.
4. **There is no free autovectorisation to fall back on.** `cl /Qvec-report:2`
   on the generated C reports `C5002: loop not vectorized (reason 506)` for a
   plain `c[i] = a[i] * b[i] + a[i]` loop, so the scalar code of the port is
   not silently widened either.
5. **The define only reaches the package C.** Of the 27 `cl` compilations of a
   release build, only the 2 of the package carry `/D__SSE2__`; the 25 files
   of `$MOON_HOME/lib/runtime` do not. That is not an ABI hazard here, because
   `moonbit_v128_t` appears in `moonbit.h` only in its three `typedef`
   alternatives and the runtime API takes `moonbit_v128_storage_t` (two
   `uint64_t`) explicitly — but it does mean the fast paths are a property of
   the package translation unit alone.

## The trap that invalidated the first three numbers: `cc-flags` replaces the defaults

Setting `link.native.cc-flags` does not *add* flags, it **replaces the flag set
of the toolchain**, and the default set carries `-O2` (`/O2`).  Compare the two
command lines of the same release build:

```
with cc-flags   : cl ... /c /std:c11 /bigobj /nologo ... avx.c /arch:AVX2 /MT
without         : cl ... /c /std:c11 /bigobj /utf-8 /wd4819 /nologo /O2 ... bl.c /MT
```

The first one has no `/O2` at all, so every package that set a flag was
compiled **unoptimised**, which this kernel pays for with a factor of nine:
33.7 us per pass without a flag against 308.9 us with `/arch:AVX2` alone, stable
across runs, with the unoptimised `stage` spilling every local to the stack
(`sub rsp,408h`).  The measurements of this directory that came before this
discovery were therefore taken in unoptimised binaries, and the ratio they
report is not the ratio of optimised code.

The flag string that keeps the default: `/O2 /utf-8 /wd4819` plus whatever is
being tested.  Everything below is measured that way.

## The measurement, corrected: the vector butterfly is 1.68x slower

`cmd/ab2/main.mbt` keeps the complex numbers next to each other, one complex
number per vector, lane 0 the real part and lane 1 the imaginary part, so a
point is read and written with one `v128_load` / `v128_store`, which the SSE2
branch of `moonbit_simd.h` turns into `_mm_loadu_si128` / `_mm_storeu_si128` —
one instruction per access, no lane interface, no bounds check.  The rotation
by 90 degrees is one `pshufb` once the package defines `__SSSE3__`, which MSVC
never defines and the CPU has.

```
PARITY : the two sides agree on all 32760 complex numbers
PASS   : scalar 37.1 us, 53 passes per segment
MEDIAN : vector/scalar = 1.6809  (before the /O2 fix, 1.1200)
```

Bit for bit identical, and the vector side needs two thirds more time.  The
same experiment without `/O2` had reported 1.12x: leaving the compiler out
flatters the vector form, because the scalar code loses more to it.

The earlier two-lane form over the `re` / `im` arrays (`cmd/ab`) reported
1.2516x in the unoptimised build and has not been re-measured; the layout above
is the one that removes the packing, so it is the one that bounds the
question.

## `/arch:AVX2` is worth 5.4 per cent, and it is free

`cmd/avx/main.mbt` is the scalar kernel of `kernels.mbt` and nothing else, in
the round format of `tools/ab_compare.py`.  The same source, built once with
the default flags and once with `/O2 /utf-8 /wd4819 /arch:AVX2`, paired over 16
rounds:

```
a median 35078 ns  min 33133  max 45588      (default flags)
b median 33460 ns  min 30907  max 40310      (/arch:AVX2)
per round ratio a/b: median 1.0541   n=256
```

5.4 per cent from the three operand encoding of VEX, with no source change at
all.  The kernel is identical, so nothing else can explain the difference.  Two
conditions come with it: the `/O2` above has to be written out explicitly, and
the flag only reaches code that the C compiler compiles — a package with no
`cc-flags` is emitted as a direct object by `moonc` and never sees the flag.

## What was tried and did not help

* **Branchless index advance**: the recurrence is `if p < limit { p += mr };
  p += delta`, four times per group, data dependent.  Written as
  `p + (mr & ((p - limit) >> 31)) + delta` the indices are identical (checked
  bit for bit) and the kernel is 1.0551x *slower*, so the branch predictor is
  not the problem.
* **Specialisation of the call**: `stage(8190, 3, ...)` with literals against
  the same numbers read out of an array at run time, in one binary: ratio
  1.0105, that is no difference.
* **More lanes**: `f32x4` would double the lanes and halve the arithmetic, but
  the arithmetic is not what the loop is spending its cycles on (see below),
  and it would abandon the double precision accumulation that `kernel.mbt`
  documents.

## `/arch:AVX2` on the port: 7.6 per cent end to end

The flag was then applied to the two programs that measure the port and
measured again, `moonbit_fft/benchab` against itself through
`tools/ab_compare.py`, 336 paired rounds of the complex to complex transform
at `n = 32760`:

```
a (default flags)  median 378033 ns  min 357131  max 521001
b (/arch:AVX2)     median 353734 ns  min 332372  max 465071
per round ratio a/b: median 1.0755   n=336
```

7.6 per cent, more than the 5.4 per cent of the isolated stage, and the
checksum of the same binary is unchanged — `-7829.640045009777` with and
without the flag — so nothing about the results moved.

**Where the flag has to go.** On the executable package, not on the library:

* the kernels are compiled into the merged translation unit of the *program*
  (`benchab.c` is 3.6 MB and holds the constants of the butterflies;
  `moonbit_fft.c` is 22 KB and holds none), and a library package's
  `link.native.cc-flags` does not reach that unit;
* setting them on the library is not merely useless, it breaks the build:
  `failed to make executable riantr/moonbit_fft (native) ... LNK1561: entry
  point must be defined`, because the link section makes the toolchain treat
  the package as a program.

So the gain is available to whoever compiles a *program* that calls the port;
a user of the library who sets nothing still gets the default encoding, and
the numbers of `BENCHMARK.md`, which were measured that way, keep describing
the default build.

## Why vectorising this kernel does not pay

At `/O2` the scalar pass takes 37.1 us for 8190 groups, 4.5 ns per group,
roughly 14 cycles, against about 34 machine operations per group — the loop is
already close to the two to three operations per cycle this core retires, so
there is no idle execution unit left for the vector form to absorb, and the
two-lane form adds the packing (or, in the layout above, the `pshufb` and the
`v128_xor` of the rotation) on top.  That is why the ratio is above one and not
below it.

The lever is therefore not vector width, and it is not memory locality either:
the earlier claim of a latency bound came from the unoptimised numbers and does
not survive them.



For comparison, the hand written **C** SSE2 kernel of this same port measured
1.10–1.16x *faster* than its scalar reference when it was tried earlier. Same
algorithm, same ISA, opposite verdict: the difference is the interface. In C
the loads fold into `movsd` + `unpcklpd`, in MoonBit every lane goes through
the splat/insert/extract of the `v128` API.

## Why this probe does not change the port

The stage kernels of `kernels.mbt` are not arithmetic bound: `stage_r4_mu3`
does 16 floating point operations against 16 memory operations per group of
four points, and its indices are computed by a modular recurrence that has no
gather instruction to serve. A two-lane rewrite therefore has to add the
packing of two scalar loads into one vector, and the measurement above shows
that this packing costs more than the arithmetic it saves. The probe exists so
that the next attempt starts from the mechanism instead of from the folklore.

The escape hatches that remain, and why they are not free:

* **Wider against the same interface** buys nothing: `moonbit_simd.h` has no
  256 bit path, so `/arch:AVX2` would only re-encode the same 128 bit
  operations.
* **A C stub with AVX2 intrinsics** would fold the loads properly and could
  reach the 1.1x of the earlier experiment or a little more, but `extern "C"`
  is unsupported in the wasm backend, so the wasm, wasm-gc and js targets of
  this port would break — for a stage kernel that is a quarter of the
  transform's time.
* **`f32x4`** would double the lane count, but the port deliberately
  accumulates in double precision (`kernel.mbt` documents it), so it would
  trade the accuracy that the parity tests were built around for the lanes.


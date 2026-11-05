# `v128probe` — the SIMD fast paths of the native backend

A probe of one question: **can MoonBit source reach the SIMD units of the
x86-64 machine the port runs on, and how wide does it get?** The answer, as
measured with `moon 0.1.20261102 (ea07287 2026-11-02)` on an
`i7-12700` (Alder Lake, AVX2 + FMA3, AVX-512 fused off), is *yes, but only
128 bit wide, and only behind an undocumented build knob.* This directory
keeps the probe and the evidence in the repository so that the finding can be
reproduced instead of retold.

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

The gate is opened by passing the define through the package:

```
options(
  is_main: true,
  link: { "native": { "cc-flags": "/D__SSE2__" } },
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

## Why this probe does not change the port

The stage kernels of `kernels.mbt` are not arithmetic bound: `stage_r4_mu3`
does 16 floating point operations against 16 memory operations per group of
four points, and its indices are computed by a modular recurrence that has no
gather instruction to serve. A two-lane rewrite therefore has to add the
packing of two scalar loads into one vector, which is where the 1.10–1.16x
measured earlier for a hand written C SSE2 kernel of this port comes from.
The probe exists so that the next attempt starts from the mechanism instead of
from the folklore.

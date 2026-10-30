#!/usr/bin/env python3
"""Generate deterministic test cases for the moonbit_fft2 port.

Each case is described by a small manifest file that both the Java oracle
(the original net.imglib2.algorithm.fft2 classes) and the MoonBit port read,
so both sides consume byte-identical input data.

Layout produced under --out:
    manifest.txt
    <case>/in.bin      raw little-endian float32 values
"""

import argparse
import os
import struct

# ---------------------------------------------------------------------------
# Case catalogue.  `kind` selects the operation, the remaining keys give the
# parameters that both implementations understand.
# ---------------------------------------------------------------------------

CASES = [
    # --- FFTMethods.realToComplex (real input along `dim`) ---------------
    dict(name="r2c_1d_8", kind="R2C", dims=[8], dim=0, scale=False),
    dict(name="r2c_1d_8_scaled", kind="R2C", dims=[8], dim=0, scale=True),
    dict(name="r2c_1d_16", kind="R2C", dims=[16], dim=0, scale=False),
    dict(name="r2c_1d_12", kind="R2C", dims=[12], dim=0, scale=False),
    dict(name="r2c_1d_10", kind="R2C", dims=[10], dim=0, scale=False),
    dict(name="r2c_1d_14", kind="R2C", dims=[14], dim=0, scale=False),
    dict(name="r2c_1d_26", kind="R2C", dims=[26], dim=0, scale=False),
    dict(name="r2c_2d_8x4", kind="R2C", dims=[8, 4], dim=0, scale=False),
    dict(name="r2c_2d_8x4_dim1", kind="R2C", dims=[8, 4], dim=1, scale=False),
    dict(name="r2c_2d_16x8", kind="R2C", dims=[16, 8], dim=0, scale=False),
    dict(name="r2c_2d_4x4_dim1", kind="R2C", dims=[4, 4], dim=1, scale=False),
    dict(name="r2c_3d_4x4x4", kind="R2C", dims=[4, 4, 4], dim=0, scale=False),

    # --- FFTMethods.complexToComplex ------------------------------------
    dict(name="c2c_1d_8_fwd", kind="C2C", dims=[8], dim=0, forward=True, scale=False),
    dict(name="c2c_1d_8_inv", kind="C2C", dims=[8], dim=0, forward=False, scale=True),
    dict(name="c2c_1d_12_fwd", kind="C2C", dims=[12], dim=0, forward=True, scale=False),
    dict(name="c2c_1d_11_fwd", kind="C2C", dims=[11], dim=0, forward=True, scale=False),
    dict(name="c2c_1d_11_inv", kind="C2C", dims=[11], dim=0, forward=False, scale=True),
    dict(name="c2c_1d_13_fwd", kind="C2C", dims=[13], dim=0, forward=True, scale=False),
    dict(name="c2c_2d_8x4_dim1", kind="C2C", dims=[8, 4], dim=1, forward=True, scale=False),
    dict(name="c2c_2d_8x4_dim0_inv", kind="C2C", dims=[8, 4], dim=0, forward=False, scale=True),
    dict(name="c2c_3d_4x4x4_dim1", kind="C2C", dims=[4, 4, 4], dim=1, forward=True, scale=False),

    # --- FFTMethods.complexToReal ---------------------------------------
    dict(name="c2r_1d_5", kind="C2R", dims=[5], dim=0, scale=True),
    dict(name="c2r_1d_7", kind="C2R", dims=[7], dim=0, scale=True),
    dict(name="c2r_1d_11", kind="C2R", dims=[11], dim=0, scale=True),
    dict(name="c2r_2d_5x4", kind="C2R", dims=[5, 4], dim=0, scale=True),
    dict(name="c2r_3d_5x4x4", kind="C2R", dims=[5, 4, 4], dim=0, scale=True),

    # --- high level FFT --------------------------------------------------
    dict(name="fft_r2c_2d_8x4", kind="FFT_R2C", dims=[8, 4]),
    dict(name="fft_r2c_2d_12x6", kind="FFT_R2C", dims=[12, 6]),
    dict(name="fft_r2c_3d_4x4x4", kind="FFT_R2C", dims=[4, 4, 4]),
    # the sizes that a wrong choice of the transform length gets wrong: the
    # length 32 has its own real length table, the length 5 is odd and is
    # padded to 6
    dict(name="fft_r2c_2d_32x4", kind="FFT_R2C", dims=[32, 4]),
    dict(name="fft_r2c_2d_5x4", kind="FFT_R2C", dims=[5, 4]),
    dict(name="fft_r2c_3d_5x4x4", kind="FFT_R2C", dims=[5, 4, 4]),
    # the original extends the input with an out of bounds strategy before it
    # pads it, here the strategy is a constant
    dict(name="fft_r2c_oob_2d_5x4", kind="FFT_R2C_OOB_CONST", dims=[5, 4], fill=0.5),
    dict(name="fft_r2c_oob_2d_9x4", kind="FFT_R2C_OOB_CONST", dims=[9, 4], fill=-0.25),
    dict(name="fft_c2c_fwd_2d_5x4", kind="FFT_C2C_FWD", dims=[5, 4]),
    dict(name="fft_c2c_inv_2d_5x4", kind="FFT_C2C_INV", dims=[5, 4]),
    dict(name="fft_c2c_fwd_3d_4x4x4", kind="FFT_C2C_FWD", dims=[4, 4, 4]),
    dict(name="fft_c2c_inv_3d_4x4x4", kind="FFT_C2C_INV", dims=[4, 4, 4]),
    dict(name="fft_c2r_2d_5x4", kind="FFT_C2R", dims=[5, 4]),
    dict(name="fft_c2r_3d_5x4x4", kind="FFT_C2R", dims=[5, 4, 4]),
    dict(name="fft_c2r_factory_2d_5x4", kind="FFT_C2R_FACTORY", dims=[5, 4]),
    dict(name="fft_c2r_factory_3d_5x4x4", kind="FFT_C2R_FACTORY", dims=[5, 4, 4]),

    # --- FFT.complexToRealUnpad ------------------------------------------
    dict(name="fft_c2r_unpad_1d_5_to_4", kind="FFT_C2R_UNPAD", dims=[5], target=[4]),
    dict(name="fft_c2r_unpad_2d_9x8_to_8x4", kind="FFT_C2R_UNPAD", dims=[9, 8], target=[8, 4]),
    dict(name="fft_c2r_unpad_3d_9x8x4_to_8x4x2", kind="FFT_C2R_UNPAD", dims=[9, 8, 4], target=[8, 4, 2]),

    # --- interval / dimension helpers -----------------------------------
    dict(name="pad_8x4", kind="PAD", dims=[8, 4], target=[16, 8]),
    dict(name="pad_9x5", kind="PAD", dims=[9, 5], target=[16, 8]),
    dict(name="pad_3d_4x4x4", kind="PAD", dims=[4, 4, 4], target=[8, 8, 8]),
    dict(name="unpad_16x8", kind="UNPAD", dims=[16, 8], target=[8, 4]),
    dict(name="unpad_3d_16x8x8", kind="UNPAD", dims=[16, 8, 8], target=[8, 4, 4]),
    dict(name="dims_r2c", kind="DIMS_R2C", dims=[8, 4]),
    dict(name="dims_r2c_12", kind="DIMS_R2C", dims=[12, 6]),
    dict(name="dims_c2r", kind="DIMS_C2R", dims=[5, 4]),
    dict(name="dims_c2c", kind="DIMS_C2C", dims=[8, 4]),
]

# ---------------------------------------------------------------------------
# Sweeps.
#
# The real valued transforms of the original implementation do *not* use the
# same length table as the complex valued ones: a real transform of length n
# is built on a half length complex transform of (n + 1) / 2.  A handful of
# hand picked sizes therefore cannot tell the two tables apart, so every size
# of the first dimension is covered.
# ---------------------------------------------------------------------------

# every length of the first dimension
SWEEP = list(range(1, 65))

# complex sizes start at 2, a complex size of 1 would ask for an empty real
# result
SWEEP_COMPLEX = list(range(2, 65))

CASES += [
    # --- the length tables of the original implementation ------------------
    dict(name="sizes", kind="SIZES", dims=[1], target=[128]),
]

# the dimension helpers decide the shape of the result, they are checked
# exactly for every length of the first dimension
CASES += [
    dict(name="dims_r2c_sweep_%d" % n, kind="DIMS_R2C", dims=[n]) for n in SWEEP
]
CASES += [
    dict(name="dims_c2r_sweep_%d" % n, kind="DIMS_C2R", dims=[n]) for n in SWEEP
]

# the "small" variants of the dimension helpers, they pick the smallest
# supported length instead of the cheapest one
CASES += [
    dict(name="dims_r2c_small_sweep_%d" % n, kind="DIMS_R2C_SMALL", dims=[n])
    for n in SWEEP
]
CASES += [
    dict(name="dims_c2r_small_sweep_%d" % n, kind="DIMS_C2R_SMALL", dims=[n])
    for n in SWEEP
]
CASES += [
    dict(name="dims_c2c_small_sweep_%d" % n, kind="DIMS_C2C_SMALL", dims=[n])
    for n in SWEEP
]

# the real valued transforms of the original implementation, for every length
# of the first dimension
CASES += [
    dict(name="r2c_sweep_%d" % n, kind="R2C", dims=[n], dim=0, scale=False)
    for n in SWEEP
]
CASES += [
    dict(name="c2r_sweep_%d" % n, kind="C2R", dims=[n], dim=0, scale=True)
    for n in SWEEP_COMPLEX
]

# the high level transforms, for every length of the first dimension
CASES += [
    dict(name="fft_r2c_sweep_%d" % n, kind="FFT_R2C", dims=[n, 1]) for n in SWEEP
]
CASES += [
    dict(name="fft_c2r_factory_sweep_%d" % n, kind="FFT_C2R_FACTORY", dims=[n, 1])
    for n in SWEEP_COMPLEX
]

# Kinds whose input is complex valued (2 floats per element).
COMPLEX_KINDS = {
    "C2C",
    "C2R",
    "FFT_C2C_FWD",
    "FFT_C2C_INV",
    "FFT_C2R",
    "FFT_C2R_UNPAD",
    "FFT_C2R_FACTORY",
}


def prod(xs):
    n = 1
    for x in xs:
        n *= x
    return n


def make_values(count, seed):
    """Deterministic, well-conditioned float32 samples in [-1, 1)."""
    vals = []
    state = seed & 0xFFFFFFFF
    for _ in range(count):
        state = (state * 1664525 + 1013904223) & 0xFFFFFFFF
        vals.append((state / 2147483648.0) - 1.0)
    return vals


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)

    manifest = []
    for idx, case in enumerate(CASES):
        name = case["name"]
        cdir = os.path.join(out, name)
        os.makedirs(cdir, exist_ok=True)

        n = prod(case["dims"])
        nvals = 2 * n if case["kind"] in COMPLEX_KINDS else n
        vals = make_values(nvals, seed=0x9E3779B9 ^ (idx * 2654435761))

        in_path = os.path.join(cdir, "in.bin")
        with open(in_path, "wb") as fh:
            fh.write(struct.pack("<%df" % nvals, *vals))

        manifest.append(
            "CASE {name}\n"
            "KIND {kind}\n"
            "DIMS {d}\n"
            "IN {path}\n"
            "DIM {dim}\n"
            "SCALE {scale}\n"
            "FORWARD {forward}\n"
            "TARGET {target}\n"
            "FILL {fill}\n".format(
                name=name,
                kind=case["kind"],
                d=" ".join(str(x) for x in case["dims"]),
                path=in_path.replace("\\", "/"),
                dim=case.get("dim", 0),
                scale=1 if case.get("scale", False) else 0,
                forward=1 if case.get("forward", True) else 0,
                target=" ".join(str(x) for x in case.get("target", [])),
                fill=repr(float(case.get("fill", 0.0))),
            )
        )

    with open(os.path.join(out, "manifest.txt"), "w", encoding="utf-8") as fh:
        fh.write("".join(manifest))

    print("wrote %d cases to %s" % (len(CASES), out))


if __name__ == "__main__":
    main()

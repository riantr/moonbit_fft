// A probe of the `v128` fast paths of the MoonBit native backend.
//
// The point it measures is the complex product written in the structure of
// arrays of the transform: the real parts of two complex numbers in one
// vector, the imaginary parts in another one (a "structure of arrays"
// layout).  A complex product is then four multiplies and two additions on
// vectors, that is two complex products per six instructions instead of the
// twelve scalar instructions of the same work.
//
// Build and check that the hardware path is the one that was emitted:
//
//   moon build --target native --release
//   dumpbin /disasm _build/native/release/build/cmd/main/main.exe > d.txt
//   findstr /C:"addpd" d.txt
//
// `addpd` and `mulpd` in the disassembly are the packed instructions of
// `moonbit_simd.h`; without them the six calls of the vectors fell back to
// the scalar implementations and the probe measures the fallback.

///|
/// The complex product in scalar code, the reference value.
fn cmul(ar : Double, ai : Double, br : Double, bi : Double) -> (Double, Double) {
  (ar * br - ai * bi, ar * bi + ai * br)
}

///|
/// A vector of two lanes with the given lane 0 and lane 1.
fn pair(lo : Double, hi : Double) -> V128 {
  @v128.f64x2_replace_lane(@v128.f64x2_splat(lo), hi, 1)
}

///|
/// The complex products of two numbers at once, the real parts of the
/// results in one vector and their imaginary parts in another one.
fn cmul_pair(
  ar : V128,
  ai : V128,
  br : V128,
  bi : V128,
) -> (V128, V128) {
  let re = @v128.f64x2_sub(
    @v128.f64x2_mul(ar, br),
    @v128.f64x2_mul(ai, bi),
  )
  let im = @v128.f64x2_add(
    @v128.f64x2_mul(ar, bi),
    @v128.f64x2_mul(ai, br),
  )
  (re, im)
}

///|
fn main {
  // Two complex products, the same work as two scalar calls of `cmul`.
  let (r0, i0) = cmul(1.0, 2.0, 0.5, 0.75)
  let (r1, i1) = cmul(3.0, 4.0, -0.25, 0.125)
  let ar = pair(1.0, 3.0)
  let ai = pair(2.0, 4.0)
  let br = pair(0.5, -0.25)
  let bi = pair(0.75, 0.125)
  let (re, im) = cmul_pair(ar, ai, br, bi)
  let vr0 = @v128.f64x2_extract_lane(re, 0)
  let vr1 = @v128.f64x2_extract_lane(re, 1)
  let vi0 = @v128.f64x2_extract_lane(im, 0)
  let vi1 = @v128.f64x2_extract_lane(im, 1)
  println("scalar : (\{r0}, \{i0}) (\{r1}, \{i1})")
  println("v128   : (\{vr0}, \{vi0}) (\{vr1}, \{vi1})")
  // The vector product must reproduce the scalar one bit for bit: the four
  // multiplies and the two additions are the same ones, only the lanes are
  // run in parallel.
  if vr0 == r0 && vi0 == i0 && vr1 == r1 && vi1 == i1 {
    println("PASS   : the two lanes equal the scalar product bit for bit")
  } else {
    println("FAIL   : the lanes differ from the scalar product")
    abort("the v128 lanes differ from the scalar product")
  }
}

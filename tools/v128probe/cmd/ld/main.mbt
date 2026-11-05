// The cost of the pieces a "structure of arrays of complex numbers" kernel
// would need, measured by looking at the instructions the backend emits:
//
//   * `v128_load` / `v128_store` on a `FixedArray[Byte]` at a byte offset —
//     the only vector load the language offers, and the reason a kernel could
//     read a complex number with one instruction instead of packing two
//     doubles;
//   * `i8x16_shuffle` with constant indices — the lane swap that a rotation
//     by 90 degrees needs, and the piece SSE2 cannot do with `pshufb`.
//
//   moon -C tools/v128probe build --target native --release
//   dumpbin /disasm _build/native/release/build/cmd/ld/ld.exe

///|
fn main {
  let buf : FixedArray[Byte] = FixedArray::make(64, b'\x00')
  // A complex number in the two lanes.
  let v = @v128.f64x2_replace_lane(@v128.f64x2_splat(1.5), 2.5, 1)
  @v128.v128_store(buf, 0, v)
  let w = @v128.v128_load(buf, 0)
  println("store/load lane0 = \{@v128.f64x2_extract_lane(w, 0)}")
  println("store/load lane1 = \{@v128.f64x2_extract_lane(w, 1)}")
  // The rotation by 90 degrees: swap the two 64 bit halves.
  let s = @v128.i8x16_shuffle(
    w, w, 8, 9, 10, 11, 12, 13, 14, 15, 0, 1, 2, 3, 4, 5, 6, 7,
  )
  println("swapped lane0    = \{@v128.f64x2_extract_lane(s, 0)}")
  println("swapped lane1    = \{@v128.f64x2_extract_lane(s, 1)}")
  @v128.v128_store(buf, 16, s)
  let t = @v128.v128_load(buf, 16)
  println("again lane0      = \{@v128.f64x2_extract_lane(t, 0)}")
  println("again lane1      = \{@v128.f64x2_extract_lane(t, 1)}")
}

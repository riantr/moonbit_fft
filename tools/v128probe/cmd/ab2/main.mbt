// The second paired measurement: the same butterfly as `cmd/ab`, but with the
// complex numbers stored next to each other, one complex number per vector
// (lane 0 the real part, lane 1 the imaginary part), so that a point is read
// and written with one `v128_load` / `v128_store` instead of two scalar loads
// packed by the lane interface.
//
// The rotation by 90 degrees — the one operation a radix 4 butterfly cannot
// avoid — costs one `i8x16_shuffle` plus one `v128_xor` per output.  The
// shuffle has a hardware path only under `__SSSE3__` in `moonbit_simd.h`,
// which MSVC never defines, so the package defines it: the CPU has SSSE3.
//
// The baseline is the scalar kernel of `moonbit_fft/kernels.mbt` on its own
// layout (`re` and `im` arrays), which is what the port runs today.
//
//   moon -C tools/v128probe build --target native --release
//   tools/v128probe/_build/native/release/build/cmd/ab2/ab2.exe

#external
type Timestamp

extern "C" fn monotonic_clock_start() -> Timestamp = "moonbit_monotonic_clock_start"

extern "C" fn monotonic_clock_end(ts : Timestamp) -> Double = "moonbit_monotonic_clock_stop"

///|
fn advance(p : Int, limit : Int, mr : Int, delta : Int) -> Int {
  let mut q = p
  if q < limit {
    q = q + mr
  }
  q + delta
}

///|
/// The scalar butterfly of `stage_r4_mu3`, verbatim.
fn stage_scalar(
  m : Int,
  kfac : Int,
  re : Array[Double],
  im : Array[Double],
) -> Unit {
  let mr = m * 4
  let delta = 1 - m * kfac
  let mut limit = m * kfac
  let mut p0 = m * (0 * kfac % 4)
  let mut p1 = m * (1 * kfac % 4)
  let mut p2 = m * (2 * kfac % 4)
  let mut p3 = m * (3 * kfac % 4)
  let c1 = -0.9999999999999998
  let mut i = 0
  while i < m {
    let t1r = re[p0] + re[p2]
    let t1i = im[p0] + im[p2]
    let t2r = re[p1] + re[p3]
    let t2i = im[p1] + im[p3]
    let y1r = re[p0] - re[p2]
    let y1i = im[p0] - im[p2]
    let y3r = c1 * (re[p1] - re[p3])
    let y3i = c1 * (im[p1] - im[p3])
    re[p0] = t1r + t2r
    im[p0] = t1i + t2i
    re[p1] = y1r - y3i
    im[p1] = y1i + y3r
    re[p2] = t1r - t2r
    im[p2] = t1i - t2i
    re[p3] = y1r + y3i
    im[p3] = y1i - y3r
    if p0 < limit {
      p0 = p0 + mr
    }
    p0 = p0 + delta
    if p1 < limit {
      p1 = p1 + mr
    }
    p1 = p1 + delta
    if p2 < limit {
      p2 = p2 + mr
    }
    p2 = p2 + delta
    if p3 < limit {
      p3 = p3 + mr
    }
    p3 = p3 + delta
    limit = limit + 1
    i = i + 1
  }
}

///|
fn pair(lo : Double, hi : Double) -> V128 {
  @v128.f64x2_replace_lane(@v128.f64x2_splat(lo), hi, 1)
}

///|
/// The rotation by 90 degrees in the complex plane: lane 0 and lane 1 swap.
fn swap(v : V128) -> V128 {
  @v128.i8x16_shuffle(
    v, v, 8, 9, 10, 11, 12, 13, 14, 15, 0, 1, 2, 3, 4, 5, 6, 7,
  )
}

///|
/// The same butterfly, one complex number per vector.
fn stage_aos(buf : FixedArray[Byte], m : Int, kfac : Int) -> Unit {
  // The offsets are carried already multiplied by 16, so that an access is an
  // add and not a multiply: the first version scaled the index at every one
  // of the eight accesses of the group, and that alone was the difference
  // against the scalar kernel.
  let mr = m * 64
  let delta = (1 - m * kfac) * 16
  let mut limit = m * kfac * 16
  let mut p0 = m * (0 * kfac % 4) * 16
  let mut p1 = m * (1 * kfac % 4) * 16
  let mut p2 = m * (2 * kfac % 4) * 16
  let mut p3 = m * (3 * kfac % 4) * 16
  let c1 = pair(-0.9999999999999998, -0.9999999999999998)
  let neg0 = pair(-0.0, 0.0)
  let neg1 = pair(0.0, -0.0)
  let mut i = 0
  while i < m {
    let a = @v128.v128_load(buf, p0)
    let b = @v128.v128_load(buf, p1)
    let c = @v128.v128_load(buf, p2)
    let d = @v128.v128_load(buf, p3)
    let t1 = @v128.f64x2_add(a, c)
    let t2 = @v128.f64x2_add(b, d)
    let y1 = @v128.f64x2_sub(a, c)
    let y3 = @v128.f64x2_mul(c1, @v128.f64x2_sub(b, d))
    let o0 = @v128.f64x2_add(t1, t2)
    let o2 = @v128.f64x2_sub(t1, t2)
    let r = swap(y3)
    let o1 = @v128.f64x2_add(y1, @v128.v128_xor(r, neg0))
    let o3 = @v128.f64x2_add(y1, @v128.v128_xor(r, neg1))
    @v128.v128_store(buf, p0, o0)
    @v128.v128_store(buf, p1, o1)
    @v128.v128_store(buf, p2, o2)
    @v128.v128_store(buf, p3, o3)
    p0 = advance(p0, limit, mr, delta)
    p1 = advance(p1, limit, mr, delta)
    p2 = advance(p2, limit, mr, delta)
    p3 = advance(p3, limit, mr, delta)
    limit = limit + 16
    i = i + 1
  }
}

///|
/// Fills both layouts with the same pseudo random values.
fn fill_both(
  re : Array[Double],
  im : Array[Double],
  buf : FixedArray[Byte],
  n : Int,
) -> Unit {
  let mut s = 12345UL
  let mut j = 0
  while j < n {
    s = s * 6364136223846793005UL + 1442695040888963407UL
    let x = (s >> 11).to_double() * 1.1102230246251565e-16 - 0.5
    s = s * 6364136223846793005UL + 1442695040888963407UL
    let y = (s >> 11).to_double() * 1.1102230246251565e-16 - 0.5
    re[j] = x
    im[j] = y
    @v128.v128_store(buf, j * 16, pair(x, y))
    j = j + 1
  }
}

///|
fn median(values : Array[Double]) -> Double {
  let n = values.length()
  let mut i = 1
  while i < n {
    let v = values[i]
    let mut j = i - 1
    while j >= 0 && values[j] > v {
      values[j + 1] = values[j]
      j = j - 1
    }
    values[j + 1] = v
    i = i + 1
  }
  if n % 2 == 1 {
    values[n / 2]
  } else {
    0.5 * (values[n / 2 - 1] + values[n / 2])
  }
}

///|
fn main {
  let m = 8190
  let kfac = 3
  let n = m * 4
  let re_s = Array::make(n, 0.0)
  let im_s = Array::make(n, 0.0)
  let re_p = Array::make(n, 0.0)
  let im_p = Array::make(n, 0.0)
  let buf : FixedArray[Byte] = FixedArray::make(n * 16, b'\x00')
  // Parity: the vector kernel must reproduce the scalar one bit for bit.
  fill_both(re_s, im_s, buf, n)
  stage_scalar(m, kfac, re_s, im_s)
  stage_aos(buf, m, kfac)
  let mut mismatch = 0
  let mut j = 0
  while j < n {
    let v = @v128.v128_load(buf, j * 16)
    if re_s[j] != @v128.f64x2_extract_lane(v, 0) {
      mismatch = mismatch + 1
    }
    if im_s[j] != @v128.f64x2_extract_lane(v, 1) {
      mismatch = mismatch + 1
    }
    j = j + 1
  }
  if mismatch == 0 {
    println("PARITY : the two sides agree on all \{n} complex numbers")
  } else {
    println("PARITY : \{mismatch} doubles differ")
    abort("the vector butterfly does not reproduce the scalar one")
  }
  let t0 = monotonic_clock_start()
  stage_scalar(m, kfac, re_p, im_p)
  let pass_us = monotonic_clock_end(t0)
  let mut reps = (2000.0 / pass_us).to_int()
  if reps < 1 {
    reps = 1
  }
  println("PASS   : scalar \{pass_us} us, \{reps} passes per segment")
  let rounds = 16
  let ratios = Array::make(rounds, 0.0)
  let mut r = 0
  while r < rounds {
    let vector_first = r % 2 == 1
    let mut us_s = 0.0
    let mut us_v = 0.0
    if vector_first {
      fill_both(re_p, im_p, buf, n)
      let tv = monotonic_clock_start()
      let mut k = 0
      while k < reps {
        stage_aos(buf, m, kfac)
        k = k + 1
      }
      us_v = monotonic_clock_end(tv)
      fill_both(re_p, im_p, buf, n)
      let ts = monotonic_clock_start()
      let mut k2 = 0
      while k2 < reps {
        stage_scalar(m, kfac, re_p, im_p)
        k2 = k2 + 1
      }
      us_s = monotonic_clock_end(ts)
    } else {
      fill_both(re_p, im_p, buf, n)
      let ts = monotonic_clock_start()
      let mut k = 0
      while k < reps {
        stage_scalar(m, kfac, re_p, im_p)
        k = k + 1
      }
      us_s = monotonic_clock_end(ts)
      fill_both(re_p, im_p, buf, n)
      let tv = monotonic_clock_start()
      let mut k2 = 0
      while k2 < reps {
        stage_aos(buf, m, kfac)
        k2 = k2 + 1
      }
      us_v = monotonic_clock_end(tv)
    }
    let ratio = us_v / us_s
    ratios[r] = ratio
    println(
      "ROUND \{r} scalar=\{us_s} us vector=\{us_v} us ratio(vector/scalar)=\{ratio}",
    )
    r = r + 1
  }
  let copies = Array::make(rounds, 0.0)
  let mut c = 0
  while c < rounds {
    copies[c] = ratios[c]
    c = c + 1
  }
  println("MEDIAN : vector/scalar = \{median(copies)} (below 1.0 is the vector side faster)")
}

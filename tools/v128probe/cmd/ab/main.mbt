// A paired measurement of one butterfly: the radix 4 stage of the transform,
// twist 3, in scalar code and with two lanes of `v128`.
//
// The scalar side is `stage_r4_mu3` of `moonbit_fft/kernels.mbt`, copied as it
// is.  The vector side runs the same wavefront with the lanes holding two
// consecutive groups, so every operation of the group is elementwise and the
// constants are the same ones; only the packing of two doubles into a vector
// and the unpacking of the results are new work.
//
// Both sides see the same data, are timed in the same process alternating the
// order every round, and the ratio of every round is kept, because this
// machine slows down by about a factor two after some seconds of load and
// measurements taken at different times are not comparable.
//
//   moon -C tools/v128probe build --target native --release
//   tools/v128probe/_build/native/release/build/cmd/ab/ab.exe

#external
type Timestamp

extern "C" fn monotonic_clock_start() -> Timestamp = "moonbit_monotonic_clock_start"

extern "C" fn monotonic_clock_end(ts : Timestamp) -> Double = "moonbit_monotonic_clock_stop"

///|
/// The next index of the wavefront: the rule of `kernels.mbt`.
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
/// A vector of two lanes: `lo` in lane 0, `hi` in lane 1.
fn pair(lo : Double, hi : Double) -> V128 {
  @v128.f64x2_replace_lane(@v128.f64x2_splat(lo), hi, 1)
}

///|
/// The butterfly above with two groups in the two lanes of the vectors.
fn stage_pair(
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
  let c1 = pair(-0.9999999999999998, -0.9999999999999998)
  let mut i = 0
  // Two groups at a time: the lane 0 holds the group `i`, the lane 1 the
  // group `i + 1`, whose indices are the same rule applied once more.
  while i + 1 < m {
    let q0 = advance(p0, limit, mr, delta)
    let q1 = advance(p1, limit, mr, delta)
    let q2 = advance(p2, limit, mr, delta)
    let q3 = advance(p3, limit, mr, delta)
    let a_r = pair(re[p0], re[q0])
    let a_i = pair(im[p0], im[q0])
    let b_r = pair(re[p1], re[q1])
    let b_i = pair(im[p1], im[q1])
    let c_r = pair(re[p2], re[q2])
    let c_i = pair(im[p2], im[q2])
    let d_r = pair(re[p3], re[q3])
    let d_i = pair(im[p3], im[q3])
    let t1r = @v128.f64x2_add(a_r, c_r)
    let t1i = @v128.f64x2_add(a_i, c_i)
    let t2r = @v128.f64x2_add(b_r, d_r)
    let t2i = @v128.f64x2_add(b_i, d_i)
    let y1r = @v128.f64x2_sub(a_r, c_r)
    let y1i = @v128.f64x2_sub(a_i, c_i)
    let y3r = @v128.f64x2_mul(c1, @v128.f64x2_sub(b_r, d_r))
    let y3i = @v128.f64x2_mul(c1, @v128.f64x2_sub(b_i, d_i))
    let o0r = @v128.f64x2_add(t1r, t2r)
    let o0i = @v128.f64x2_add(t1i, t2i)
    let o1r = @v128.f64x2_sub(y1r, y3i)
    let o1i = @v128.f64x2_add(y1i, y3r)
    let o2r = @v128.f64x2_sub(t1r, t2r)
    let o2i = @v128.f64x2_sub(t1i, t2i)
    let o3r = @v128.f64x2_add(y1r, y3i)
    let o3i = @v128.f64x2_sub(y1i, y3r)
    re[p0] = @v128.f64x2_extract_lane(o0r, 0)
    im[p0] = @v128.f64x2_extract_lane(o0i, 0)
    re[q0] = @v128.f64x2_extract_lane(o0r, 1)
    im[q0] = @v128.f64x2_extract_lane(o0i, 1)
    re[p1] = @v128.f64x2_extract_lane(o1r, 0)
    im[p1] = @v128.f64x2_extract_lane(o1i, 0)
    re[q1] = @v128.f64x2_extract_lane(o1r, 1)
    im[q1] = @v128.f64x2_extract_lane(o1i, 1)
    re[p2] = @v128.f64x2_extract_lane(o2r, 0)
    im[p2] = @v128.f64x2_extract_lane(o2i, 0)
    re[q2] = @v128.f64x2_extract_lane(o2r, 1)
    im[q2] = @v128.f64x2_extract_lane(o2i, 1)
    re[p3] = @v128.f64x2_extract_lane(o3r, 0)
    im[p3] = @v128.f64x2_extract_lane(o3i, 0)
    re[q3] = @v128.f64x2_extract_lane(o3r, 1)
    im[q3] = @v128.f64x2_extract_lane(o3i, 1)
    p0 = advance(q0, limit + 1, mr, delta)
    p1 = advance(q1, limit + 1, mr, delta)
    p2 = advance(q2, limit + 1, mr, delta)
    p3 = advance(q3, limit + 1, mr, delta)
    limit = limit + 2
    i = i + 2
  }
  // The last group of an odd count is the scalar one.
  while i < m {
    let t1r = re[p0] + re[p2]
    let t1i = im[p0] + im[p2]
    let t2r = re[p1] + re[p3]
    let t2i = im[p1] + im[p3]
    let y1r = re[p0] - re[p2]
    let y1i = im[p0] - im[p2]
    let y3r = -0.9999999999999998 * (re[p1] - re[p3])
    let y3i = -0.9999999999999998 * (im[p1] - im[p3])
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
/// Fills the two arrays with the same pseudo random values every time, so
/// that both sides of the measurement see the same data.
fn fill(re : Array[Double], im : Array[Double], n : Int) -> Unit {
  let mut s = 12345UL
  let mut j = 0
  while j < n {
    s = s * 6364136223846793005UL + 1442695040888963407UL
    re[j] = (s >> 11).to_double() * 1.1102230246251565e-16 - 0.5
    s = s * 6364136223846793005UL + 1442695040888963407UL
    im[j] = (s >> 11).to_double() * 1.1102230246251565e-16 - 0.5
    j = j + 1
  }
}

///|
/// The median of the values, by insertion sort: there are only a few of them.
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
  let re_v = Array::make(n, 0.0)
  let im_v = Array::make(n, 0.0)
  // The two implementations must agree bit for bit before anything is timed:
  // a faster wrong kernel is not a faster kernel.
  fill(re_s, im_s, n)
  fill(re_v, im_v, n)
  stage_scalar(m, kfac, re_s, im_s)
  stage_pair(m, kfac, re_v, im_v)
  let mut mismatch = 0
  let mut j = 0
  while j < n {
    if re_s[j] != re_v[j] || im_s[j] != im_v[j] {
      mismatch = mismatch + 1
    }
    j = j + 1
  }
  if mismatch == 0 {
    println("PARITY : the two sides agree on all \{n} doubles")
  } else {
    println("PARITY : \{mismatch} doubles differ")
    abort("the vector butterfly does not reproduce the scalar one")
  }
  // One pass of each, warm, to size the segments at about 2 ms.
  let t0 = monotonic_clock_start()
  stage_scalar(m, kfac, re_s, im_s)
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
      fill(re_v, im_v, n)
      let tv = monotonic_clock_start()
      let mut k = 0
      while k < reps {
        stage_pair(m, kfac, re_v, im_v)
        k = k + 1
      }
      us_v = monotonic_clock_end(tv)
      fill(re_s, im_s, n)
      let ts = monotonic_clock_start()
      let mut k2 = 0
      while k2 < reps {
        stage_scalar(m, kfac, re_s, im_s)
        k2 = k2 + 1
      }
      us_s = monotonic_clock_end(ts)
    } else {
      fill(re_s, im_s, n)
      let ts = monotonic_clock_start()
      let mut k = 0
      while k < reps {
        stage_scalar(m, kfac, re_s, im_s)
        k = k + 1
      }
      us_s = monotonic_clock_end(ts)
      fill(re_v, im_v, n)
      let tv = monotonic_clock_start()
      let mut k2 = 0
      while k2 < reps {
        stage_pair(m, kfac, re_v, im_v)
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

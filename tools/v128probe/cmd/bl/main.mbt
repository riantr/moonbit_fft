// The butterfly of `stage_r4_mu3` twice: with the conditional advance of the
// original, and with the same advance written branchlessly.
//
// The advance is `if p < limit { p += mr }; p += delta`, and it runs four
// times per group of four points.  The condition is data dependent and its
// outcome follows the period of the wavefront, so the branch predictor gets
// it wrong a good part of the time, and a wrong guess costs the pipeline of
// the next groups of loads.  Written as arithmetic the same sequence is
// computed without a branch:
//
//   mask = (p - limit) >> 31   // -1 when p < limit, 0 otherwise
//   p = p + (mr & mask) + delta
//
// The sequence of indices is identical, so the result is bit for bit the
// same, which is checked before anything is timed.
//
//   moon -C tools/v128probe build --target native --release
//   tools/v128probe/_build/native/release/build/cmd/bl/bl.exe

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
/// The same advance without a branch.
fn advance_flat(p : Int, limit : Int, mr : Int, delta : Int) -> Int {
  let mask = (p - limit) >> 31
  p + (mr & mask) + delta
}

///|
fn stage_branchy(
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
fn stage_flat(
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
    p0 = advance_flat(p0, limit, mr, delta)
    p1 = advance_flat(p1, limit, mr, delta)
    p2 = advance_flat(p2, limit, mr, delta)
    p3 = advance_flat(p3, limit, mr, delta)
    limit = limit + 1
    i = i + 1
  }
}

///|
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
  let re_a = Array::make(n, 0.0)
  let im_a = Array::make(n, 0.0)
  let re_b = Array::make(n, 0.0)
  let im_b = Array::make(n, 0.0)
  // The two advances must pick the same indices before anything is timed.
  fill(re_a, im_a, n)
  fill(re_b, im_b, n)
  stage_branchy(m, kfac, re_a, im_a)
  stage_flat(m, kfac, re_b, im_b)
  let mut mismatch = 0
  let mut j = 0
  while j < n {
    if re_a[j] != re_b[j] || im_a[j] != im_b[j] {
      mismatch = mismatch + 1
    }
    j = j + 1
  }
  if mismatch == 0 {
    println("PARITY : the two sides agree on all \{n} doubles")
  } else {
    println("PARITY : \{mismatch} doubles differ")
    abort("the branchless advance does not pick the same indices")
  }
  let t0 = monotonic_clock_start()
  stage_branchy(m, kfac, re_a, im_a)
  let pass_us = monotonic_clock_end(t0)
  let mut reps = (2000.0 / pass_us).to_int()
  if reps < 1 {
    reps = 1
  }
  println("PASS   : branchy \{pass_us} us, \{reps} passes per segment")
  let rounds = 16
  let ratios = Array::make(rounds, 0.0)
  let mut r = 0
  while r < rounds {
    let flat_first = r % 2 == 1
    let mut us_a = 0.0
    let mut us_b = 0.0
    if flat_first {
      fill(re_b, im_b, n)
      let tb = monotonic_clock_start()
      let mut k = 0
      while k < reps {
        stage_flat(m, kfac, re_b, im_b)
        k = k + 1
      }
      us_b = monotonic_clock_end(tb)
      fill(re_a, im_a, n)
      let ta = monotonic_clock_start()
      let mut k2 = 0
      while k2 < reps {
        stage_branchy(m, kfac, re_a, im_a)
        k2 = k2 + 1
      }
      us_a = monotonic_clock_end(ta)
    } else {
      fill(re_a, im_a, n)
      let ta = monotonic_clock_start()
      let mut k = 0
      while k < reps {
        stage_branchy(m, kfac, re_a, im_a)
        k = k + 1
      }
      us_a = monotonic_clock_end(ta)
      fill(re_b, im_b, n)
      let tb = monotonic_clock_start()
      let mut k2 = 0
      while k2 < reps {
        stage_flat(m, kfac, re_b, im_b)
        k2 = k2 + 1
      }
      us_b = monotonic_clock_end(tb)
    }
    let ratio = us_b / us_a
    ratios[r] = ratio
    println(
      "ROUND \{r} branchy=\{us_a} us flat=\{us_b} us ratio(flat/branchy)=\{ratio}",
    )
    r = r + 1
  }
  let copies = Array::make(rounds, 0.0)
  let mut c = 0
  while c < rounds {
    copies[c] = ratios[c]
    c = c + 1
  }
  println("MEDIAN : flat/branchy = \{median(copies)} (below 1.0 is the branchless side faster)")
}

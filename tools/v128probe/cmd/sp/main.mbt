// Is the 7x between the two shapes of the same kernel the *specialisation* of
// the call — `stage(8190, 3, ...)` with literal arguments, which the C
// compiler inlines and folds — or something else?
//
// One implementation, called two ways in one binary: with literals, and with
// the same numbers read out of an array at run time, which the compiler
// cannot fold.  Everything else is identical, so the paired ratio of the two
// is the price of the arguments not being known.
//
//   moon -C tools/v128probe build --target native --release
//   tools/v128probe/_build/native/release/build/cmd/sp/sp.exe

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
fn stage(m : Int, kfac : Int, re : Array[Double], im : Array[Double]) -> Unit {
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
  // The same numbers, read at run time so that nothing can be folded.
  let sizes = Array::make(2, 0)
  sizes[0] = 8190
  sizes[1] = 3
  let mv = sizes[0]
  let kv = sizes[1]
  let n = 8190 * 4
  let re_c = Array::make(n, 0.0)
  let im_c = Array::make(n, 0.0)
  let re_v = Array::make(n, 0.0)
  let im_v = Array::make(n, 0.0)
  let re_c2 = Array::make(n, 0.0)
  let im_c2 = Array::make(n, 0.0)
  let re_v2 = Array::make(n, 0.0)
  let im_v2 = Array::make(n, 0.0)
  // Same results either way.
  fill(re_c, im_c, n)
  fill(re_v, im_v, n)
  stage(8190, 3, re_c, im_c)
  stage(mv, kv, re_v, im_v)
  let mut mismatch = 0
  let mut j = 0
  while j < n {
    if re_c[j] != re_v[j] || im_c[j] != im_v[j] {
      mismatch = mismatch + 1
    }
    j = j + 1
  }
  if mismatch == 0 {
    println("PARITY : the literal and the run time call agree on all \{n} doubles")
  } else {
    println("PARITY : \{mismatch} doubles differ")
    abort("the two calls disagree")
  }
  // Size the segment on the slower side, so that both are measured for long
  // enough.
  let t0 = monotonic_clock_start()
  stage(mv, kv, re_v, im_v)
  let pass_us = monotonic_clock_end(t0)
  let mut reps = (2000.0 / pass_us).to_int()
  if reps < 1 {
    reps = 1
  }
  println("PASS   : run time \{pass_us} us, \{reps} passes per segment")
  let rounds = 16
  let ratios = Array::make(rounds, 0.0)
  let mut r = 0
  while r < rounds {
    let var_first = r % 2 == 1
    let mut us_c = 0.0
    let mut us_v = 0.0
    if var_first {
      fill(re_v2, im_v2, n)
      let tv = monotonic_clock_start()
      let mut k = 0
      while k < reps {
        stage(mv, kv, re_v2, im_v2)
        k = k + 1
      }
      us_v = monotonic_clock_end(tv)
      fill(re_c2, im_c2, n)
      let tc = monotonic_clock_start()
      let mut k2 = 0
      while k2 < reps {
        stage(8190, 3, re_c2, im_c2)
        k2 = k2 + 1
      }
      us_c = monotonic_clock_end(tc)
    } else {
      fill(re_c2, im_c2, n)
      let tc = monotonic_clock_start()
      let mut k = 0
      while k < reps {
        stage(8190, 3, re_c2, im_c2)
        k = k + 1
      }
      us_c = monotonic_clock_end(tc)
      fill(re_v2, im_v2, n)
      let tv = monotonic_clock_start()
      let mut k2 = 0
      while k2 < reps {
        stage(mv, kv, re_v2, im_v2)
        k2 = k2 + 1
      }
      us_v = monotonic_clock_end(tv)
    }
    let ratio = us_c / us_v
    ratios[r] = ratio
    println(
      "ROUND \{r} literal=\{us_c} us runtime=\{us_v} us ratio(literal/runtime)=\{ratio}",
    )
    r = r + 1
  }
  let copies = Array::make(rounds, 0.0)
  let mut c = 0
  while c < rounds {
    copies[c] = ratios[c]
    c = c + 1
  }
  println("MEDIAN : literal/runtime = \{median(copies)} (below 1.0 is the specialised side faster)")
}

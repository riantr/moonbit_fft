// The scalar butterfly of `kernels.mbt`, unchanged, in the round format of
// `tools/ab_compare.py`:
//
//   ROUND <index> <ns per pass> ns
//
// The same source is built twice, once without a flag and once with
// `/arch:AVX2` in `link.native.cc-flags`, and the two executables are paired
// by that script.  The kernel is identical in both, so the difference is only
// what the C compiler does with it: the three operand encoding of VEX
// replaces a number of register copies of the two operand encoding.
//
//   moon -C tools/v128probe build --target native --release cmd/avx
//   python tools/ab_compare.py <baseline.exe> <avx2.exe> 16

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
fn stage(
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
fn main {
  let m = 8190
  let kfac = 3
  let n = m * 4
  let re = Array::make(n, 0.0)
  let im = Array::make(n, 0.0)
  fill(re, im, n)
  // Size the segment at about 2 ms, so that a round is long enough to be
  // stable and short enough that the machine does not start to slow down
  // inside it.
  let t0 = monotonic_clock_start()
  stage(m, kfac, re, im)
  let pass_us = monotonic_clock_end(t0)
  let mut reps = (2000.0 / pass_us).to_int()
  if reps < 1 {
    reps = 1
  }
  println("PASS \{pass_us} us, \{reps} passes per round")
  let rounds = 16
  let mut r = 0
  while r < rounds {
    fill(re, im, n)
    let ts = monotonic_clock_start()
    let mut k = 0
    while k < reps {
      stage(m, kfac, re, im)
      k = k + 1
    }
    let us = monotonic_clock_end(ts)
    // The third field is what `ab_compare.py` reads: nanoseconds per pass.
    println("ROUND \{r} \{us * 1000.0 / reps.to_double()} ns")
    r = r + 1
  }
  // Keep the result alive: the compiler may not drop the loop above.
  if re[0] == 12345.678 {
    println("\{im[1]}")
  }
}

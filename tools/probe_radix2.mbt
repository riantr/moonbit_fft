///|
/// The floor of a transform in MoonBit.
///
/// This is the classic iterative radix-2 decimation in time transform: a bit
/// reversal permutation and then log2(n) butterfly passes.  It does about
/// four array accesses per element per pass, which is the minimum for a
/// butterfly, so it shows what the array access cost of the language costs
/// in the best case.  A specialised mixed radix kernel cannot be much
/// faster than this, so the ratio between the two is the headroom that is
/// left for the kernel of the port.
///
/// The build profile matters: the debug build of the MoonBit compiler is
/// about ten times slower here than the release build.  Run it twice, once
/// per profile, and compare:
///
/// ```
/// moon run --target native tools/probe_radix2.mbt
/// moon run --target native --release tools/probe_radix2.mbt
/// ```
fn main {
  let n = 32768
  let reps = 50
  // warm up
  let mut i = 0
  while i < 5 {
    let a = make_input(n)
    fft(a)
    i = i + 1
  }
  let ts = @bench.monotonic_clock_start()
  i = 0
  while i < reps {
    let a = make_input(n)
    fft(a)
    i = i + 1
  }
  let us = @bench.monotonic_clock_end(ts)
  let per = us * 1000.0 / reps.to_double()
  println("radix-2 n=\{n}: \{per} ns per transform, \{per / n.to_double()} ns per element")
}

///|
fn make_input(n : Int) -> Array[Double] {
  let a = Array::Array(capacity=n)
  let mut i = 0
  while i < n {
    a.push((i % 1000).to_double() / 1000.0 - 0.5)
    i = i + 1
  }
  a
}

///|
/// The classic iterative radix-2 transform, in place.
fn fft(a : Array[Double]) -> Unit {
  let n = a.length()
  // bit reversal permutation
  let mut j = 0
  let mut i = 0
  while i < n {
    if i < j {
      let t = a[i]
      a[i] = a[j]
      a[j] = t
    }
    let mut m = n / 2
    while m >= 1 && j >= m {
      j = j - m
      m = m / 2
    }
    j = j + m
    i = i + 1
  }
  // the twiddle factors, computed once per transform
  let tw = Array::Array(capacity=n)
  let mut t = 0
  while t < n {
    let ang = -6.283185307179586 * t.to_double() / n.to_double()
    tw.push(@math.cos(ang))
    tw.push(@math.sin(ang))
    t = t + 1
  }
  let mut len = 2
  while len <= n {
    let half = len / 2
    let step = n / len
    let mut base = 0
    while base < n {
      let mut k = 0
      while k < half {
        let wr = tw[2 * (k * step)]
        let wi = tw[2 * (k * step) + 1]
        let p = base + k
        let q = base + k + half
        let ur = a[p]
        let ui = a[q]
        let tr = ur * wr - ui * wi
        let ti = ur * wi + ui * wr
        a[p] = tr
        a[q] = ti
        k = k + 1
      }
      base = base + len
    }
    len = len * 2
  }
}

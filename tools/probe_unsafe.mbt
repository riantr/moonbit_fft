///|
/// How much does the bounds check of `Array` access cost?
///
/// `Array::unsafe_get` and `Array::unsafe_set` are the intrinsic accessors
/// of the `builtin` package, they skip the `0 <= idx < length` check.  The
/// kernel of the transform does about 42.8 array accesses per element, so
/// every saved compare-and-branch is worth a lot.
///
/// The probe measures four access patterns on `Array[Double]`:
///   * checked read, sequential
///   * unchecked read, sequential
///   * checked read, strided (the access pattern of a butterfly stage)
///   * unchecked read, strided
///
/// ```
/// moon run --target native --release tools/probe_unsafe.mbt
/// ```
fn main {
  // A small array stays in L1, so the loop is limited by the instruction
  // throughput and not by the memory bandwidth.  A large one is limited by
  // the bandwidth and hides the cost of the bounds check.
  report(4096, 400000)
  report(65536, 40000)
  report(1 << 20, 16)
}

///|
fn report(n : Int, reps : Int) -> Unit {
  println("--- n = \{n} (L1 / L2 / DRAM) ---")
  println("seq   checked   = \{bench_seq(n, reps, false)} ns/elem")
  println("seq   unchecked = \{bench_seq(n, reps, true)} ns/elem")
  println("strid checked   = \{bench_strided(n, reps, false)} ns/elem")
  println("strid unchecked = \{bench_strided(n, reps, true)} ns/elem")
}

///|
fn fill(n : Int) -> Array[Double] {
  let a = Array::Array(capacity=n)
  let mut i = 0
  while i < n {
    a.push(i.to_double() * 0.5)
    i = i + 1
  }
  a
}

///|
fn bench_seq(n : Int, reps : Int, unchecked : Bool) -> Double {
  let a = fill(n)
  let mut acc = 0.0
  let ts = @bench.monotonic_clock_start()
  let mut r = 0
  while r < reps {
    let mut j = 0
    while j < n {
      if unchecked {
        acc = acc + a.unsafe_get(j)
      } else {
        acc = acc + a[j]
      }
      j = j + 1
    }
    r = r + 1
  }
  let us = @bench.monotonic_clock_end(ts)
  if acc == 12345.678 {
    println("\{acc}")
  }
  us * 1000.0 / (n.to_double() * reps.to_double())
}

///|
/// A strided read, the pattern of one butterfly stage: the elements of a
/// group are far apart in memory.
fn bench_strided(n : Int, reps : Int, unchecked : Bool) -> Double {
  let a = fill(n)
  let stride = 8
  let group = n / stride
  let mut acc = 0.0
  let ts = @bench.monotonic_clock_start()
  let mut r = 0
  while r < reps {
    let mut g = 0
    while g < group {
      let mut k = 0
      while k < stride {
        let idx = g + k * group
        if unchecked {
          acc = acc + a.unsafe_get(idx)
        } else {
          acc = acc + a[idx]
        }
        k = k + 1
      }
      g = g + 1
    }
    r = r + 1
  }
  let us = @bench.monotonic_clock_end(ts)
  if acc == 12345.678 {
    println("\{acc}")
  }
  us * 1000.0 / (n.to_double() * reps.to_double())
}

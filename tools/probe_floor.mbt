// The monotonic clock of `moonbitlang/core/bench`, declared here because a
// standalone file cannot import a package of `moonbitlang/core`.  The
// elapsed time is in microseconds.
#external
type Timestamp

extern "C" fn monotonic_clock_start() -> Timestamp = "moonbit_monotonic_clock_start"

extern "C" fn monotonic_clock_end(ts : Timestamp) -> Double = "moonbit_monotonic_clock_stop"

///|
/// The floor of the array access cost of MoonBit.
///
/// It measures the sequential read throughput of `Array[Double]`,
/// `Array[Float]` and `Array[Int]`.  A boxed `Double` array would have to
/// chase a pointer for every element, so its throughput is expected to be
/// clearly below the unboxed ones.
///
/// The build profile matters: the debug build of the MoonBit compiler is
/// about five times slower here than the release build.  Run it twice, once
/// per profile, and compare:
///
/// ```
/// moon run --target native tools/probe_floor.mbt
/// moon run --target native --release tools/probe_floor.mbt
/// ```
fn main {
  let n = 4 * 1024 * 1024
  let reps = 8
  println("double ns/elem = \{bench_doubles(n, reps)}")
  println("float  ns/elem = \{bench_floats(n, reps)}")
  println("int    ns/elem = \{bench_ints(n, reps)}")
}

///|
fn bench_doubles(n : Int, reps : Int) -> Double {
  let a = Array::Array(capacity=n)
  let mut i = 0
  while i < n {
    a.push(i.to_double() * 0.5)
    i = i + 1
  }
  let mut acc = 0.0
  let ts = monotonic_clock_start()
  let mut r = 0
  while r < reps {
    let mut j = 0
    while j < n {
      acc = acc + a[j]
      j = j + 1
    }
    r = r + 1
  }
  let us = monotonic_clock_end(ts)
  // keep the accumulator alive
  if acc == 12345.678 {
    println("\{acc}")
  }
  us * 1000.0 / (n.to_double() * reps.to_double())
}

///|
fn bench_floats(n : Int, reps : Int) -> Double {
  let a = Array::Array(capacity=n)
  let mut i = 0
  while i < n {
    a.push(Float::from_double(i.to_double() * 0.5))
    i = i + 1
  }
  let mut acc = 0.0
  let ts = monotonic_clock_start()
  let mut r = 0
  while r < reps {
    let mut j = 0
    while j < n {
      acc = acc + a[j].to_double()
      j = j + 1
    }
    r = r + 1
  }
  let us = monotonic_clock_end(ts)
  if acc == 12345.678 {
    println("\{acc}")
  }
  us * 1000.0 / (n.to_double() * reps.to_double())
}

///|
fn bench_ints(n : Int, reps : Int) -> Double {
  let a = Array::Array(capacity=n)
  let mut i = 0
  while i < n {
    a.push(i)
    i = i + 1
  }
  let mut acc = 0
  let ts = monotonic_clock_start()
  let mut r = 0
  while r < reps {
    let mut j = 0
    while j < n {
      acc = acc + a[j]
      j = j + 1
    }
    r = r + 1
  }
  let us = monotonic_clock_end(ts)
  if acc == 12345678 {
    println("\{acc}")
  }
  us * 1000.0 / (n.to_double() * reps.to_double())
}

///|
/// Benchmark of the MoonBit port, the counterpart of `tools/java/Bench.java`.
///
/// The measurement protocol is identical on both sides:
///
/// 1. a probe that grows the batch size until the probe itself lasts long
///    enough to be timed accurately; the probe doubles as the warm up,
/// 2. an iteration count derived from the probe so that one measured round
///    takes about one second,
/// 3. the best of three measured rounds.
///
/// The clock of `moonbitlang/core/bench` counts microseconds, the Java
/// original counts nanoseconds, so the results are converted to nanoseconds
/// here.
fn main {
  let mut checksum = 0.0
  checksum = checksum + bench_complex()
  checksum = checksum + bench_real()
  checksum = checksum + bench_api()
  println("CHECKSUM \{checksum}")
}

///|
/// The measured section should take about this long, in microseconds.
let target_us : Double = 1000000.0

///|
/// A probe shorter than this is not accurate enough to derive the iteration
/// count.
let min_measure_us : Double = 100.0

///|
/// The largest batch size used by the probe.
let max_batch : Double = 1000000.0

///|
/// The largest number of iterations of a measured round.
let max_iters : Double = 1000000.0

///|
/// The number of measured rounds, the best one is reported.
let rounds : Int32 = 3

///|
/// Creates an array of `n` deterministic values in `[-0.5, 0.5)`.
fn make_floats(n : Int32) -> Array[Float] {
  let a = Array::Array(capacity=n)
  let mut i = 0
  while i < n {
    let v = i.to_int64() * 2654435761L % 1000L
    a.push(Float::from_double(v.to_double() / 1000.0 - 0.5))
    i = i + 1
  }
  a
}

///|
/// Runs `count` calls of `f` and returns the elapsed time in microseconds.
fn time_batch(f : () -> Unit, count : Double) -> Double {
  let ts = @bench.monotonic_clock_start()
  let mut i = 0.0
  while i < count {
    f()
    i = i + 1.0
  }
  @bench.monotonic_clock_end(ts)
}

///|
/// Measures the cost of one call of `f`, in nanoseconds.
fn measure(f : () -> Unit) -> Double {
  // probe, the batch grows until the probe is long enough to be timed
  // accurately; this is also where the hot code gets compiled
  let mut batch = 1.0
  let mut probe = time_batch(f, batch)
  while probe < min_measure_us && batch < max_batch {
    let grown = batch * 10.0
    batch = if grown > max_batch { max_batch } else { grown }
    probe = time_batch(f, batch)
  }
  // pick an iteration count that fills about one second
  let single = probe / batch
  let mut iters = max_iters
  if single > 0.0 {
    let cand = @math.floor(target_us / single)
    if cand < 1.0 {
      iters = 1.0
    } else if cand > max_iters {
      iters = max_iters
    } else {
      iters = cand
    }
  }
  // warm up
  let mut warmup = 20.0
  if warmup > iters {
    warmup = iters
  }
  let mut i = 0.0
  while i < warmup {
    f()
    i = i + 1.0
  }
  // measure, the best of three rounds
  let mut best = 1.0e300
  let mut r = 0
  while r < rounds {
    let total = time_batch(f, iters)
    let per = total / iters
    if per < best {
      best = per
    }
    r = r + 1
  }
  // microseconds to nanoseconds
  best * 1000.0
}

///|
/// Reports one measurement and returns the sum of the output values, the sum
/// is the checksum that keeps the compiler from dropping the work.
fn report(
  workload : String,
  n : Int32,
  ns_per_op : Double,
  out : Array[Float],
) -> Double {
  let mut sum = 0.0
  let mut i = 0
  while i < out.length() {
    sum = sum + out[i].to_double()
    i = i + 1
  }
  println(
    "CASE moonbit " +
    workload +
    " n=" +
    n.to_string() +
    " ns_per_op=" +
    ns_per_op.to_string(),
  )
  sum
}

///|
/// The complex to complex transform of the kernel.
fn bench_complex() -> Double {
  let lengths = [16, 120, 240, 720, 4095, 5460, 10920, 32760]
  let mut checksum = 0.0
  let mut li = 0
  while li < lengths.length() {
    let n = lengths[li]
    let fft = @moonbit_fft.FftComplex::new(n)
    let cx = make_floats(2 * n)
    let cy = make_floats(2 * n)
    let ns = measure(fn() { fft.complex_to_complex(-1, cx, cy) })
    checksum = checksum + report("c2c", n, ns, cy)
    li = li + 1
  }
  checksum
}

///|
/// The real to complex transform of the kernel.
fn bench_real() -> Double {
  let lengths = [32, 480, 1440, 8190, 21840, 65520]
  let mut checksum = 0.0
  let mut li = 0
  while li < lengths.length() {
    let n = lengths[li]
    let fft = @moonbit_fft.FftReal::new(n)
    let rx = make_floats(n)
    let cy = make_floats(n + 2)
    let ns = measure(fn() { fft.real_to_complex(-1, rx, cy) })
    checksum = checksum + report("r2c", n, ns, cy)
    li = li + 1
  }
  checksum
}

///|
/// The same transform through the image API of the port.
fn bench_api() -> Double {
  let lengths = [16, 120, 240, 720, 5460, 10920, 32760, 65520]
  let mut checksum = 0.0
  let mut li = 0
  while li < lengths.length() {
    let n = lengths[li]
    let input = @moonbit_fft.RealImage::from_data([n], make_floats(n))
    let output = @moonbit_fft.ComplexImage::new([n / 2 + 1])
    let ns = measure(fn() {
      let _ = @moonbit_fft.real_to_complex(input, output, None, 0, false)
    })
    checksum = checksum + report("api", n, ns, output.data)
    li = li + 1
  }
  checksum
}

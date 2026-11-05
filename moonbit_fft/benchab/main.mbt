///|
/// The probe of the runtime of the transform.
///
/// It answers two questions that the benchmark of the port cannot, because
/// the benchmark reports the best of three rounds and keeps its output to
/// itself:
///
/// 1. *How does the time of a call change while the transform is called
///    again and again?*  The rounds are short and every one of them is
///    reported, so that a drift is visible.  The answer matters, because the
///    machine this runs on loses about half of its speed under a sustained
///    load, and it loses it on everything, so a drift in the rounds of a
///    single build says nothing about the build - only rounds that were
///    measured at the same time do.
/// 2. *How does one build of the port compare with another one?*  The two
///    builds are run alternately and their rounds are paired, so that the
///    ratio of the two sides in the same round cancels the part of the noise
///    that both of them see.
///
/// ```
/// moon -C moonbit_fft run --release --target native ./benchab
/// ```
fn main {
  let n = 32_760
  let fft = @moonbit_fft.FftComplex::new(n)
  let cx = make_floats(2 * n)
  let cy = make_floats(2 * n)

  // The warm up: the plan of the length is built in the first call.
  let mut warm = 0
  while warm < 50 {
    fft.complex_to_complex(-1, cx, cy)
    warm = warm + 1
  }

  // The rounds, for the comparison of two builds.
  let mut round = 0
  while round < 30 {
    let ts = @bench.monotonic_clock_start()
    let mut i = 0
    while i < 95 {
      fft.complex_to_complex(-1, cx, cy)
      i = i + 1
    }
    let us = @bench.monotonic_clock_end(ts)
    println("ROUND \{round} \{us * 1000.0 / 95.0} ns")
    round = round + 1
  }

  // The measurements with the protocol of the benchmark of the port: the
  // probe, the warm up and the best of three rounds of about a second.
  let mut measurement = 0
  while measurement < 3 {
    let ns = measure(fn() { fft.complex_to_complex(-1, cx, cy) })
    println("MEASURE \{measurement} c2c n=32760 ns_per_op=\{ns}")
    measurement = measurement + 1
  }

  // The checksum, so that the work cannot be dropped.
  let mut sum = 0.0
  let mut j = 0
  while j < cy.length() {
    sum = sum + cy[j].to_double()
    j = j + 1
  }
  println("CHECKSUM \{sum}")
}

///|
/// The measure of the benchmark of the port, unchanged.
fn measure(f : () -> Unit) -> Double {
  let mut batch = 1.0
  let mut probe = time_batch(f, batch)
  while probe < 100.0 && batch < 1000000.0 {
    let grown = batch * 10.0
    batch = if grown > 1000000.0 { 1000000.0 } else { grown }
    probe = time_batch(f, batch)
  }
  let single = probe / batch
  let mut iters = 1000000.0
  if single > 0.0 {
    let cand = @math.floor(1000000.0 / single)
    if cand < 1.0 {
      iters = 1.0
    } else if cand > 1000000.0 {
      iters = 1000000.0
    } else {
      iters = cand
    }
  }
  let mut warmup = 20.0
  if warmup > iters {
    warmup = iters
  }
  let mut i = 0.0
  while i < warmup {
    f()
    i = i + 1.0
  }
  let mut best = 1.0e300
  let mut r = 0
  while r < 3 {
    let total = time_batch(f, iters)
    let per = total / iters
    if per < best {
      best = per
    }
    r = r + 1
  }
  best * 1000.0
}

///|
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

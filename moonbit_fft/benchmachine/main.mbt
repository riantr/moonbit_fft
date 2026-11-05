///|
/// The runtime of the transform of the port, with the state of the machine
/// next to it.
///
/// The machine this runs on loses about half of its speed under a sustained
/// load, and it loses it on everything: on the transform of the port as much
/// as on a loop of integer multiplications.  A drift in the rounds of the
/// transform therefore says nothing about the transform, unless the two
/// references keep their speed:
///
/// * a loop of integer arithmetic, which shows the clock of the machine,
/// * a sequential pass over a megabyte of doubles, which shows the speed of
///   the memory system.
///
/// When the transform slows down and the two references slow down with it,
/// the machine is the reason.
///
/// ```
/// moon -C moonbit_fft run --release --target native ./benchmachine
/// ```
fn main {
  let n = 32_760
  let fft = @moonbit_fft.FftComplex::new(n)
  let cx = make_floats(2 * n)
  let cy = make_floats(2 * n)
  let mem = Array::make(131_072, 1.0)

  // The warm up: the plan of the length is built in the first call.
  let mut warm = 0
  while warm < 50 {
    fft.complex_to_complex(-1, cx, cy)
    warm = warm + 1
  }

  // The rounds.  Each one lasts long enough to let the machine reach its
  // state, which is what the references are there to show.
  let iters = 2500
  let mut round = 0
  while round < 20 {
    let t0 = @bench.monotonic_clock_start()
    let mut i = 0
    while i < iters {
      fft.complex_to_complex(-1, cx, cy)
      i = i + 1
    }
    let t1 = @bench.monotonic_clock_end(t0)

    // The clock of the machine: a fixed number of dependent multiplications.
    let t2 = @bench.monotonic_clock_start()
    let mut x = 12345
    let mut k = 0
    while k < 20_000_000 {
      x = (x * 1103515245 + 12345) % 2147483647
      k = k + 1
    }
    let t3 = @bench.monotonic_clock_end(t2)

    // The memory system: a sequential pass over a megabyte of doubles.
    let t4 = @bench.monotonic_clock_start()
    let mut acc = 0.0
    let mut m = 0
    while m < mem.length() {
      acc = acc + mem[m]
      m = m + 1
    }
    let t5 = @bench.monotonic_clock_end(t4)

    println(
      "round \{round} transform \{t1 * 1000.0 / iters.to_double()} ns | clock \{t3} us | memory \{t5 * 1000.0 / 131072.0} ns/elem | acc \{acc} x \{x}",
    )
    round = round + 1
  }

  // The checksum, so that none of the work can be dropped.
  let mut sum = 0.0
  let mut j = 0
  while j < cy.length() {
    sum = sum + cy[j].to_double()
    j = j + 1
  }
  println("CHECKSUM \{sum}")
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

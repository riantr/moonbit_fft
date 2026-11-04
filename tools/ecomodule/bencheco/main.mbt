///|
/// The port of the repository against the best implementation of the
/// ecosystem, measured in the same session.
///
/// The ecosystem was searched with `moon search fft` and the packages that
/// really transform were installed and run.  Most of them transform a length
/// that is not a power of two with Bluestein, and they allocate the buffers of
/// that convolution on every call, so their cost at a length of the original
/// is tens of times the cost of the port.  One of them is different:
/// `HK-SHAO/dsp` keeps a **plan** - the bit reversal and the two tables of the
/// cosines and the sines of a window - and transforms in place in the memory
/// of a **slot** that it hands out once.  That is the same structure the port
/// of today has after its own rewrites, and it is the only package of the
/// ecosystem that is in the same class as the port.
///
/// The two of them cannot be given the same length, and that is the point of
/// the whole comparison:
///
/// * the port takes the **lengths of the original**, the table of
///   `edu.mines.jtk.dsp.Pfacc`.  That table has 240 entries, most of them are
///   not powers of two, and **the powers of two stop at 16** - 32, 64, 128,
///   4096 are not valid lengths of the port at all,
/// * `HK-SHAO/dsp` takes the **powers of two from 256 to 4096**, and nothing
///   else.
///
/// So the two of them meet nowhere exactly.  Two pairs are measured, and the
/// length of the port is the entry of its table that is the closest to the
/// window of `HK-SHAO/dsp`:
///
/// | window | the port | difference |
/// | ---: | ---: | ---: |
/// | 4 096 | 4 095 | the port is 0.02 % shorter |
/// | 1 024 | 1 008 | the port is 1.6 % shorter |
///
/// A difference of 1.6 % of the length can not explain a ratio of two, and the
/// cost per `n log n` that the program prints next to the times makes the two
/// lengths comparable at all.
///
/// The candidates are measured in **one process**, and in every round they run
/// one after the other in an order that is rotated from round to round, so
/// that neither the order nor the load of the machine can favour one of them.
/// The rounds are paired and the ratio of the two sides of a round cancels the
/// part of the noise that both of them see.  The references of the machine run
/// once per round, after the candidates: a loop of integer arithmetic, which
/// shows the clock, and a sequential pass over a megabyte of doubles, which
/// shows the memory system.
///
/// ```
/// moon -C build/ecomodule run --release --target native ./bencheco
/// ```
fn main {
  let rounds = 16
  // The window of `HK-SHAO/dsp` and the closest valid length of the port.
  let big = 4_096
  let big_port = 4_095
  let small = 1_024
  let small_port = 1_008

  let fft_big = @moonbit_fft2.FftComplex::new(big_port)
  let fft_small = @moonbit_fft2.FftComplex::new(small_port)
  let cx_big = make_floats(2 * big_port)
  let cy_big = make_floats(2 * big_port)
  let cx_small = make_floats(2 * small_port)
  let cy_small = make_floats(2 * small_port)

  let slot_big = @hkdsp.slot_open(big)
  let slot_small = @hkdsp.slot_open(small)
  let mem_big = @hkdsp.slot_mem_of(slot_big)
  let mem_small = @hkdsp.slot_mem_of(slot_small)

  let ref_mem = Array::make(131_072, 1.0)

  // The warm up: the plan of a length is built by the first transform, and
  // the slot of `HK-SHAO/dsp` is zeroed when it is opened.
  let mut warm = 0
  while warm < 30 {
    let _ = fft_big.complex_to_complex(-1, cx_big, cy_big)
    let _ = fft_small.complex_to_complex(-1, cx_small, cy_small)
    fill_hmem(mem_big, big)
    @hkdsp.forward(slot_big)
    fill_hmem(mem_small, small)
    @hkdsp.forward(slot_small)
    warm = warm + 1
  }

  let names = ["port", "hkdsp", "port", "hkdsp"]
  let lengths = [big, big, small, small]
  let mut sink = 0.0
  let mut round = 0
  while round < rounds {
    let order = rotate(4, round)
    let mut k = 0
    while k < order.length() {
      let which = order[k]
      let ns = measure(
        which, fft_big, fft_small, cx_big, cy_big, cx_small, cy_small, slot_big,
        slot_small, mem_big, mem_small,
      )
      println(
        "round \{round} side \{names[which]} length \{lengths[which]} \{ns} ns",
      )
      k = k + 1
    }
    // The result of the last transform of each side is read here, outside the
    // measured region, so that neither side can be dropped as dead work.
    sink = sink + cy_big[0].to_double() + cy_small[0].to_double()
    let (clock, memory, x, acc) = references(ref_mem)
    println(
      "round \{round} reference clock \{clock} us | memory \{memory} ns/elem | mem0 \{mem_big.unsafe_get(0)} sink \{sink} x \{x} acc \{acc}",
    )
    round = round + 1
  }

  println("CHECKSUM \{sink}")
  println("the port: \{@moonbit_fft2.nfft_valid(big)} accepts \{big}")
  @hkdsp.slot_close(slot_big)
  @hkdsp.slot_close(slot_small)
}

///|
/// The transform of one side, in nanoseconds per transform.
///
/// `HK-SHAO/dsp` transforms **in place**, so its samples are put back before
/// every block of transforms and the refill is kept out of the measured
/// region.  Without that the values would be multiplied by the length at every
/// transform, and after a few dozen of them they would be infinite, which is
/// not the data this comparison is about.  The amount of work of a transform
/// does not depend on the values, so the two sides are still measured on the
/// same work.
fn measure(
  which : Int32,
  fft_big : @moonbit_fft2.FftComplex,
  fft_small : @moonbit_fft2.FftComplex,
  cx_big : Array[Float],
  cy_big : Array[Float],
  cx_small : Array[Float],
  cy_small : Array[Float],
  slot_big : Int32,
  slot_small : Int32,
  mem_big : FixedArray[Double],
  mem_small : FixedArray[Double],
) -> Double {
  if which == 0 {
    time_port(fft_big, cx_big, cy_big, 320)
  } else if which == 1 {
    time_slot(slot_big, mem_big, 4_096, 8, 40)
  } else if which == 2 {
    time_port(fft_small, cx_small, cy_small, 1_200)
  } else {
    time_slot(slot_small, mem_small, 1_024, 6, 200)
  }
}

///|
/// The transform of the port, `repeats` times in a row.
fn time_port(
  fft : @moonbit_fft2.FftComplex,
  cx : Array[Float],
  cy : Array[Float],
  repeats : Int32,
) -> Double {
  let t0 = @bench.monotonic_clock_start()
  let mut i = 0
  while i < repeats {
    let _ = fft.complex_to_complex(-1, cx, cy)
    i = i + 1
  }
  @bench.monotonic_clock_end(t0) * 1000.0 / repeats.to_double()
}

///|
/// The transform of `HK-SHAO/dsp`, in blocks of transforms, with the samples
/// put back between the blocks.
fn time_slot(
  slot : Int32,
  mem : FixedArray[Double],
  n : Int32,
  blocks : Int32,
  per_block : Int32,
) -> Double {
  let mut total = 0.0
  let mut b = 0
  while b < blocks {
    fill_hmem(mem, n)
    let t0 = @bench.monotonic_clock_start()
    let mut i = 0
    while i < per_block {
      @hkdsp.forward(slot)
      i = i + 1
    }
    total = total + @bench.monotonic_clock_end(t0)
    b = b + 1
  }
  total * 1000.0 / (blocks * per_block).to_double()
}

///|
/// The state of the machine: the clock of the integer unit and the speed of
/// the memory system.
///
/// Both results are returned and printed by the caller.  MoonBit removes the
/// computations whose result is never read, and a reference that is measured
/// and then dropped reads **zero**: the loop is gone and the round looks
/// infinitely fast.  The two values are therefore part of the line that is
/// printed, and the driver refuses a measurement whose clock is not positive.
fn references(mem : Array[Double]) -> (Double, Double, Int32, Double) {
  let t1 = @bench.monotonic_clock_start()
  let mut x = 12345
  let mut k = 0
  while k < 20_000_000 {
    x = (x * 1103515245 + 12345) % 2147483647
    k = k + 1
  }
  let t2 = @bench.monotonic_clock_end(t1)
  let t3 = @bench.monotonic_clock_start()
  let mut acc = 0.0
  let mut m = 0
  while m < mem.length() {
    acc = acc + mem[m]
    m = m + 1
  }
  let t4 = @bench.monotonic_clock_end(t3)
  (t2, t4 * 1000.0 / 131_072.0, x, acc)
}

///|
/// The samples in the memory of a slot of `HK-SHAO/dsp`: the real parts come
/// first, then the imaginary ones.
fn fill_hmem(mem : FixedArray[Double], n : Int32) -> Unit {
  let mut i = 0
  while i < n {
    mem.unsafe_set(i, sample(2 * i))
    mem.unsafe_set(n + i, sample(2 * i + 1))
    i = i + 1
  }
}

///|
/// The order of the candidates in one round: rotated, so that none of them
/// always runs in the same slot.
fn rotate(count : Int32, round : Int32) -> Array[Int32] {
  let out = Array::Array(capacity=count)
  let mut i = 0
  while i < count {
    out.push((i + round) % count)
    i = i + 1
  }
  out
}

///|
/// The value of the sample at the index `i`.  The port and `HK-SHAO/dsp` get
/// the same samples, so that the two of them describe the same transform.
fn sample(i : Int32) -> Double {
  let v = i.to_int64() * 2654435761L % 1000L
  v.to_double() / 1000.0 - 0.5
}

///|
fn make_floats(n : Int32) -> Array[Float] {
  let a = Array::Array(capacity=n)
  let mut i = 0
  while i < n {
    a.push(Float::from_double(sample(i)))
    i = i + 1
  }
  a
}

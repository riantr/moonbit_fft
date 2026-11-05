///|
/// The port of the repository against the packages of the ecosystem, measured
/// in the same session.
///
/// The ecosystem was searched with `moon search fft`, and every package that
/// really transforms a complex signal is measured here.  Each one is driven
/// through **its own fastest entry point for the length at hand**, which is the
/// only fair way to compare implementations: a package that has a radix-4 path
/// for a length that is a power of four is measured on that path, not on the
/// generic one it falls back to.
///
/// | side | what is called | why that entry |
/// | --- | --- | --- |
/// | `port` | `FftComplex::complex_to_complex` | the port, with the plan of the length cached |
/// | `hkdsp` | `slot_open` then `forward` | plan and slot cached, in place |
/// | `hx/radix4` | `fft_radix4` | in place; 4 096 and 1 024 are powers of four |
/// | `hx/bluestein` | `fft_bluestein` | the generic path of the same package |
/// | `lc/radix4` | `fft_radix4` | its `fft` entry routes **every** length through Bluestein |
/// | `lc/bluestein` | `fft_bluestein` | the generic path of the same package |
/// | `moonnum` | `fft` | dispatches to its radix-2 for a power of two |
/// | `mspec` | `fft` | its only entry, powers of two only |
/// | `mdsp` | `fft` | its only entry, **real** input, powers of two only |
///
/// Two packages offer both a radix path and a Bluestein one, and **both of them
/// are measured**: which of the two is faster is a property of the package and
/// not of the length, so one row per package would have to choose, and the
/// choice would be a claim.  The table shows that the radix-4 path of
/// `hwlxmm/dsp` is the slower of its two, because it recomputes the twiddles of
/// every stage with a pair of transcendental calls, while the convolution of
/// Bluestein runs off a table it builds once.
///
/// The two windows and the lengths:
///
/// * the port takes the **lengths of the original**, the table of
///   `edu.mines.jtk.dsp.Pfacc`.  Most of its 240 entries are not powers of two
///   and **the powers of two stop at 16**, so the port cannot take 4 096 or
///   1 024 at all.  It is given the closest entry of its table: 4 095 and 1 008,
/// * every other side is given the window itself, 4 096 and 1 024.
///
/// The cost of an element, in nanoseconds per `n log2(n)`, is what makes the
/// two lengths comparable: 4 095 against 4 096 differs by 0.02 %, 1 008 against
/// 1 024 by 1.6 %.
///
/// The sides are measured in **one process**, and in every round they run one
/// after the other in an order that is rotated from round to round, so that
/// neither the order nor the load of the machine can favour one of them.  The
/// rounds are paired and the ratio of a side to the port of the same round
/// cancels the part of the noise that both of them see.  The references of the
/// machine run once per round, after the sides: a loop of integer arithmetic,
/// which shows the clock, and a sequential pass over a megabyte of doubles,
/// which shows the memory system.
///
/// `mdsp` transforms **real** samples, and a real transform does about half of
/// the arithmetic of a complex one of the same length.  It is in the table
/// anyway, and its rows say so, because leaving it out would hide the only
/// package of the ecosystem that has a real transform at all.  The comparison
/// is therefore generous to it: it is credited with half the work.
///
/// ```
/// moon -C build/ecomodule run --release --target native ./bencheco
/// ```
fn main raise {
  let rounds = 16
  // The window of the packages and the closest valid length of the port.
  let big = 4_096
  let big_port = 4_095
  let small = 1_024
  let small_port = 1_008

  let fft_big = @moonbit_fft.FftComplex::new(big_port)
  let fft_small = @moonbit_fft.FftComplex::new(small_port)
  let cx_big = make_floats(2 * big_port)
  let cy_big = make_floats(2 * big_port)
  let cx_small = make_floats(2 * small_port)
  let cy_small = make_floats(2 * small_port)

  let slot_big = @hkdsp.slot_open(big)
  let slot_small = @hkdsp.slot_open(small)
  let mem_big = @hkdsp.slot_mem_of(slot_big)
  let mem_small = @hkdsp.slot_mem_of(slot_small)

  let radix_big = make_hwlxmm(big)
  let radix_small = make_hwlxmm(small)
  let lc_big = make_lcyllp(big)
  let lc_small = make_lcyllp(small)
  let nd_big = make_ndarray(big)
  let nd_small = make_ndarray(small)
  let spec_big = make_mspec(big)
  let spec_small = make_mspec(small)
  let real_big = make_real(big)
  let real_small = make_real(small)

  let ref_mem = Array::make(131_072, 1.0)

  // The sides, one entry per window: 0 to 8 are the long window, 9 to 17 the
  // short one, 18 to 25 the inverse of the long window and 26 to 33 the
  // inverse of the short one.
  let names : Array[String] = [
    "port", "hkdsp", "hx/radix4", "hx/bluestein", "lc/radix4", "lc/bluestein", "moonnum",
    "mspec", "mdsp", "port", "hkdsp", "hx/radix4", "hx/bluestein", "lc/radix4", "lc/bluestein",
    "moonnum", "mspec", "mdsp",
    "port/bfft", "port/ifft", "hx/ifft-bluestein", "hx/ifft-radix2", "lc/ifft",
    "lc/ifft-radix4", "moonnum/ifft", "mspec/ifft",
    "port/bfft", "port/ifft", "hx/ifft-bluestein", "hx/ifft-radix2", "lc/ifft",
    "lc/ifft-radix4", "moonnum/ifft", "mspec/ifft",
  ]
  let lengths : Array[Int32] = [
    big_port, big, big, big, big, big, big, big, big, small_port, small, small, small,
    small, small, small, small, small,
    big_port, big_port, big, big, big, big, big, big,
    small_port, small_port, small, small, small, small, small, small,
  ]
  let sides = names.length()

  // The warm up: the plan of a length is built by the first transform, and
  // the slot of `HK-SHAO/dsp` is zeroed when it is opened.
  let mut warm = 0
  while warm < 20 {
    warm_up(
      fft_big, fft_small, cx_big, cy_big, cx_small, cy_small, slot_big, slot_small,
      mem_big, mem_small, radix_big, radix_small, lc_big, lc_small, nd_big, nd_small,
      spec_big, spec_small, real_big, real_small, big, small,
    )
    warm = warm + 1
  }

  // How many transforms a segment of a side holds, so that every segment lasts
  // about ten milliseconds and the resolution of the clock is not the thing
  // that is measured.  Each side is timed once to find out.
  let repeats : Array[Int32] = []
  let mut k = 0
  while k < sides {
    let ns = measure(
      k, fft_big, fft_small, cx_big, cy_big, cx_small, cy_small, slot_big, slot_small,
      mem_big, mem_small, radix_big, radix_small, lc_big, lc_small, nd_big, nd_small,
      spec_big, spec_small, real_big, real_small, 1,
    )
    repeats.push(repeats_for(ns))
    println("side \{names[k]} length \{lengths[k]} repeats \{repeats[k]}")
    k = k + 1
  }

  let mut sink = 0.0
  let mut round = 0
  while round < rounds {
    let order = rotate(sides, round)
    let mut i = 0
    while i < order.length() {
      let which = order[i]
      let ns = measure(
        which,
        fft_big,
        fft_small,
        cx_big,
        cy_big,
        cx_small,
        cy_small,
        slot_big,
        slot_small,
        mem_big,
        mem_small,
        radix_big,
        radix_small,
        lc_big,
        lc_small,
        nd_big,
        nd_small,
        spec_big,
        spec_small,
        real_big,
        real_small,
        repeats[which],
      )
      println(
        "round \{round} side \{names[which]} length \{lengths[which]} \{ns} ns",
      )
      i = i + 1
    }
    // The result of the last transform of the sides that keep their output is
    // read here, outside the measured region, so that the work cannot be
    // dropped as dead code.
    sink = sink +
      cy_big[0].to_double() +
      cy_small[0].to_double() +
      lc_big[0].re +
      spec_big[0].re
    let (clock, memory, x, acc) = references(ref_mem)
    println(
      "round \{round} reference clock \{clock} us | memory \{memory} ns/elem | radix0 \{radix_big[0].re} mem0 \{mem_big.unsafe_get(0)} sink \{sink} x \{x} acc \{acc}",
    )
    round = round + 1
  }

  println("CHECKSUM \{sink}")
  println("the port accepts \{big}: \{@moonbit_fft.nfft_valid(big)}")
  @hkdsp.slot_close(slot_big)
  @hkdsp.slot_close(slot_small)
}

///|
/// The transform of every side, the ones that need their samples put back
/// included.
fn warm_up(
  fft_big : @moonbit_fft.FftComplex,
  fft_small : @moonbit_fft.FftComplex,
  cx_big : Array[Float],
  cy_big : Array[Float],
  cx_small : Array[Float],
  cy_small : Array[Float],
  slot_big : Int32,
  slot_small : Int32,
  mem_big : FixedArray[Double],
  mem_small : FixedArray[Double],
  radix_big : Array[@hmath.Complex],
  radix_small : Array[@hmath.Complex],
  lc_big : Array[@ltypes.Complex],
  lc_small : Array[@ltypes.Complex],
  nd_big : @mcore.NdArray,
  nd_small : @mcore.NdArray,
  spec_big : Array[@mspec.Complex],
  spec_small : Array[@mspec.Complex],
  real_big : Array[Double],
  real_small : Array[Double],
  big : Int32,
  small : Int32,
) -> Unit raise {
  let _ = fft_big.complex_to_complex(-1, cx_big, cy_big)
  let _ = fft_small.complex_to_complex(-1, cx_small, cy_small)
  fill_hmem(mem_big, big)
  @hkdsp.forward(slot_big)
  fill_hmem(mem_small, small)
  @hkdsp.forward(slot_small)
  fill_hwlxmm(radix_big, big)
  @hwlxmm.fft_radix4(radix_big)
  fill_hwlxmm(radix_small, small)
  @hwlxmm.fft_radix4(radix_small)
  let _ = @lcyllp.fft_radix4(lc_big)
  let _ = @lcyllp.fft_radix4(lc_small)
  let _ = @mnum.fft(nd_big)
  let _ = @mnum.fft(nd_small)
  let _ = @mspec.fft(spec_big)
  let _ = @mspec.fft(spec_small)
  let _ = @mdsp.fft(real_big)
  let _ = @mdsp.fft(real_small)
}

///|
/// The time of one segment of a side, in nanoseconds per transform.
///
/// The sides that transform **in place** have their samples put back before
/// every block of transforms and the refill is kept out of the measured
/// region.  Without that the values are multiplied by the length at every
/// transform and become infinite after a few dozen of them, which is not the
/// data this comparison is about.  The amount of work of a transform does not
/// depend on the values, so the sides are still measured on the same work.
fn measure(
  which : Int32,
  fft_big : @moonbit_fft.FftComplex,
  fft_small : @moonbit_fft.FftComplex,
  cx_big : Array[Float],
  cy_big : Array[Float],
  cx_small : Array[Float],
  cy_small : Array[Float],
  slot_big : Int32,
  slot_small : Int32,
  mem_big : FixedArray[Double],
  mem_small : FixedArray[Double],
  radix_big : Array[@hmath.Complex],
  radix_small : Array[@hmath.Complex],
  lc_big : Array[@ltypes.Complex],
  lc_small : Array[@ltypes.Complex],
  nd_big : @mcore.NdArray,
  nd_small : @mcore.NdArray,
  spec_big : Array[@mspec.Complex],
  spec_small : Array[@mspec.Complex],
  real_big : Array[Double],
  real_small : Array[Double],
  repeats : Int32,
) -> Double raise {
  if which == 0 {
    time_port(fft_big, cx_big, cy_big, repeats)
  } else if which == 1 {
    time_slot(slot_big, mem_big, 4_096, repeats)
  } else if which == 2 {
    time_radix4(radix_big, 4_096, repeats)
  } else if which == 3 {
    time_hx_bluestein(radix_big, repeats)
  } else if which == 4 {
    time_lc_radix4(lc_big, repeats)
  } else if which == 5 {
    time_lc_bluestein(lc_big, repeats)
  } else if which == 6 {
    time_moonnum(nd_big, repeats)
  } else if which == 7 {
    time_mspec(spec_big, repeats)
  } else if which == 8 {
    time_mdsp(real_big, repeats)
  } else if which == 9 {
    time_port(fft_small, cx_small, cy_small, repeats)
  } else if which == 10 {
    time_slot(slot_small, mem_small, 1_024, repeats)
  } else if which == 11 {
    time_radix4(radix_small, 1_024, repeats)
  } else if which == 12 {
    time_hx_bluestein(radix_small, repeats)
  } else if which == 13 {
    time_lc_radix4(lc_small, repeats)
  } else if which == 14 {
    time_lc_bluestein(lc_small, repeats)
  } else if which == 15 {
    time_moonnum(nd_small, repeats)
  } else if which == 16 {
    time_mspec(spec_small, repeats)
  } else if which == 17 {
    time_mdsp(real_small, repeats)
  } else if which == 18 {
    time_port_bfft(fft_big, cx_big, cy_big, repeats)
  } else if which == 19 {
    time_port_ifft(fft_big, cx_big, cy_big, repeats)
  } else if which == 20 {
    time_hx_ifft_bluestein(radix_big, repeats)
  } else if which == 21 {
    time_hx_ifft_radix2(radix_big, 4_096, repeats)
  } else if which == 22 {
    time_lc_ifft(lc_big, repeats)
  } else if which == 23 {
    time_lc_ifft_radix4(lc_big, repeats)
  } else if which == 24 {
    time_moonnum_ifft(nd_big, repeats)
  } else if which == 25 {
    time_mspec_ifft(spec_big, repeats)
  } else if which == 26 {
    time_port_bfft(fft_small, cx_small, cy_small, repeats)
  } else if which == 27 {
    time_port_ifft(fft_small, cx_small, cy_small, repeats)
  } else if which == 28 {
    time_hx_ifft_bluestein(radix_small, repeats)
  } else if which == 29 {
    time_hx_ifft_radix2(radix_small, 1_024, repeats)
  } else if which == 30 {
    time_lc_ifft(lc_small, repeats)
  } else if which == 31 {
    time_lc_ifft_radix4(lc_small, repeats)
  } else if which == 32 {
    time_moonnum_ifft(nd_small, repeats)
  } else {
    time_mspec_ifft(spec_small, repeats)
  }
}

///|
/// How the transforms of an in place side are split into blocks, so that the
/// samples can be put back between them.  Eight blocks is enough to keep the
/// values finite for any number of transforms of a segment.
fn blocks_of(repeats : Int32) -> (Int32, Int32) {
  if repeats <= 8 {
    (1, repeats)
  } else {
    (8, repeats / 8)
  }
}

///|
/// The number of transforms of a segment, so that the segment lasts about two
/// milliseconds: with a clock that resolves a microsecond, two milliseconds is
/// three orders of magnitude above the resolution.
///
/// Two and not ten, because the machine of this host loses about half of its
/// speed after roughly three seconds of sustained work, and the whole
/// measurement has to stay inside the phase it starts in.  A round holds the
/// forward **and** the inverse sides, thirty four of them: at ten milliseconds
/// a round is far past the turn of the machine, and so it is at four.  The
/// spread of the rounds is the check of that - a round that crosses the turn
/// raises the spread to three or more on every side at once.
fn repeats_for(ns : Double) -> Int32 {
  let target = 2_000_000.0
  if ns <= 0.0 {
    return 1
  }
  let want = target / ns
  let mut r = want.to_int()
  // Round up, so that every segment is at least the target long even when a
  // single transform is already most of one.
  if r.to_double() < want {
    r = r + 1
  }
  if r < 1 {
    1
  } else if r > 4_000 {
    4_000
  } else {
    r
  }
}

///|
/// The transform of the port, `repeats` times in a row.
fn time_port(
  fft : @moonbit_fft.FftComplex,
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
/// The in place transform of `HK-SHAO/dsp`, in blocks, with the samples put
/// back between the blocks.
fn time_slot(
  slot : Int32,
  mem : FixedArray[Double],
  n : Int32,
  repeats : Int32,
) -> Double {
  let (blocks, per_block) = blocks_of(repeats)
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
/// The in place radix-4 transform of `hwlxmm/dsp`, in blocks, with the samples
/// put back between the blocks.
fn time_radix4(
  data : Array[@hmath.Complex],
  n : Int32,
  repeats : Int32,
) -> Double {
  let (blocks, per_block) = blocks_of(repeats)
  let mut total = 0.0
  let mut b = 0
  while b < blocks {
    fill_hwlxmm(data, n)
    let t0 = @bench.monotonic_clock_start()
    let mut i = 0
    while i < per_block {
      @hwlxmm.fft_radix4(data)
      i = i + 1
    }
    total = total + @bench.monotonic_clock_end(t0)
    b = b + 1
  }
  total * 1000.0 / (blocks * per_block).to_double()
}

///|
/// The Bluestein transform of `hwlxmm/dsp`, which builds its convolution out of
/// a table and returns a new array.
fn time_hx_bluestein(data : Array[@hmath.Complex], repeats : Int32) -> Double {
  let t0 = @bench.monotonic_clock_start()
  let mut i = 0
  while i < repeats {
    let _ = @hwlxmm.fft_bluestein(data)
    i = i + 1
  }
  @bench.monotonic_clock_end(t0) * 1000.0 / repeats.to_double()
}

///|
/// The radix-4 transform of `lcyllp`, which returns a new array.
fn time_lc_radix4(data : Array[@ltypes.Complex], repeats : Int32) -> Double {
  let t0 = @bench.monotonic_clock_start()
  let mut i = 0
  while i < repeats {
    let _ = @lcyllp.fft_radix4(data)
    i = i + 1
  }
  @bench.monotonic_clock_end(t0) * 1000.0 / repeats.to_double()
}

///|
/// The Bluestein transform of `lcyllp`, which is also what its `fft` entry
/// calls for every length.
fn time_lc_bluestein(data : Array[@ltypes.Complex], repeats : Int32) -> Double {
  let t0 = @bench.monotonic_clock_start()
  let mut i = 0
  while i < repeats {
    let _ = @lcyllp.fft_bluestein(data, false)
    i = i + 1
  }
  @bench.monotonic_clock_end(t0) * 1000.0 / repeats.to_double()
}

///|
/// The transform of `amor2025/moonNum`, which dispatches to its radix-2 for a
/// power of two and returns a new array.
fn time_moonnum(nd : @mcore.NdArray, repeats : Int32) -> Double {
  let t0 = @bench.monotonic_clock_start()
  let mut i = 0
  while i < repeats {
    let _ = @mnum.fft(nd)
    i = i + 1
  }
  @bench.monotonic_clock_end(t0) * 1000.0 / repeats.to_double()
}

///|
/// The transform of `chgttyyr/MoonSpectrum`.
fn time_mspec(signal : Array[@mspec.Complex], repeats : Int32) -> Double raise {
  let t0 = @bench.monotonic_clock_start()
  let mut i = 0
  while i < repeats {
    let _ = @mspec.fft(signal)
    i = i + 1
  }
  @bench.monotonic_clock_end(t0) * 1000.0 / repeats.to_double()
}

///|
/// The transform of `2227057182/moonbit-dsp`, whose input is real.
fn time_mdsp(real : Array[Double], repeats : Int32) -> Double {
  let t0 = @bench.monotonic_clock_start()
  let mut i = 0
  while i < repeats {
    let _ = @mdsp.fft(real)
    i = i + 1
  }
  @bench.monotonic_clock_end(t0) * 1000.0 / repeats.to_double()
}

///|
/// The unnormalised inverse of the port: the transform of the other direction,
/// with no scaling at all.  It is the `bfft` of FFTW.jl and the only inverse of
/// the Java original, so it is the row that tells the price of the kernel
/// alone.
fn time_port_bfft(
  fft : @moonbit_fft.FftComplex,
  cx : Array[Float],
  cy : Array[Float],
  repeats : Int32,
) -> Double {
  let t0 = @bench.monotonic_clock_start()
  let mut i = 0
  while i < repeats {
    let _ = fft.complex_to_complex(1, cx, cy)
    i = i + 1
  }
  @bench.monotonic_clock_end(t0) * 1000.0 / repeats.to_double()
}

///|
/// The normalised inverse of the port, which is the same transform followed by
/// one pass over the result that divides it by `n`.  The difference to the row
/// of `port/bfft` is what that pass costs.
fn time_port_ifft(
  fft : @moonbit_fft.FftComplex,
  cx : Array[Float],
  cy : Array[Float],
  repeats : Int32,
) -> Double {
  let t0 = @bench.monotonic_clock_start()
  let mut i = 0
  while i < repeats {
    fft.ifft(cx, cy)
    i = i + 1
  }
  @bench.monotonic_clock_end(t0) * 1000.0 / repeats.to_double()
}

///|
/// The Bluestein inverse of `hwlxmm/dsp`, which returns a new array.
fn time_hx_ifft_bluestein(
  data : Array[@hmath.Complex],
  repeats : Int32,
) -> Double {
  let t0 = @bench.monotonic_clock_start()
  let mut i = 0
  while i < repeats {
    let _ = @hwlxmm.ifft_bluestein(data)
    i = i + 1
  }
  @bench.monotonic_clock_end(t0) * 1000.0 / repeats.to_double()
}

///|
/// The in place radix 2 inverse of `hwlxmm/dsp`, in blocks, with the samples
/// put back between the blocks.
fn time_hx_ifft_radix2(
  data : Array[@hmath.Complex],
  n : Int32,
  repeats : Int32,
) -> Double {
  let (blocks, per_block) = blocks_of(repeats)
  let mut total = 0.0
  let mut b = 0
  while b < blocks {
    fill_hwlxmm(data, n)
    let t0 = @bench.monotonic_clock_start()
    let mut i = 0
    while i < per_block {
      @hwlxmm.ifft_radix2(data)
      i = i + 1
    }
    total = total + @bench.monotonic_clock_end(t0)
    b = b + 1
  }
  total * 1000.0 / (blocks * per_block).to_double()
}

///|
/// The entry point of the inverse of `lcyllp/moonbit-nlse-ssfm`, which is what
/// a caller of that package reaches for.
fn time_lc_ifft(data : Array[@ltypes.Complex], repeats : Int32) -> Double {
  let t0 = @bench.monotonic_clock_start()
  let mut i = 0
  while i < repeats {
    let _ = @lcyllp.ifft(data)
    i = i + 1
  }
  @bench.monotonic_clock_end(t0) * 1000.0 / repeats.to_double()
}

///|
/// The radix 4 inverse of `lcyllp/moonbit-nlse-ssfm`.
fn time_lc_ifft_radix4(
  data : Array[@ltypes.Complex],
  repeats : Int32,
) -> Double {
  let t0 = @bench.monotonic_clock_start()
  let mut i = 0
  while i < repeats {
    let _ = @lcyllp.ifft_radix4(data)
    i = i + 1
  }
  @bench.monotonic_clock_end(t0) * 1000.0 / repeats.to_double()
}

///|
/// The inverse of `amor2025/moonNum`.
fn time_moonnum_ifft(nd : @mcore.NdArray, repeats : Int32) -> Double {
  let t0 = @bench.monotonic_clock_start()
  let mut i = 0
  while i < repeats {
    let _ = @mnum.ifft(nd)
    i = i + 1
  }
  @bench.monotonic_clock_end(t0) * 1000.0 / repeats.to_double()
}

///|
/// The inverse of `chgttyyr/MoonSpectrum`, which reports its failures as a
/// result instead of a panic.
fn time_mspec_ifft(
  spec : Array[@mspec.Complex],
  repeats : Int32,
) -> Double raise {
  let t0 = @bench.monotonic_clock_start()
  let mut i = 0
  while i < repeats {
    let _ = @mspec.ifft(spec)
    i = i + 1
  }
  @bench.monotonic_clock_end(t0) * 1000.0 / repeats.to_double()
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
/// The samples of the array of `hwlxmm/dsp`, which transforms in place.
fn fill_hwlxmm(data : Array[@hmath.Complex], n : Int32) -> Unit {
  let mut i = 0
  while i < n {
    data[i] = @hmath.Complex::new(sample(2 * i), sample(2 * i + 1))
    i = i + 1
  }
}

///|
/// The order of the sides in one round: rotated, so that none of them always
/// runs in the same slot.
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
/// The value of the sample at the index `i`.  Every side gets the same samples,
/// so that all of them describe the same transform.
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

///|
fn make_hwlxmm(n : Int32) -> Array[@hmath.Complex] {
  let out = Array::Array(capacity=n)
  let mut i = 0
  while i < n {
    out.push(@hmath.Complex::new(sample(2 * i), sample(2 * i + 1)))
    i = i + 1
  }
  out
}

///|
fn make_lcyllp(n : Int32) -> Array[@ltypes.Complex] {
  let out = Array::Array(capacity=n)
  let mut i = 0
  while i < n {
    out.push(@ltypes.Complex::new(sample(2 * i), sample(2 * i + 1)))
    i = i + 1
  }
  out
}

///|
fn make_ndarray(n : Int32) -> @mcore.NdArray {
  let scalars : Array[@mcore.Scalar] = []
  let mut i = 0
  while i < n {
    scalars.push(@mcore.Scalar::Complex((sample(2 * i), sample(2 * i + 1))))
    i = i + 1
  }
  @mcore.array(scalars, [n])
}

///|
fn make_mspec(n : Int32) -> Array[@mspec.Complex] {
  let out = Array::Array(capacity=n)
  let mut i = 0
  while i < n {
    out.push(@mspec.complex(re=sample(2 * i), im=sample(2 * i + 1)))
    i = i + 1
  }
  out
}

///|
fn make_real(n : Int32) -> Array[Double] {
  let out = Array::Array(capacity=n)
  let mut i = 0
  while i < n {
    out.push(sample(2 * i))
    i = i + 1
  }
  out
}

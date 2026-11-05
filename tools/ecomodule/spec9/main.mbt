///|
/// The spectrum of every side of the ecosystem benchmark, at the two lengths of
/// the benchmark, so that a double precision reference can hold them to the
/// right answer.
///
/// A timing table is only worth its rows if the faster side computes the same
/// transform as the slower one.  Every side is therefore dumped once, at the
/// length it is measured at in the benchmark, and held to `numpy.fft` by
/// `tools/check_ecospectra.py`.
///
/// The spectra are written to the directory of the first argument:
///
/// ```
/// moon -C build/ecomodule run --release --target native ./spec9 -- build/ecomodule/spec9out
/// ```
fn main raise {
  let args = @env.args()
  let out_dir = if args.length() > 1 {
    args[1]
  } else {
    "build/ecomodule/spec9out"
  }
  if !@fs.path_exists(out_dir) {
    @fs.create_dir(out_dir)
  }
  let big = 4_096
  let big_port = 4_095
  let small = 1_024
  let small_port = 1_008
  dump_port(big_port, out_dir)
  dump_port(small_port, out_dir)
  dump_hkdsp(big, out_dir)
  dump_hkdsp(small, out_dir)
  dump_hx_radix4(big, out_dir)
  dump_hx_radix4(small, out_dir)
  dump_hx_bluestein(big, out_dir)
  dump_hx_bluestein(small, out_dir)
  dump_lc_radix4(big, out_dir)
  dump_lc_radix4(small, out_dir)
  dump_lc_bluestein(big, out_dir)
  dump_lc_bluestein(small, out_dir)
  dump_moonnum(big, out_dir)
  dump_moonnum(small, out_dir)
  dump_mspec(big, out_dir)
  dump_mspec(small, out_dir)
  dump_mdsp(big, out_dir)
  dump_mdsp(small, out_dir)
}

///|
fn write(
  lines : Array[String],
  out_dir : String,
  name : String,
  n : Int32,
) -> Unit raise {
  let mut out = ""
  let mut i = 0
  while i < lines.length() {
    out = out + lines[i] + "\n"
    i = i + 1
  }
  @fs.write_string_to_file(
    out_dir + "\\" + name + "_" + n.to_string() + ".txt",
    out,
  )
  println("dumped \{name} at \{n}")
}

///|
fn dump_port(n : Int32, out_dir : String) -> Unit raise {
  if !@moonbit_fft.nfft_valid(n) {
    println("the port refuses \{n}")
    return
  }
  let cx = make_floats(2 * n)
  let cy = make_floats(2 * n)
  let fft = @moonbit_fft.FftComplex::new(n)
  fft.complex_to_complex(-1, cx, cy)
  let lines : Array[String] = []
  let mut i = 0
  while i < n {
    lines.push(cy[2 * i].to_string() + " " + cy[2 * i + 1].to_string())
    i = i + 1
  }
  write(lines, out_dir, "port", n)
}

///|
fn dump_hkdsp(n : Int32, out_dir : String) -> Unit raise {
  let slot = @hkdsp.slot_open(n)
  if slot < 0 {
    println("hkdsp refuses \{n}")
    return
  }
  let mem = @hkdsp.slot_mem_of(slot)
  fill_hmem(mem, n)
  @hkdsp.forward(slot)
  let lines : Array[String] = []
  let mut i = 0
  while i < n {
    lines.push(
      mem.unsafe_get(i).to_string() + " " + mem.unsafe_get(n + i).to_string(),
    )
    i = i + 1
  }
  write(lines, out_dir, "hkdsp", n)
  @hkdsp.slot_close(slot)
}

///|
fn dump_hx_radix4(n : Int32, out_dir : String) -> Unit raise {
  let data = make_hwlxmm(n)
  @hwlxmm.fft_radix4(data)
  let lines : Array[String] = []
  let mut i = 0
  while i < n {
    lines.push(data[i].re.to_string() + " " + data[i].im.to_string())
    i = i + 1
  }
  write(lines, out_dir, "hx_radix4", n)
}

///|
fn dump_hx_bluestein(n : Int32, out_dir : String) -> Unit raise {
  let data = make_hwlxmm(n)
  let spec = @hwlxmm.fft_bluestein(data)
  let lines : Array[String] = []
  let mut i = 0
  while i < n {
    lines.push(spec[i].re.to_string() + " " + spec[i].im.to_string())
    i = i + 1
  }
  write(lines, out_dir, "hx_bluestein", n)
}

///|
fn dump_lc_radix4(n : Int32, out_dir : String) -> Unit raise {
  let data = make_lcyllp(n)
  let spec = @lcyllp.fft_radix4(data)
  let lines : Array[String] = []
  let mut i = 0
  while i < n {
    lines.push(spec[i].re.to_string() + " " + spec[i].im.to_string())
    i = i + 1
  }
  write(lines, out_dir, "lc_radix4", n)
}

///|
fn dump_lc_bluestein(n : Int32, out_dir : String) -> Unit raise {
  let data = make_lcyllp(n)
  let spec = @lcyllp.fft_bluestein(data, false)
  let lines : Array[String] = []
  let mut i = 0
  while i < n {
    lines.push(spec[i].re.to_string() + " " + spec[i].im.to_string())
    i = i + 1
  }
  write(lines, out_dir, "lc_bluestein", n)
}

///|
fn dump_moonnum(n : Int32, out_dir : String) -> Unit raise {
  let nd = make_ndarray(n)
  let spec = @mnum.fft(nd)
  let lines : Array[String] = []
  let mut i = 0
  while i < n {
    let v = spec.get_c128(i)
    lines.push(v.0.to_string() + " " + v.1.to_string())
    i = i + 1
  }
  write(lines, out_dir, "moonnum", n)
}

///|
fn dump_mspec(n : Int32, out_dir : String) -> Unit raise {
  let signal = make_mspec(n)
  let spec = @mspec.fft(signal)
  let lines : Array[String] = []
  let mut i = 0
  while i < n {
    lines.push(spec[i].re.to_string() + " " + spec[i].im.to_string())
    i = i + 1
  }
  write(lines, out_dir, "mspec", n)
}

///|
/// The real input transform.  Its reference is the transform of the real
/// samples, which is what its own input is.
fn dump_mdsp(n : Int32, out_dir : String) -> Unit raise {
  let real = make_real(n)
  let spec = @mdsp.fft(real)
  let lines : Array[String] = []
  let mut i = 0
  while i < n {
    lines.push(spec[i].re.to_string() + " " + spec[i].im.to_string())
    i = i + 1
  }
  write(lines, out_dir, "mdsp", n)
}

///|
fn sample(i : Int32) -> Double {
  let v = i.to_int64() * 2654435761L % 1000L
  v.to_double() / 1000.0 - 0.5
}

///|
fn fill_hmem(mem : FixedArray[Double], n : Int32) -> Unit {
  let mut i = 0
  while i < n {
    mem.unsafe_set(i, sample(2 * i))
    mem.unsafe_set(n + i, sample(2 * i + 1))
    i = i + 1
  }
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

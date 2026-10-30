///|
/// Checks that two floats agree to within `eps`, relative to the magnitude
/// of the expectation.
fn assert_close(actual : Float, expected : Float, eps : Float) -> Unit raise {
  let diff = (actual - expected).abs()
  let magnitude = expected.abs()
  let scale = if magnitude > Float::from_int(1) {
    magnitude
  } else {
    Float::from_int(1)
  }
  assert_true(
    diff <= eps * scale,
    msg="expected \{expected}, got \{actual} (difference \{diff})",
  )
}

///|
/// Checks that two integers are equal.
fn assert_int_eq(actual : Int32, expected : Int32) -> Unit raise {
  assert_true(actual == expected, msg="expected \{expected}, got \{actual}")
}

///|
fn make_real(values : Array[Float]) -> RealImage {
  RealImage::from_data([values.length()], values)
}

///|
test "nfft tables match JTransforms" {
  assert_int_eq(nfft_small(1), 1)
  assert_int_eq(nfft_small(7), 7)
  assert_int_eq(nfft_small(17), 18)
  assert_int_eq(nfft_small(32), 33)
  assert_int_eq(nfft_fast(7), 8)
  assert_int_eq(nfft_fast(8), 8)
  assert_int_eq(nfft_fast(13), 15)
  assert_int_eq(nfft_fast(32), 36)
  assert_int_eq(nfft_fast(64), 72)
  assert_true(nfft_valid(16))
  assert_true(nfft_valid(33))
  assert_true(!nfft_valid(17))
  assert_true(!nfft_valid(32))
}

///|
/// The real valued transforms use their own length table: a real transform
/// of length n is built on a half length complex transform of (n + 1) / 2.
/// The expectations are the values of `edu.mines.jtk.dsp.FftReal`.
test "real nfft tables are twice the half length complex ones" {
  assert_int_eq(nfft_small_real(1), 2)
  assert_int_eq(nfft_small_real(2), 2)
  assert_int_eq(nfft_small_real(3), 4)
  assert_int_eq(nfft_small_real(4), 4)
  assert_int_eq(nfft_small_real(5), 6)
  assert_int_eq(nfft_small_real(7), 8)
  assert_int_eq(nfft_small_real(8), 8)
  assert_int_eq(nfft_small_real(9), 10)
  assert_int_eq(nfft_small_real(16), 16)
  assert_int_eq(nfft_small_real(17), 18)
  assert_int_eq(nfft_small_real(32), 32)
  assert_int_eq(nfft_small_real(33), 36)
  assert_int_eq(nfft_small_real(63), 66)
  assert_int_eq(nfft_small_real(64), 66)
  assert_int_eq(nfft_fast_real(1), 2)
  assert_int_eq(nfft_fast_real(2), 2)
  assert_int_eq(nfft_fast_real(3), 4)
  assert_int_eq(nfft_fast_real(4), 4)
  assert_int_eq(nfft_fast_real(5), 6)
  assert_int_eq(nfft_fast_real(7), 8)
  assert_int_eq(nfft_fast_real(8), 8)
  assert_int_eq(nfft_fast_real(9), 10)
  assert_int_eq(nfft_fast_real(16), 16)
  assert_int_eq(nfft_fast_real(17), 18)
  // the length 32 is the cheapest one for the half length 16, the complex
  // table would answer 36
  assert_int_eq(nfft_fast_real(32), 32)
  assert_int_eq(nfft_fast_real(33), 36)
  assert_int_eq(nfft_fast_real(63), 72)
  assert_int_eq(nfft_fast_real(64), 72)
}

///|
/// A real transform of length nfft needs nfft to be even and nfft / 2 to be
/// a valid complex length.
test "real transform lengths are validated" {
  assert_true(nfft_valid_real(2))
  assert_true(nfft_valid_real(8))
  assert_true(nfft_valid_real(32))
  assert_true(!nfft_valid_real(3))
  assert_true(!nfft_valid_real(34))
  assert_true(!nfft_valid_real(0))
}

///|
/// The real valued transforms are only supported for the lengths whose half
/// is a valid complex length, the original refuses the others.
test "real to complex refuses unsupported lengths instead of failing" {
  // an odd length has no valid half length complex transform
  let input = make_real([1.0, 2.0, 3.0, 4.0, 5.0])
  let output = ComplexImage::new([3])
  assert_true(!real_to_complex(input, output, None, 0, false))
  // the length 34 has the half length 17, which is not a valid length
  let longer = make_real([
    1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0, 13.0, 14.0, 15.0,
    16.0, 17.0, 18.0, 19.0, 20.0, 21.0, 22.0, 23.0, 24.0, 25.0, 26.0, 27.0, 28.0,
    29.0, 30.0, 31.0, 32.0, 33.0, 34.0,
  ])
  let longer_output = ComplexImage::new([18])
  assert_true(!real_to_complex(longer, longer_output, None, 0, false))
}

///|
/// The complex to real transform derives its real length from the input, and
/// refuses the complex lengths whose real length is not supported.
test "complex to real refuses unsupported lengths instead of failing" {
  let input = ComplexImage::from_data([18], zerosf(36))
  let output = RealImage::new([34])
  assert_true(!complex_to_real(input, output, None, 0, true))
  let supported = ComplexImage::from_data([5], zerosf(10))
  let supported_output = RealImage::new([8])
  assert_true(complex_to_real(supported, supported_output, None, 0, true))
}

///|
/// The original implementation reads the input of the high level complex to
/// real transform through a view that is not extended, so it fails whenever
/// the extent of the result differs from the extent of the input.
test "high level complex to real only supports the matching extents" {
  assert_true(fft_complex_to_real_supported([5, 4]))
  assert_true(fft_complex_to_real_supported([4]))
  assert_true(!fft_complex_to_real_supported([8, 1]))
  assert_true(!fft_complex_to_real_supported([12, 1]))
}

///|
/// The original extends the input with an out of bounds strategy before it
/// pads it.  The port supports the constant strategy, the other ones would
/// need the coordinate based access of `net.imglib2.RandomAccessible`.
test "the padding of the forward transform can be filled with a constant" {
  let input = make_real([1.0, 2.0, 3.0, 4.0, 5.0])
  // the length 5 is padded to 6, so the padding adds one sample
  let zero_filled = fft_real_to_complex(input)
  assert_int_eq(zero_filled.dims[0], 4)
  // the bin of the direct current is the sum of the padded samples
  assert_close(zero_filled.data[0], 15.0, 1.0e-5)
  let constant_filled = fft_real_to_complex_with_fill(input, 1.0)
  assert_int_eq(constant_filled.dims[0], 4)
  assert_close(constant_filled.data[0], 16.0, 1.0e-5)
  // the other bins are the spectrum of a constant sample, which is a pure
  // direct current
  assert_close(constant_filled.data[1], 0.0, 1.0e-5)
}

///|
/// The "small" variants of the dimension helpers pick the smallest supported
/// length instead of the cheapest one.
test "dimension helpers with the smallest lengths" {
  let complex_sizes = zeros(2)
  let real_sizes = zeros(2)
  dimensions_real_to_complex_small([8, 4], complex_sizes, real_sizes)
  assert_int_eq(real_sizes[0], 8)
  assert_int_eq(complex_sizes[0], 5)
  assert_int_eq(real_sizes[1], 4)
  assert_int_eq(complex_sizes[1], 4)
  dimensions_complex_to_real_small([5, 4], complex_sizes, real_sizes)
  assert_int_eq(complex_sizes[0], 5)
  assert_int_eq(real_sizes[0], 8)
  assert_int_eq(complex_sizes[1], 4)
  assert_int_eq(real_sizes[1], 4)
  let sizes = zeros(2)
  dimensions_complex_to_complex_small([8, 4], sizes)
  assert_int_eq(sizes[0], 8)
  assert_int_eq(sizes[1], 4)
}

///|
test "complex fft of a delta is flat" {
  let n = 8
  let input = zerosf(2 * n)
  input[0] = Float::from_int(1)
  let fft = FftComplex::new(n)
  let out = zerosf(2 * n)
  fft.complex_to_complex(-1, input, out)
  let mut i = 0
  while i < n {
    assert_close(out[2 * i], 1.0, 1.0e-5)
    assert_close(out[2 * i + 1], 0.0, 1.0e-5)
    i = i + 1
  }
}

///|
test "complex fft of a constant concentrates in the DC bin" {
  let n = 8
  let input = zerosf(2 * n)
  let mut i = 0
  while i < n {
    input[2 * i] = 1.0
    i = i + 1
  }
  let fft = FftComplex::new(n)
  let out = zerosf(2 * n)
  fft.complex_to_complex(-1, input, out)
  assert_close(out[0], 8.0, 1.0e-5)
  assert_close(out[1], 0.0, 1.0e-5)
  let mut k = 1
  while k < n {
    assert_close(out[2 * k], 0.0, 1.0e-5)
    assert_close(out[2 * k + 1], 0.0, 1.0e-5)
    k = k + 1
  }
}

///|
test "complex fft inverse round trip" {
  let n = 8
  let input = zerosf(2 * n)
  let mut i = 0
  while i < n {
    input[2 * i] = Float::from_double(0.5 * i.to_double() - 1.0)
    input[2 * i + 1] = Float::from_double(0.25 * i.to_double())
    i = i + 1
  }
  let fft = FftComplex::new(n)
  let spectrum = zerosf(2 * n)
  fft.complex_to_complex(-1, input, spectrum)
  let back = zerosf(2 * n)
  fft.complex_to_complex(1, spectrum, back)
  let scale = Float::from_int(n)
  let mut k = 0
  while k < 2 * n {
    assert_close(back[k] / scale, input[k], 1.0e-5)
    k = k + 1
  }
}

///|
test "real fft of a constant is a pure DC bin" {
  let n = 8
  let input = zerosf(n)
  let mut i = 0
  while i < n {
    input[i] = 1.0
    i = i + 1
  }
  let fft = FftReal::new(n)
  let out = zerosf(n + 2)
  fft.real_to_complex(-1, input, out)
  assert_close(out[0], 8.0, 1.0e-5)
  assert_close(out[1], 0.0, 1.0e-5)
  let mut k = 1
  while k < n / 2 + 1 {
    assert_close(out[2 * k], 0.0, 1.0e-5)
    assert_close(out[2 * k + 1], 0.0, 1.0e-5)
    k = k + 1
  }
}

///|
test "real fft of an alternating signal is a pure Nyquist bin" {
  let n = 8
  let input = zerosf(n)
  let mut i = 0
  while i < n {
    input[i] = if i % 2 == 0 { 1.0 } else { -1.0 }
    i = i + 1
  }
  let fft = FftReal::new(n)
  let out = zerosf(n + 2)
  fft.real_to_complex(-1, input, out)
  assert_close(out[0], 0.0, 1.0e-5)
  assert_close(out[2 * (n / 2)], 8.0, 1.0e-5)
}

///|
test "real fft round trip" {
  let n = 8
  let input = zerosf(n)
  let mut i = 0
  while i < n {
    input[i] = Float::from_double(0.5 * i.to_double() - 2.0)
    i = i + 1
  }
  let fft = FftReal::new(n)
  let spectrum = zerosf(n + 2)
  fft.real_to_complex(-1, input, spectrum)
  let back = zerosf(n)
  fft.complex_to_real(1, spectrum, back)
  let scale = Float::from_int(n)
  let mut k = 0
  while k < n {
    assert_close(back[k] / scale, input[k], 1.0e-5)
    k = k + 1
  }
}

///|
test "real to complex transform of an image" {
  let n = 8
  let input = make_real([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
  let output = ComplexImage::new([n / 2 + 1])
  assert_true(real_to_complex(input, output, None, 0, false))
  assert_int_eq(output.dims[0], 5)
  // the DC bin is the sum of all samples
  assert_close(output.data[0], 36.0, 1.0e-5)
  assert_close(output.data[1], 0.0, 1.0e-5)
  // the remaining bins of the spectrum of a ramp, the imaginary part does not
  // vanish because the signal is not even symmetric
  assert_close(output.data[2], -4.0, 1.0e-5)
  assert_close(output.data[3], 9.656854, 1.0e-5)
  assert_close(output.data[4], -4.0, 1.0e-5)
  assert_close(output.data[5], 4.0, 1.0e-5)
  assert_close(output.data[6], -4.0, 1.0e-5)
  assert_close(output.data[7], 1.656854, 1.0e-5)
  // the Nyquist bin is real
  assert_close(output.data[8], -4.0, 1.0e-5)
  assert_close(output.data[9], 0.0, 1.0e-5)
}

///|
test "scaled real to complex transform divides by the sample count" {
  let n = 8
  let input = make_real([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
  let output = ComplexImage::new([n / 2 + 1])
  assert_true(real_to_complex(input, output, None, 0, true))
  assert_close(output.data[0], 4.5, 1.0e-6)
}

///|
test "complex to complex transform along a dimension" {
  let data = ComplexImage::from_data([2, 2], [
    1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0,
  ])
  assert_true(complex_to_complex(data, 0, true, false))
  // the transform along the first dimension turns both columns into a sum
  // and a difference of their two samples
  assert_close(data.data[0], 1.0, 1.0e-5)
  assert_close(data.data[1], 0.0, 1.0e-5)
  assert_close(data.data[2], 1.0, 1.0e-5)
  assert_close(data.data[3], 0.0, 1.0e-5)
  assert_close(data.data[4], 1.0, 1.0e-5)
  assert_close(data.data[5], 0.0, 1.0e-5)
  assert_close(data.data[6], -1.0, 1.0e-5)
  assert_close(data.data[7], 0.0, 1.0e-5)
}

///|
test "complex to real transform" {
  let n = 8
  let input = make_real([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
  let spectrum = fft_real_to_complex(input)
  assert_int_eq(spectrum.dims[0], 5)
  let back = fft_complex_to_real(spectrum)
  assert_int_eq(back.dims[0], n)
  let mut k = 0
  while k < n {
    assert_close(back.data[k], input.data[k], 1.0e-4)
    k = k + 1
  }
}

///|
test "n-dimensional round trip" {
  let input = RealImage::from_data([4, 4], [
    0.5, -1.0, 2.0, 0.25, 1.5, 0.0, -0.5, 1.0, -2.0, 3.0, 0.125, -0.75, 0.0, 1.25,
    -1.5, 2.5,
  ])
  let spectrum = fft_real_to_complex(input)
  assert_int_eq(spectrum.dims.length(), 2)
  assert_int_eq(spectrum.dims[0], 3)
  assert_int_eq(spectrum.dims[1], 4)
  let back = fft_complex_to_real(spectrum)
  assert_int_eq(back.dims[0], 4)
  assert_int_eq(back.dims[1], 4)
  let mut k = 0
  while k < 16 {
    assert_close(back.data[k], input.data[k], 1.0e-4)
    k = k + 1
  }
}

///|
test "forward and inverse complex transform round trip" {
  let data = ComplexImage::from_data([4, 4], [
    0.5, -1.0, 2.0, 0.25, 1.5, 0.0, -0.5, 1.0, -2.0, 3.0, 0.125, -0.75, 0.0, 1.25,
    -1.5, 2.5, 3.0, -1.0, 0.5, 0.25, -1.0, 2.0, 0.75, 1.0, 1.0, -3.0, 2.0, 0.5, -0.25,
    1.5, 0.5, -1.0,
  ])
  let original = data.data.copy()
  fft_complex_to_complex_forward(data)
  fft_complex_to_complex_inverse(data)
  let mut k = 0
  while k < original.length() {
    assert_close(data.data[k], original[k], 1.0e-4)
    k = k + 1
  }
}

///|
test "padding interval is centred" {
  let input = Interval::new([8, 4])
  let padded = padding_interval_centered(input, [16, 8])
  assert_int_eq(padded.min[0], -4)
  assert_int_eq(padded.max[0], 11)
  assert_int_eq(padded.dimension(0), 16)
  assert_int_eq(padded.min[1], -2)
  assert_int_eq(padded.max[1], 5)
  assert_int_eq(padded.dimension(1), 8)
}

///|
test "odd padding adds the extra sample on the high side" {
  let input = Interval::new([9, 5])
  let padded = padding_interval_centered(input, [16, 8])
  assert_int_eq(padded.min[0], -3)
  assert_int_eq(padded.max[0], 12)
  assert_int_eq(padded.dimension(0), 16)
  assert_int_eq(padded.min[1], -1)
  assert_int_eq(padded.max[1], 6)
  assert_int_eq(padded.dimension(1), 8)
}

///|
test "unpadding interval recovers the original extent" {
  let padded = Interval::new([16, 8])
  let unpadded = unpadding_interval_centered(padded, [8, 4])
  assert_int_eq(unpadded.dimension(0), 8)
  assert_int_eq(unpadded.dimension(1), 4)
}

///|
test "dimension helpers" {
  let dims = [8, 4]
  let complex_sizes = zeros(2)
  let real_sizes = zeros(2)
  dimensions_real_to_complex_fast(dims, complex_sizes, real_sizes)
  assert_int_eq(complex_sizes[0], 5)
  assert_int_eq(real_sizes[0], 8)
  assert_int_eq(complex_sizes[1], 4)
  assert_int_eq(real_sizes[1], 4)
  dimensions_complex_to_real_fast([5, 4], complex_sizes, real_sizes)
  assert_int_eq(complex_sizes[0], 5)
  assert_int_eq(real_sizes[0], 8)
  assert_int_eq(complex_sizes[1], 4)
  assert_int_eq(real_sizes[1], 4)
  let sizes = zeros(2)
  dimensions_complex_to_complex_fast(dims, sizes)
  assert_int_eq(sizes[0], 8)
  assert_int_eq(sizes[1], 4)
}

///|
test "verify dimensions" {
  assert_true(verify_real_to_complex_fft_dimensions(8, 5))
  assert_true(!verify_real_to_complex_fft_dimensions(8, 6))
  assert_true(verify_complex_to_complex_fft_dimensions(8, 8))
  assert_true(verify_complex_to_complex_fft_dimensions(7, 7))
  assert_true(!verify_complex_to_complex_fft_dimensions(7, 9))
}

///|
test "complex conjugate flips the imaginary parts" {
  let data = ComplexImage::from_data([2], [1.0, 2.0, 3.0, -4.0])
  complex_conjugate(data)
  assert_close(data.data[1], -2.0, 1.0e-6)
  assert_close(data.data[3], 4.0, 1.0e-6)
}

///|
test "complex to real writes the cropped range at the origin of the output" {
  let input = make_real([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
  let spectrum = fft_real_to_complex(input)
  assert_int_eq(spectrum.dims[0], 5)
  // the spectrum describes eight real samples, only the first four of them
  // are written
  let output = RealImage::new([4])
  assert_true(
    complex_to_real(spectrum, output, Some(Interval::new([4])), 0, true),
  )
  let mut k = 0
  while k < 4 {
    assert_close(output.data[k], input.data[k], 1.0e-4)
    k = k + 1
  }
}

///|
test "complex to real unpad removes the padding around the result" {
  let input = make_real([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
  let spectrum = fft_real_to_complex(input)
  assert_int_eq(spectrum.dims[0], 5)
  // the spectrum describes eight real samples, the unpadded result keeps the
  // middle four of them
  let output = fft_complex_to_real_unpad(spectrum, [4])
  assert_int_eq(output.dims[0], 4)
  let mut k = 0
  while k < 4 {
    assert_close(output.data[k], input.data[k + 2], 1.0e-4)
    k = k + 1
  }
}

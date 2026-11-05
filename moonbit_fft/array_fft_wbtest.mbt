///|
/// A deterministic sequence of `n` complex points, interleaved.
///
/// The values are small integers, so that the sequence has no symmetry that
/// could hide a mistake of the transform: every bin of its spectrum is
/// non-zero.
fn sample_complex(n : Int32) -> Array[Float] {
  let x = zerosf(2 * n)
  let mut i = 0
  while i < n {
    x[2 * i] = Float::from_int(i % 7 - 3)
    x[2 * i + 1] = Float::from_int(i * 5 % 11 - 5)
    i = i + 1
  }
  x
}

///|
test "the normalised inverse undoes the forward transform at every length" {
  for n in [1, 2, 3, 4, 5, 7, 8, 12, 16, 120, 720] {
    let complex_fft = FftComplex::new(n)
    let x = sample_complex(n)
    let spectrum = zerosf(2 * n)
    let back = zerosf(2 * n)
    complex_fft.complex_to_complex(-1, x, spectrum)
    complex_fft.ifft(spectrum, back)
    let mut i = 0
    while i < 2 * n {
      assert_close(back[i], x[i], 1.0e-5)
      i = i + 1
    }
  }
}

///|
test "the normalised inverse is the unnormalised one divided by the length" {
  for n in [1, 2, 3, 5, 8, 13, 16] {
    let complex_fft = FftComplex::new(n)
    let x = sample_complex(n)
    let spectrum = zerosf(2 * n)
    complex_fft.complex_to_complex(-1, x, spectrum)
    let unnormalised = zerosf(2 * n)
    let normalised = zerosf(2 * n)
    complex_fft.complex_to_complex(1, spectrum, unnormalised)
    complex_fft.ifft(spectrum, normalised)
    let divisor = Float::from_int(n)
    let mut i = 0
    while i < 2 * n {
      assert_close(normalised[i], unnormalised[i] / divisor, 1.0e-6)
      i = i + 1
    }
  }
}

///|
test "the normalised inverse only scales the points of the transform" {
  let n = 8
  let complex_fft = FftComplex::new(n)
  let x = sample_complex(n)
  // The output is longer than the transform, and the entries past the `2 * n`
  // points of it are not part of the result, so they must not be touched.
  let padded = zerosf(2 * n + 4)
  padded[2 * n] = Float::from_int(7)
  padded[2 * n + 1] = Float::from_int(-7)
  padded[2 * n + 2] = Float::from_int(11)
  padded[2 * n + 3] = Float::from_int(13)
  complex_fft.ifft(x, padded)
  assert_close(padded[2 * n], Float::from_int(7), 1.0e-6)
  assert_close(padded[2 * n + 1], Float::from_int(-7), 1.0e-6)
  assert_close(padded[2 * n + 2], Float::from_int(11), 1.0e-6)
  assert_close(padded[2 * n + 3], Float::from_int(13), 1.0e-6)
}

///|
test "the array transforms undo each other" {
  for n in [1, 2, 4, 5, 8, 16, 120] {
    let x = sample_complex(n)
    let back = ifft(fft(x))
    assert_int_eq(back.length(), 2 * n)
    let mut i = 0
    while i < 2 * n {
      assert_close(back[i], x[i], 1.0e-5)
      i = i + 1
    }
  }
}

///|
test "the array transforms leave the input alone" {
  let n = 8
  let x = sample_complex(n)
  let before = zerosf(2 * n)
  let mut i = 0
  while i < 2 * n {
    before[i] = x[i]
    i = i + 1
  }
  let _ = fft(x)
  let _ = ifft(x)
  i = 0
  while i < 2 * n {
    assert_close(x[i], before[i], 0.0)
    i = i + 1
  }
}

///|
test "the forward transform of a delta is flat and the inverse returns it" {
  let n = 8
  let x = zerosf(2 * n)
  x[0] = Float::from_int(1)
  let spectrum = fft(x)
  // Every bin of the spectrum of a delta holds 1, and the unscaled forward
  // transform is what puts it there.
  let mut k = 0
  while k < n {
    assert_close(spectrum[2 * k], 1.0, 1.0e-6)
    assert_close(spectrum[2 * k + 1], 0.0, 1.0e-6)
    k = k + 1
  }
  // The inverse is scaled by `1 / n`, so a flat spectrum of ones becomes a
  // single sample worth 1, not worth `n`.
  let back = ifft(spectrum)
  assert_close(back[0], 1.0, 1.0e-6)
  assert_close(back[1], 0.0, 1.0e-6)
  k = 1
  while k < n {
    assert_close(back[2 * k], 0.0, 1.0e-6)
    assert_close(back[2 * k + 1], 0.0, 1.0e-6)
    k = k + 1
  }
}

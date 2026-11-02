///|
/// Tests of the mixed radix kernel of `mixed_radix.mbt`.
///
/// The parity suite of `parity_wbtest.mbt` checks the port against the
/// original Java bytecode, but it reaches the kernel only through the image
/// API.  These tests check the kernel itself: every radix it uses has to
/// reproduce the direct evaluation of the discrete Fourier transform, and
/// every valid length of the original has to be a fixed point of the forward
/// and the inverse transform.

///|
/// The direct evaluation of the discrete Fourier transform, `O(n^2)`, which is
/// the reference of the mixed radix kernel.
///
/// `sign` is `-1` for the forward transform and `1` for the inverse one.
fn naive_dft(sign : Int32, re : Array[Double], im : Array[Double]) -> Unit {
  let n = re.length()
  let out_re = Array::Array(capacity=n)
  let out_im = Array::Array(capacity=n)
  let mut k = 0
  while k < n {
    let mut sr = 0.0
    let mut si = 0.0
    let mut j = 0
    while j < n {
      // The product of the two indices is computed in 64 bits: it does not
      // fit into 32 bits for a length of more than 46341.
      let angle = sign.to_double() *
        6.283185307179586 *
        (j.to_int64() * k.to_int64()).to_double() /
        n.to_double()
      let wr = @math.cos(angle)
      let wi = @math.sin(angle)
      let vr = re[j]
      let vi = im[j]
      sr = sr + (vr * wr - vi * wi)
      si = si + (vr * wi + vi * wr)
      j = j + 1
    }
    out_re.push(sr)
    out_im.push(si)
    k = k + 1
  }
  let mut i = 0
  while i < n {
    re[i] = out_re[i]
    im[i] = out_im[i]
    i = i + 1
  }
}

///|
/// A deterministic test signal of `n` points, the real and the imaginary part
/// are different pseudo random sequences.
fn test_signal(n : Int32) -> (Array[Double], Array[Double]) {
  let re = Array::Array(capacity=n)
  let im = Array::Array(capacity=n)
  let mut j = 0
  while j < n {
    re.push((j * 37 % 41).to_double() / 20.0 - 0.5)
    im.push((j * 53 % 43).to_double() / 21.0 - 0.5)
    j = j + 1
  }
  (re, im)
}

///|
/// Compares a spectrum of the port with the expectation, the tolerance is
/// relative to the magnitude of the whole spectrum and not to a single
/// sample: a sample that happens to be close to zero still carries the
/// rounding error of the whole transform.
fn assert_spectrum_close(
  actual : Array[Float],
  expected_re : Array[Double],
  expected_im : Array[Double],
  eps : Double,
) -> Unit raise {
  let n = expected_re.length()
  let mut magnitude = 0.0
  let mut k = 0
  while k < n {
    let m = expected_re[k].abs() + expected_im[k].abs()
    if m > magnitude {
      magnitude = m
    }
    k = k + 1
  }
  if magnitude < 1.0 {
    magnitude = 1.0
  }
  let mut worst = 0.0
  k = 0
  while k < n {
    let dr = actual[2 * k].to_double() - expected_re[k]
    let di = actual[2 * k + 1].to_double() - expected_im[k]
    let d = dr * dr + di * di
    if d > worst {
      worst = d
    }
    k = k + 1
  }
  assert_true(
    worst <= eps * eps * magnitude * magnitude,
    msg="the deviation of the spectrum is \{worst}, the tolerance is \{eps * eps * magnitude * magnitude}",
  )
}

///|
/// The steps of `dft_inplace`, but in double precision and on separate
/// arrays, so that the kernel can be checked without the rounding of the
/// `Float` samples.
fn dft_double(
  sign : Int32,
  n : Int32,
  re : Array[Double],
  im : Array[Double],
) -> Unit {
  dft_plan_double(sign, plan_for(n), re, im)
}

///|
/// The same steps as `dft_double`, but for a plan that is given and not
/// looked up, so that a length the original does not support can be checked
/// as well.
fn dft_plan_double(
  sign : Int32,
  plan : FftPlan,
  re : Array[Double],
  im : Array[Double],
) -> Unit {
  let n = plan.n
  let inverse = sign > 0
  let src_re = Array::Array(capacity=n)
  let src_im = Array::Array(capacity=n)
  let mut j = 0
  while j < n {
    let src = plan.perm[j]
    let vr = re[src]
    let vi = im[src]
    src_re.push(vr)
    src_im.push(if inverse { -vi } else { vi })
    j = j + 1
  }
  j = 0
  while j < n {
    re[j] = src_re[j]
    im[j] = src_im[j]
    j = j + 1
  }
  dft_plan(plan, re, im)
  j = 0
  while j < n {
    if inverse {
      im[j] = -im[j]
    }
    j = j + 1
  }
}

///|
/// The mixed radix kernel has to reproduce the direct evaluation of the
/// discrete Fourier transform, for every radix it uses and for both
/// directions.
test "the mixed radix kernel agrees with the direct transform" {
  let lengths = [
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 20, 21, 22, 24, 26,
    28, 30, 33, 35, 36, 39, 40, 42, 44, 45, 48, 52, 55, 56, 60, 63, 65, 66, 70, 72,
    77, 78, 80, 84, 88, 90, 91, 99, 104, 105, 110, 112, 117, 120, 126, 130, 132,
    140, 143, 144, 154, 156, 165, 168, 176, 180, 182, 195, 198, 208, 210, 220, 231,
    234, 240, 252, 260, 264, 273, 280, 286, 308, 312, 315, 330, 336, 360, 364,
  ]
  let mut index = 0
  while index < lengths.length() {
    let n = lengths[index]
    assert_true(nfft_valid(n), msg="\{n} is not a valid transform length")
    let (re, im) = test_signal(n)
    let forward_re = re.copy()
    let forward_im = im.copy()
    naive_dft(-1, forward_re, forward_im)
    let inverse_re = re.copy()
    let inverse_im = im.copy()
    naive_dft(1, inverse_re, inverse_im)
    // The forward transform of the port.
    let samples = Array::Array(capacity=2 * n)
    let mut j = 0
    while j < n {
      samples.push(Float::from_double(re[j]))
      samples.push(Float::from_double(im[j]))
      j = j + 1
    }
    let fft = FftComplex::new(n)
    let spectrum = zerosf(2 * n)
    fft.complex_to_complex(-1, samples, spectrum)
    assert_spectrum_close(spectrum, forward_re, forward_im, 1.0e-5)
    // And the inverse one.
    fft.complex_to_complex(1, samples, spectrum)
    assert_spectrum_close(spectrum, inverse_re, inverse_im, 1.0e-5)
    index = index + 1
  }
}

///|
/// Every valid length of the original has to be a fixed point of the forward
/// and the inverse transform: the inverse of the forward transform is the
/// signal multiplied by the length of the transform.
///
/// The check runs in double precision, so that it is not limited by the
/// rounding of the `Float` samples of the public API.
test "the forward and the inverse transform undo each other at every length" {
  let mut index = 0
  while index < ntable.length() {
    let n = ntable[index]
    let (re, im) = test_signal(n)
    let spectrum_re = re.copy()
    let spectrum_im = im.copy()
    dft_double(-1, n, spectrum_re, spectrum_im)
    dft_double(1, n, spectrum_re, spectrum_im)
    let mut magnitude = 0.0
    let mut j = 0
    while j < n {
      let m = (re[j] * n.to_double()).abs()
      if m > magnitude {
        magnitude = m
      }
      j = j + 1
    }
    if magnitude < 1.0 {
      magnitude = 1.0
    }
    let mut worst = 0.0
    j = 0
    while j < n {
      let dr = spectrum_re[j] - re[j] * n.to_double()
      let di = spectrum_im[j] - im[j] * n.to_double()
      let d = dr * dr + di * di
      if d > worst {
        worst = d
      }
      j = j + 1
    }
    assert_true(
      worst <= 1.0e-18 * magnitude * magnitude,
      msg="the round trip of the length \{n} deviates by \{worst}",
    )
    index = index + 1
  }
}

///|
/// The plan of a length is reused, so a transform must not depend on the
/// transforms that ran before it.
test "a transform does not depend on the transforms before it" {
  let (re, im) = test_signal(120)
  let samples = Array::Array(capacity=240)
  let mut j = 0
  while j < 120 {
    samples.push(Float::from_double(re[j]))
    samples.push(Float::from_double(im[j]))
    j = j + 1
  }
  let fft = FftComplex::new(120)
  let first = zerosf(240)
  fft.complex_to_complex(-1, samples, first)
  // A transform of another length in between, it uses another plan.
  let other = FftComplex::new(77)
  let other_samples = Array::Array(capacity=154)
  j = 0
  while j < 77 {
    other_samples.push(Float::from_double(re[j]))
    other_samples.push(Float::from_double(im[j]))
    j = j + 1
  }
  let other_spectrum = zerosf(154)
  other.complex_to_complex(-1, other_samples, other_spectrum)
  // And the same transform again.
  let second = zerosf(240)
  fft.complex_to_complex(-1, samples, second)
  let mut k = 0
  while k < 240 {
    assert_close(second[k], first[k], 1.0e-6)
    k = k + 1
  }
}

///|
/// Compares two spectra of double precision, the tolerance is relative to the
/// magnitude of the whole spectrum and not to a single sample.
fn assert_double_spectrum_close(
  actual_re : Array[Double],
  actual_im : Array[Double],
  expected_re : Array[Double],
  expected_im : Array[Double],
  eps : Double,
) -> Unit raise {
  let n = expected_re.length()
  let mut magnitude = 0.0
  let mut k = 0
  while k < n {
    let m = expected_re[k].abs() + expected_im[k].abs()
    if m > magnitude {
      magnitude = m
    }
    k = k + 1
  }
  if magnitude < 1.0 {
    magnitude = 1.0
  }
  let mut worst = 0.0
  k = 0
  while k < n {
    let dr = actual_re[k] - expected_re[k]
    let di = actual_im[k] - expected_im[k]
    let d = dr * dr + di * di
    if d > worst {
      worst = d
    }
    k = k + 1
  }
  assert_true(
    worst <= eps * eps * magnitude * magnitude,
    msg="the deviation of the spectrum is \{worst}, the tolerance is \{eps * eps * magnitude * magnitude}",
  )
}

///|
/// The valid lengths of the original only use the radices 2, 3, 5, 7, 11 and
/// 13, all of which have a specialised butterfly.  The generic butterfly,
/// which evaluates the small transform with a matrix, is the fallback for
/// every other radix, and it has to work as well.
///
/// The length 17 is a prime that the original does not support, so it
/// exercises the generic butterfly with a radix that is larger than every
/// radix of the valid lengths.
test "the generic butterfly handles a radix without a specialised kernel" {
  let lengths = [17, 19, 23, 29, 31, 34, 46, 51, 58, 62, 69, 87, 93, 116, 124]
  let mut index = 0
  while index < lengths.length() {
    let n = lengths[index]
    let plan = build_plan(n)
    let (re, im) = test_signal(n)
    let forward_re = re.copy()
    let forward_im = im.copy()
    naive_dft(-1, forward_re, forward_im)
    let inverse_re = re.copy()
    let inverse_im = im.copy()
    naive_dft(1, inverse_re, inverse_im)
    let got_re = re.copy()
    let got_im = im.copy()
    dft_plan_double(-1, plan, got_re, got_im)
    assert_double_spectrum_close(
      got_re, got_im, forward_re, forward_im, 1.0e-12,
    )
    let back_re = re.copy()
    let back_im = im.copy()
    dft_plan_double(1, plan, back_re, back_im)
    assert_double_spectrum_close(
      back_re, back_im, inverse_re, inverse_im, 1.0e-12,
    )
    index = index + 1
  }
}

///|
/// The plan of a length is built once and then reused; that is what makes a
/// transform of a length that was used before cheap.
///
/// The check does not look at the identity of the plan, it looks at its
/// effect: the work buffer of the plan holds the spectrum of the last
/// transform, so a plan that was built again would have an empty buffer.
test "the plan of a length is built once and then reused" {
  let n = 120
  // The plan of the length; it may already be cached from another test.
  let plan = plan_for(n)
  let cost = plan_cache_cost[0]
  // The second call has to find the plan and must not build it again.
  let again = plan_for(n)
  assert_int_eq(plan_cache_cost[0], cost)
  // A transform of a delta writes its spectrum into the work buffer of the
  // plan, so a plan that was built again would have an empty buffer.
  let samples = zerosf(2 * n)
  samples[0] = Float::from_int(1)
  let fft = FftComplex::new(n)
  let spectrum = zerosf(2 * n)
  fft.complex_to_complex(-1, samples, spectrum)
  assert_true(
    (plan.buf_re[0] - 1.0).abs() < 1.0e-9,
    msg="the work buffer of the plan has to hold the spectrum, it is \{plan.buf_re[0]}",
  )
  assert_true(
    (again.buf_re[0] - plan.buf_re[0]).abs() < 1.0e-9,
    msg="the second call has to return the cached plan, its buffer holds \{again.buf_re[0]}",
  )
}

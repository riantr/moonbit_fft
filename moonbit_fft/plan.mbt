///|
/// The plan that a caller keeps: building one outside the cache of the
/// module, and the entries that transform with it.
///
/// The contract that a caller relies on - the plan is immutable, and the unit
/// of concurrency is the buffer and not the plan - is written on `FftPlan`
/// itself in `mixed_radix.mbt`, where the plan is defined.

///|
/// The length of the transform of the plan.
pub fn FftPlan::nfft(self : FftPlan) -> Int32 {
  self.n
}

///|
/// Builds the plan of the length `n`, which is not entered into the cache of
/// the module.
///
/// The plan keeps its own workspace, which costs sixteen bytes per element of
/// the length, and it lives as long as the caller keeps it.  `n` must be a
/// valid FFT length, see `nfft_valid`.
pub fn FftPlan::create(n : Int32) -> FftPlan {
  if !nfft_valid(n) {
    abort("FftPlan: " + n.to_string() + " is not a valid FFT length")
  }
  build_plan(n)
}

///|
/// Transforms the `n` complex points of `cx` into `cy` with the plan.
///
/// The same convention as `FftComplex::complex_to_complex`: both arrays hold
/// interleaved `(real, imaginary)` pairs and must have at least `2 * n`
/// entries, `sign` is `-1` for the forward and `1` for the unnormalised
/// inverse transform, and `cx` may be `cy`.
///
/// The transform runs in the workspace of the plan, so two calls that overlap
/// on the same plan must not both use this function.
/// `FftPlan::complex_to_complex_buffers` is the entry that carries its own
/// workspace.
pub fn FftPlan::complex_to_complex(
  self : FftPlan,
  sign : Int32,
  cx : Array[Float],
  cy : Array[Float],
) -> Unit {
  check_sign(sign)
  let n = self.n
  if cx.length() < 2 * n || cy.length() < 2 * n {
    abort("FftPlan: array too short")
  }
  if n <= 1 {
    // The transform of a single point is the point itself.  The transform of
    // nothing is nothing.
    if n == 1 {
      cy[0] = cx[0]
      cy[1] = cx[1]
    }
    return
  }
  dft_from_to_plan(sign, self, cx, cy)
}

///|
/// Transforms the `n` complex points of `re` and `im` in place with the plan,
/// in double precision.
///
/// This is the entry that carries no workspace of its own: it reads the plan
/// and it writes nothing but the two arrays it is given, so many calls can
/// share one plan at the same time as long as no two of them share a buffer.
/// `sign` is `-1` for the forward and `1` for the unnormalised inverse
/// transform, which is the conjugate of the forward transform of the
/// conjugated input.
pub fn FftPlan::complex_to_complex_buffers(
  self : FftPlan,
  sign : Int32,
  re : Array[Double],
  im : Array[Double],
) -> Unit {
  check_sign(sign)
  let n = self.n
  if re.length() < n || im.length() < n {
    abort("FftPlan: buffer too short")
  }
  if n <= 1 {
    return
  }
  let inverse = sign > 0
  let mut j = 0
  while j < n {
    if inverse {
      im[j] = -im[j]
    }
    j = j + 1
  }
  dft_plan(self, re, im)
  if inverse {
    j = 0
    while j < n {
      im[j] = -im[j]
      j = j + 1
    }
  }
}

///|
/// Transforms the `n` complex points of `cx` into the **normalised** inverse
/// transform in `cy` with the plan, so that the inverse undoes a forward
/// transform of the same length.
///
/// This is the `ifft` of FFTW.jl: the unnormalised inverse transform divided
/// by `n`, the same as `FftComplex::ifft`.
pub fn FftPlan::ifft(
  self : FftPlan,
  cx : Array[Float],
  cy : Array[Float],
) -> Unit {
  self.complex_to_complex(1, cx, cy)
  // The transform has already written `2 * n` values into `cy`, and `cy` may
  // be longer than that, so only that prefix is scaled.
  let n = self.n
  let divisor = Float::from_int(n)
  let mut i = 0
  while i < 2 * n {
    cy[i] = cy[i] / divisor
    i = i + 1
  }
}

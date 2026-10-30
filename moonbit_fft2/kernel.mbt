///|
/// The double precision value of pi, identical to Java's `Math.PI`.
/// Two times pi.
let two_pi : Double = 6.283185307179586

///|
/// Checks that a transform direction is either `-1` (forward) or `1`
/// (inverse).
fn check_sign(sign : Int32) -> Unit {
  if sign != 1 && sign != -1 {
    abort("FFT direction must be 1 or -1")
  }
}

///|
/// Returns true if `n` is a power of two.
fn is_power_of_two(n : Int32) -> Bool {
  n > 0 && (n & (n - 1)) == 0
}

///|
/// Precomputes the `n` twiddle factors `exp(sign * 2 * pi * i / n)`.
fn twiddle_table(sign : Int32, n : Int32) -> (Array[Double], Array[Double]) {
  let re = Array::Array(capacity=n)
  let im = Array::Array(capacity=n)
  let s = sign.to_double()
  let nn = n.to_double()
  let mut i = 0
  while i < n {
    let ang = s * two_pi * i.to_double() / nn
    re.push(@math.cos(ang))
    im.push(@math.sin(ang))
    i = i + 1
  }
  (re, im)
}

///|
/// In-place discrete Fourier transform of `n` complex points stored as
/// interleaved `(real, imaginary)` pairs in `c`.
///
/// `sign` selects the direction: `-1` computes the forward transform
/// `X[k] = sum_j x[j] * exp(-2*pi*i*j*k/n)`, `1` computes the *unnormalised*
/// inverse `X[k] = sum_j x[j] * exp(+2*pi*i*j*k/n)`.  This matches the
/// convention of `edu.mines.jtk.dsp.FftComplex`, where the inverse transform
/// does not divide by `n`.
///
/// The Java original evaluates the transform in single precision with a mixed
/// radix PFA kernel.  The port accumulates in double precision and rounds the
/// result back to single precision, so the difference to the original is
/// dominated by the rounding error of the original instead of by the error of
/// the port.
fn dft_inplace(sign : Int32, n : Int32, c : Array[Float]) -> Unit {
  if n <= 1 {
    return
  }
  let re = Array::Array(capacity=n)
  let im = Array::Array(capacity=n)
  let mut i = 0
  while i < n {
    re.push(c[2 * i].to_double())
    im.push(c[2 * i + 1].to_double())
    i = i + 1
  }
  if is_power_of_two(n) {
    dft_radix2(sign, n, re, im)
  } else {
    dft_naive(sign, n, re, im)
  }
  let mut i = 0
  while i < n {
    c[2 * i] = Float::from_double(re[i])
    c[2 * i + 1] = Float::from_double(im[i])
    i = i + 1
  }
}

///|
/// Iterative radix-2 decimation-in-time Cooley-Tukey transform.
fn dft_radix2(
  sign : Int32,
  n : Int32,
  c_re : Array[Double],
  c_im : Array[Double],
) -> Unit {
  // bit reversal permutation
  let mut j = 0
  let mut i = 0
  while i < n {
    if i < j {
      let tr = c_re[i]
      c_re[i] = c_re[j]
      c_re[j] = tr
      let ti = c_im[i]
      c_im[i] = c_im[j]
      c_im[j] = ti
    }
    let mut m = n / 2
    while m >= 1 && j >= m {
      j = j - m
      m = m / 2
    }
    j = j + m
    i = i + 1
  }
  // butterflies
  let (tw_re, tw_im) = twiddle_table(sign, n)
  let mut len = 2
  while len <= n {
    let half = len / 2
    let step = n / len
    let mut base = 0
    while base < n {
      let mut k = 0
      while k < half {
        let wr = tw_re[k * step]
        let wi = tw_im[k * step]
        let a = base + k
        let b = base + k + half
        let vr = c_re[b]
        let vi = c_im[b]
        let tr = vr * wr - vi * wi
        let ti = vr * wi + vi * wr
        let ur = c_re[a]
        let ui = c_im[a]
        c_re[a] = ur + tr
        c_im[a] = ui + ti
        c_re[b] = ur - tr
        c_im[b] = ui - ti
        k = k + 1
      }
      base = base + len
    }
    len = len * 2
  }
}

///|
/// Direct evaluation of the DFT, used for lengths that are not a power of
/// two.
fn dft_naive(
  sign : Int32,
  n : Int32,
  c_re : Array[Double],
  c_im : Array[Double],
) -> Unit {
  let (tw_re, tw_im) = twiddle_table(sign, n)
  let out_re = Array::Array(capacity=n)
  let out_im = Array::Array(capacity=n)
  let mut k = 0
  while k < n {
    let mut sr = 0.0
    let mut si = 0.0
    let mut j = 0
    while j < n {
      let idx = j * k % n
      let wr = tw_re[idx]
      let wi = tw_im[idx]
      let xr = c_re[j]
      let xi = c_im[j]
      sr = sr + (xr * wr - xi * wi)
      si = si + (xr * wi + xi * wr)
      j = j + 1
    }
    out_re.push(sr)
    out_im.push(si)
    k = k + 1
  }
  let mut i = 0
  while i < n {
    c_re[i] = out_re[i]
    c_im[i] = out_im[i]
    i = i + 1
  }
}

///|
/// Complex-to-complex FFT of a fixed length.
///
/// Mirrors `edu.mines.jtk.dsp.FftComplex`.
pub struct FftComplex {
  n : Int32
}

///|
/// Creates a complex FFT of length `n`.
///
/// `n` must be a valid FFT length, see `nfft_valid`.
pub fn FftComplex::new(n : Int32) -> FftComplex {
  if !nfft_valid(n) {
    abort("FftComplex: " + n.to_string() + " is not a valid FFT length")
  }
  { n, }
}

///|
/// The length of the transform.
pub fn FftComplex::nfft(self : FftComplex) -> Int32 {
  self.n
}

///|
/// Transforms the `n` complex points of `cx` into `cy`.
///
/// Both arrays hold interleaved `(real, imaginary)` pairs and must have at
/// least `2 * n` entries.  `sign` is `-1` for the forward and `1` for the
/// unnormalised inverse transform.
pub fn FftComplex::complex_to_complex(
  self : FftComplex,
  sign : Int32,
  cx : Array[Float],
  cy : Array[Float],
) -> Unit {
  check_sign(sign)
  let n = self.n
  if cx.length() < 2 * n || cy.length() < 2 * n {
    abort("FftComplex: array too short")
  }
  let mut i = 0
  while i < 2 * n {
    cy[i] = cx[i]
    i = i + 1
  }
  dft_inplace(sign, n, cy)
}

///|
/// Real-to-complex and complex-to-real FFT of a fixed length.
///
/// Mirrors `edu.mines.jtk.dsp.FftReal`.
pub struct FftReal {
  nfft : Int32
}

///|
/// Creates a real FFT of length `nfft`.
///
/// `nfft` must be even and `nfft / 2` must be a valid FFT length.
pub fn FftReal::new(nfft : Int32) -> FftReal {
  if nfft % 2 != 0 || !nfft_valid(nfft / 2) {
    abort("FftReal: " + nfft.to_string() + " is not a valid FFT length")
  }
  { nfft, }
}

///|
/// The length of the transform.
pub fn FftReal::nfft(self : FftReal) -> Int32 {
  self.nfft
}

///|
/// Transforms the `nfft` real samples of `rx` into the `nfft / 2 + 1`
/// complex spectrum of `cy`.
///
/// `cy` holds interleaved `(real, imaginary)` pairs and must have at least
/// `nfft + 2` entries.  `sign` is `-1` for the forward transform.
pub fn FftReal::real_to_complex(
  self : FftReal,
  sign : Int32,
  rx : Array[Float],
  cy : Array[Float],
) -> Unit {
  check_sign(sign)
  let nfft = self.nfft
  if rx.length() < nfft || cy.length() < nfft + 2 {
    abort("FftReal: array too short")
  }
  let mut i = nfft - 1
  while i >= 0 {
    cy[i] = Float::from_double(0.5) * rx[i]
    i = i - 1
  }
  dft_inplace(sign, nfft / 2, cy)
  // The first and the last bin of the spectrum are not covered by the
  // rotation below, they are computed from the DC bin of the half length
  // transform instead.  Both of them are real.
  let two = Float::from_double(2.0)
  cy[nfft] = two * (cy[0] - cy[1])
  cy[0] = two * (cy[0] + cy[1])
  cy[nfft + 1] = Float::from_int(0)
  cy[1] = Float::from_int(0)
  // rotation of the conjugate symmetric spectrum; the twiddle factor is
  // advanced by a recurrence instead of a trigonometric call
  let theta = sign.to_double() * two_pi / nfft.to_double()
  let wt = @math.sin(0.5 * theta)
  let c = -2.0 * wt * wt
  let s2 = @math.sin(theta)
  let mut a = 1.0 + c
  let mut b = s2
  let mut k = 2
  let mut m = nfft - 2
  while k <= m {
    let r1 = cy[k] + cy[m]
    let i1 = cy[k + 1] + cy[m + 1]
    let r2 = cy[k] - cy[m]
    let i2 = cy[k + 1] - cy[m + 1]
    let t23 = Float::from_double(b * r2.to_double() + a * i1.to_double())
    let t24 = Float::from_double(b * i1.to_double() - a * r2.to_double())
    cy[k] = r1 + t23
    cy[k + 1] = t24 + i2
    cy[m] = r1 - t23
    cy[m + 1] = t24 - i2
    let old_a = a
    a = a + (a * c - b * s2)
    b = b + (b * c + old_a * s2)
    k = k + 2
    m = m - 2
  }
}

///|
/// Transforms the `nfft / 2 + 1` complex spectrum of `cx` back into the
/// `nfft` real samples of `ry`.
///
/// `cx` holds interleaved `(real, imaginary)` pairs and must have at least
/// `nfft + 2` entries, `ry` must have at least `nfft` entries.  `sign` is `1`
/// for the inverse transform; the result is *not* divided by `nfft`.
pub fn FftReal::complex_to_real(
  self : FftReal,
  sign : Int32,
  cx : Array[Float],
  ry : Array[Float],
) -> Unit {
  check_sign(sign)
  let nfft = self.nfft
  if cx.length() < nfft + 2 || ry.length() < nfft {
    abort("FftReal: array too short")
  }
  let mut i = nfft - 1
  while i >= 2 {
    ry[i] = cx[i]
    i = i - 1
  }
  ry[1] = cx[0] - cx[nfft]
  ry[0] = cx[0] + cx[nfft]
  let theta = (-sign).to_double() * two_pi / nfft.to_double()
  let wt = @math.sin(0.5 * theta)
  let c = -2.0 * wt * wt
  let s2 = @math.sin(theta)
  let mut a = 1.0 + c
  let mut b = s2
  let mut k = 2
  let mut m = nfft - 2
  while k <= m {
    let r1 = ry[k] + ry[m]
    let i1 = ry[k + 1] + ry[m + 1]
    let r2 = ry[k] - ry[m]
    let i2 = ry[k + 1] - ry[m + 1]
    let t22 = Float::from_double(b * r2.to_double() - a * i1.to_double())
    let t23 = Float::from_double(b * i1.to_double() + a * r2.to_double())
    ry[k] = r1 + t22
    ry[k + 1] = t23 + i2
    ry[m] = r1 - t22
    ry[m + 1] = t23 - i2
    let old_a = a
    a = a + (a * c - b * s2)
    b = b + (b * c + old_a * s2)
    k = k + 2
    m = m - 2
  }
  dft_inplace(sign, nfft / 2, ry)
}

///|
/// The length of the transform that an interleaved array holds.
///
/// The array holds `(real, imaginary)` pairs, so its length is `2 * n`, `n`
/// has to be a valid transform length and the name of the caller goes into
/// the message of the failure.
fn complex_length(x : Array[Float], caller : String) -> Int32 {
  let len = x.length()
  if len % 2 != 0 {
    abort(
      caller +
      ": the array holds " +
      len.to_string() +
      " floats, which is not a whole number of (real, imaginary) pairs",
    )
  }
  let n = len / 2
  if !nfft_valid(n) {
    abort(
      caller +
      ": " +
      n.to_string() +
      " is not a valid transform length, the nearest one is " +
      nfft_small(n).to_string() +
      ", see nfft_valid",
    )
  }
  n
}

///|
/// The forward discrete Fourier transform of a sequence of complex points.
///
/// This is the `fft` of FFTW.jl: unscaled, `X[k] = sum_j x[j] *
/// exp(-2*pi*i*j*k/n)`.  `x` holds `n` interleaved `(real, imaginary)` pairs,
/// so it is `2 * n` floats long, and `n` has to be a valid transform length,
/// see *Transform sizes*; the nearest valid length to a given length is
/// `nfft_small(n)`.  The result is a new array of the same length, and `x` is
/// left untouched.
///
/// The inverse is `ifft`, which is scaled so that the two undo each other.
pub fn fft(x : Array[Float]) -> Array[Float] {
  let n = complex_length(x, "fft")
  let y = zerosf(x.length())
  FftComplex::new(n).complex_to_complex(-1, x, y)
  y
}

///|
/// The inverse discrete Fourier transform of a sequence of complex points,
/// scaled by `1 / n` so that it undoes `fft`.
///
/// This is the `ifft` of FFTW.jl: the transform of the opposite direction
/// divided by the length.  The unscaled inverse - the `bfft` of FFTW.jl - is
/// what `complex_to_complex(1, ...)` of `FftComplex` computes, and it is the
/// only inverse of the Java original, which never scales.  `x` holds `n`
/// interleaved pairs and `n` has to be a valid transform length, as in `fft`.
pub fn ifft(x : Array[Float]) -> Array[Float] {
  let n = complex_length(x, "ifft")
  let y = zerosf(x.length())
  FftComplex::new(n).ifft(x, y)
  y
}

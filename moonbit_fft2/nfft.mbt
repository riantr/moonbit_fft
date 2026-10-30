///|
/// Index of the first entry of `ntable` that is greater than or equal to `n`.
fn lower_bound(n : Int32) -> Int32 {
  let mut lo = 0
  let mut hi = ntable.length()
  while lo < hi {
    let mid = (lo + hi) / 2
    if ntable[mid] < n {
      lo = mid + 1
    } else {
      hi = mid
    }
  }
  lo
}

///|
/// Returns true if `n` is a valid FFT length.
///
/// Mirrors `edu.mines.jtk.dsp.Pfacc.nfftValid`.
pub fn nfft_valid(n : Int32) -> Bool {
  let i = lower_bound(n)
  i < ntable.length() && ntable[i] == n
}

///|
/// Returns the smallest valid FFT length greater than or equal to `n`.
///
/// Mirrors `edu.mines.jtk.dsp.Pfacc.nfftSmall`, which is also what
/// `edu.mines.jtk.dsp.FftComplex.nfftSmall` computes.  The Java original
/// refuses lengths beyond the table, the port answers the largest length of
/// the table for them.
pub fn nfft_small(n : Int32) -> Int32 {
  let i = lower_bound(n)
  if i >= ntable.length() {
    ntable[ntable.length() - 1]
  } else {
    ntable[i]
  }
}

///|
/// Returns the "fast" valid FFT length for `n`: the cheapest transform
/// length that is not much larger than `n`.
///
/// Mirrors `edu.mines.jtk.dsp.Pfacc.nfftFast`, which is also what
/// `edu.mines.jtk.dsp.FftComplex.nfftFast` computes.  The Java original
/// refuses lengths beyond the table, the port answers the largest length of
/// the table for them.
pub fn nfft_fast(n : Int32) -> Int32 {
  let i = lower_bound(n)
  if i >= ntable.length() {
    return ntable[ntable.length() - 1]
  }
  let mut nfast = ntable[i]
  let nlimit = 2 * nfast
  let mut cfast = ctable[i]
  let mut j = i + 1
  while j < ntable.length() && ntable[j] < nlimit {
    if ctable[j] < cfast {
      cfast = ctable[j]
      nfast = ntable[j]
    }
    j = j + 1
  }
  nfast
}

///|
/// Returns the smallest valid FFT length greater than or equal to `n`, for
/// real valued transforms.
///
/// The real valued transforms do *not* use the complex length table.  A real
/// transform of length `n` is built on a half length complex transform, so
/// the length is twice the length of the complex transform of `(n + 1) / 2`.
///
/// Mirrors `edu.mines.jtk.dsp.FftReal.nfftSmall`.
pub fn nfft_small_real(n : Int32) -> Int32 {
  2 * nfft_small((n + 1) / 2)
}

///|
/// Returns the "fast" valid FFT length for `n`, for real valued transforms.
///
/// Like `nfft_small_real` the length is twice the length of the complex
/// transform of `(n + 1) / 2`, but the complex length is the "fast" one.
///
/// Mirrors `edu.mines.jtk.dsp.FftReal.nfftFast`.
pub fn nfft_fast_real(n : Int32) -> Int32 {
  2 * nfft_fast((n + 1) / 2)
}

///|
/// Returns true if `nfft` is a valid length for a real valued transform.
///
/// A real valued transform of length `nfft` is built on a half length complex
/// transform, so `nfft` has to be even and `nfft / 2` has to be a valid
/// complex transform length.
///
/// Mirrors the check of the `edu.mines.jtk.dsp.FftReal` constructor.
pub fn nfft_valid_real(nfft : Int32) -> Bool {
  nfft % 2 == 0 && nfft_valid(nfft / 2)
}

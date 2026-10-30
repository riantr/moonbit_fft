///|
/// The bounds of `range` along dimension `d`, falling back to the full
/// extent `0 .. fallback_max` when no range was given.
fn range_bounds(
  range : Interval?,
  d : Int32,
  fallback_max : Int32,
) -> (Int32, Int32) {
  match range {
    Some(r) => (r.min[d], r.max[d])
    None => (0, fallback_max)
  }
}

///|
/// The offset of the output in every dimension, i.e. the lower bound of the
/// range that is written.  It is zero for every dimension that is not
/// cropped.
fn range_shift(range : Interval?, dims : Array[Int32]) -> Array[Int32] {
  let shift = zeros(dims.length())
  match range {
    Some(r) => {
      let mut d = 0
      while d < dims.length() {
        shift[d] = r.min[d]
        d = d + 1
      }
    }
    None => ()
  }
  shift
}

///|
/// Iterates over all lines parallel to dimension `dim`.
///
/// The callback receives the flat offset of the line origin in the input and
/// in the output image, the coordinate of the line along every dimension
/// except `dim`, and the list of those dimensions.  The coordinate array is
/// reused between calls and must not be retained.
///
/// `shift` holds the offset of the output in every dimension except `dim`;
/// it is the lower bound of the range that is written, so that a cropped
/// range starts at the origin of the output image.
fn for_each_line(
  in_dims : Array[Int32],
  out_dims : Array[Int32],
  dim : Int32,
  shift : Array[Int32],
  f : (Int32, Int32, Array[Int32], Array[Int32]) -> Unit,
) -> Unit {
  let nd = in_dims.length()
  let in_stride = linear_strides(in_dims)
  let out_stride = linear_strides(out_dims)
  let others = zeros(if nd > 0 { nd - 1 } else { 0 })
  let mut k = 0
  let mut d = 0
  while d < nd {
    if d != dim {
      others[k] = d
      k = k + 1
    }
    d = d + 1
  }
  let sizes = zeros(others.length())
  let mut i = 0
  while i < others.length() {
    sizes[i] = in_dims[others[i]]
    i = i + 1
  }
  let coord = zeros(others.length())
  let total = total_size(sizes)
  let mut idx = 0
  while idx < total {
    let mut in_base = 0
    let mut out_base = 0
    let mut j = 0
    while j < others.length() {
      in_base = in_base + coord[j] * in_stride[others[j]]
      out_base = out_base +
        (coord[j] - shift[others[j]]) * out_stride[others[j]]
      j = j + 1
    }
    f(in_base, out_base, coord, others)
    let mut j = others.length() - 1
    while j >= 0 {
      coord[j] = coord[j] + 1
      if coord[j] < sizes[j] {
        break
      }
      coord[j] = 0
      j = j - 1
    }
    idx = idx + 1
  }
}

///|
/// Returns true if a real transform of length `real_size` produces
/// `complex_size` complex samples.
///
/// The real valued transforms use their own length table, so the check is
/// made against `nfft_small_real`/`nfft_fast_real` and not against the
/// complex lengths.
///
/// Mirrors `FFTMethods.verifyRealToComplexfftDimensions`.
pub fn verify_real_to_complex_fft_dimensions(
  real_size : Int32,
  complex_size : Int32,
) -> Bool {
  nfft_fast_real(real_size) / 2 + 1 == complex_size ||
  nfft_small_real(real_size) / 2 + 1 == complex_size
}

///|
/// Returns true if a complex transform of length `size` is supported.
///
/// Mirrors `FFTMethods.verifyComplexToComplexfftDimensions`.
pub fn verify_complex_to_complex_fft_dimensions(
  size : Int32,
  other : Int32,
) -> Bool {
  nfft_fast(size) == other || nfft_small(size) == other
}

///|
/// Computes the real-to-complex forward FFT of `input` along dimension `dim`
/// and writes the result into `output`.
///
/// `input` provides `input.dims[dim]` real samples per line, `output` holds
/// `output.dims[dim]` complex samples per line.  `range` optionally crops
/// the output; when it is `None` the whole output is written.  When `scale`
/// is true the spectrum is divided by the number of real samples.
///
/// Returns false if the two images are not compatible.
pub fn real_to_complex(
  input : RealImage,
  output : ComplexImage,
  range : Interval?,
  dim : Int32,
  scale : Bool,
) -> Bool {
  let real_size = input.dims[dim]
  let complex_size = output.dims[dim]
  if !verify_real_to_complex_fft_dimensions(real_size, complex_size) {
    return false
  }
  if !nfft_valid_real(real_size) {
    return false
  }
  let fft = FftReal::new(real_size)
  let temp_in = zerosf(real_size)
  let temp_out = zerosf(complex_size * 2)
  let in_stride = linear_strides(input.dims)
  let out_stride = linear_strides(output.dims)
  let (rmin, rmax) = range_bounds(range, dim, complex_size - 1)
  let divisor = Float::from_int(real_size)
  let shift = range_shift(range, output.dims)
  for_each_line(input.dims, output.dims, dim, shift, fn(
    in_base,
    out_base,
    coord,
    others,
  ) {
    let mut skip = false
    let mut i = 0
    while i < others.length() {
      let (lo, hi) = range_bounds(range, others[i], input.dims[others[i]] - 1)
      if coord[i] < lo || coord[i] > hi {
        skip = true
      }
      i = i + 1
    }
    if skip {
      return
    }
    let mut idx = in_base
    let mut i = 0
    while i < real_size {
      temp_in[i] = input.data[idx]
      idx = idx + in_stride[dim]
      i = i + 1
    }
    fft.real_to_complex(-1, temp_in, temp_out)
    let mut oidx = out_base
    let mut p = rmin
    while p <= rmax {
      let re = temp_out[2 * p]
      let im = temp_out[2 * p + 1]
      if scale {
        output.data[2 * oidx] = re / divisor
        output.data[2 * oidx + 1] = im / divisor
      } else {
        output.data[2 * oidx] = re
        output.data[2 * oidx + 1] = im
      }
      oidx = oidx + out_stride[dim]
      p = p + 1
    }
  })
  true
}

///|
/// Computes the complex-to-real inverse FFT of `input` along dimension `dim`
/// and writes the result into `output`.
///
/// `input` holds `input.dims[dim]` complex samples per line.  The number of
/// real samples of the transform is derived from the input, exactly like the
/// Java original: it is `2 * (input.dims[dim] - 1)`.  `output` may be
/// smaller, `range` then selects the part of the result that is written.
/// When `scale` is true the result is divided by the number of real samples.
///
/// Returns false if the two images are not compatible.
pub fn complex_to_real(
  input : ComplexImage,
  output : RealImage,
  range : Interval?,
  dim : Int32,
  scale : Bool,
) -> Bool {
  let complex_size = input.dims[dim]
  let real_size = 2 * (complex_size - 1)
  if !verify_real_to_complex_fft_dimensions(real_size, complex_size) {
    return false
  }
  if !nfft_valid_real(real_size) {
    return false
  }
  let fft = FftReal::new(real_size)
  let temp_in = zerosf(complex_size * 2)
  let temp_out = zerosf(real_size)
  let in_stride = linear_strides(input.dims)
  let out_stride = linear_strides(output.dims)
  let (rmin, rmax) = range_bounds(range, dim, real_size - 1)
  let divisor = Float::from_int(real_size)
  let shift = range_shift(range, output.dims)
  for_each_line(input.dims, output.dims, dim, shift, fn(
    in_base,
    out_base,
    coord,
    others,
  ) {
    let mut skip = false
    let mut i = 0
    while i < others.length() {
      let (lo, hi) = range_bounds(range, others[i], input.dims[others[i]] - 1)
      if coord[i] < lo || coord[i] > hi {
        skip = true
      }
      i = i + 1
    }
    if skip {
      return
    }
    let mut idx = in_base
    let mut i = 0
    while i < complex_size {
      temp_in[2 * i] = input.data[2 * idx]
      temp_in[2 * i + 1] = input.data[2 * idx + 1]
      idx = idx + in_stride[dim]
      i = i + 1
    }
    fft.complex_to_real(1, temp_in, temp_out)
    let mut oidx = out_base
    let mut p = rmin
    while p <= rmax {
      if scale {
        output.data[oidx] = temp_out[p] / divisor
      } else {
        output.data[oidx] = temp_out[p]
      }
      oidx = oidx + out_stride[dim]
      p = p + 1
    }
  })
  true
}

///|
/// Computes the complex-to-complex forward or inverse FFT of `data` along
/// dimension `dim`, in place.
///
/// When `forward` is false the inverse transform is computed and, if `scale`
/// is true, the result is divided by the number of samples per line.
///
/// Returns false if the length of the lines is not supported.
pub fn complex_to_complex(
  data : ComplexImage,
  dim : Int32,
  forward : Bool,
  scale : Bool,
) -> Bool {
  let size = data.dims[dim]
  if !verify_complex_to_complex_fft_dimensions(size, size) {
    return false
  }
  let stride = linear_strides(data.dims)[dim]
  let temp = zerosf(size * 2)
  let divisor = Float::from_int(size)
  let shift = zeros(data.dims.length())
  for_each_line(data.dims, data.dims, dim, shift, fn(
    in_base,
    out_base,
    coord,
    others,
  ) {
    let _ = coord
    let _ = others
    let mut idx = in_base
    let mut i = 0
    while i < size {
      temp[2 * i] = data.data[2 * idx]
      temp[2 * i + 1] = data.data[2 * idx + 1]
      idx = idx + stride
      i = i + 1
    }
    dft_inplace(if forward { -1 } else { 1 }, size, temp)
    let mut oidx = out_base
    let mut i = 0
    while i < size {
      let re = temp[2 * i]
      let im = temp[2 * i + 1]
      if scale {
        data.data[2 * oidx] = re / divisor
        data.data[2 * oidx + 1] = im / divisor
      } else {
        data.data[2 * oidx] = re
        data.data[2 * oidx + 1] = im
      }
      oidx = oidx + stride
      i = i + 1
    }
  })
  true
}

///|
/// Conjugates every complex value of `data` in place.
pub fn complex_conjugate(data : ComplexImage) -> Unit {
  let mut i = 1
  while i < data.data.length() {
    data.data[i] = -data.data[i]
    i = i + 2
  }
}

///|
/// Computes the interval required to pad `input` so that it reaches the
/// given dimensions, keeping the original data centred.
///
/// If the extension is not even, one extra sample is added on the high side.
///
/// Mirrors `FFTMethods.paddingIntervalCentered`.
pub fn padding_interval_centered(
  input : Interval,
  padding : Array[Int32],
) -> Interval {
  let nd = input.min.length()
  let min = zeros(nd)
  let max = zeros(nd)
  let mut d = 0
  while d < nd {
    let diff = padding[d] - input.dimension(d)
    let half = diff / 2
    min[d] = input.min[d] - half
    max[d] = input.max[d] + half
    if diff % 2 != 0 {
      max[d] = max[d] + 1
    }
    d = d + 1
  }
  { min, max, }
}

///|
/// Computes the interval of the original data inside a padded interval.
///
/// Mirrors `FFTMethods.unpaddingIntervalCentered`.
pub fn unpadding_interval_centered(
  input : Interval,
  dims : Array[Int32],
) -> Interval {
  let nd = input.min.length()
  let min = zeros(nd)
  let max = zeros(nd)
  let offset0 = (input.dimension(0) - 1) * 2
  let extra0 = offset0 - dims[0]
  min[0] = input.min[0] + extra0 / 2
  max[0] = min[0] + dims[0] - 1
  let mut d = 1
  while d < nd {
    let extra = input.dimension(d) - dims[d]
    min[d] = input.min[d] + extra / 2
    max[d] = min[d] + dims[d] - 1
    d = d + 1
  }
  { min, max, }
}

///|
/// Computes the complex and real sizes used for a real-to-complex
/// transform of an image with the given dimensions.
///
/// Mirrors `FFTMethods.dimensionsRealToComplexFast`.
pub fn dimensions_real_to_complex_fast(
  dims : Array[Int32],
  complex_sizes : Array[Int32],
  real_sizes : Array[Int32],
) -> Unit {
  real_sizes[0] = nfft_fast_real(dims[0])
  complex_sizes[0] = real_sizes[0] / 2 + 1
  let mut d = 1
  while d < dims.length() {
    complex_sizes[d] = nfft_fast(dims[d])
    real_sizes[d] = complex_sizes[d]
    d = d + 1
  }
}

///|
/// Computes the complex and real sizes used for a complex-to-real transform
/// of an image with the given dimensions.
///
/// Mirrors `FFTMethods.dimensionsComplexToRealFast`.
pub fn dimensions_complex_to_real_fast(
  dims : Array[Int32],
  complex_sizes : Array[Int32],
  real_sizes : Array[Int32],
) -> Unit {
  let real_size0 = (dims[0] - 1) * 2
  complex_sizes[0] = nfft_fast_real(real_size0) / 2 + 1
  real_sizes[0] = (complex_sizes[0] - 1) * 2
  let mut d = 1
  while d < dims.length() {
    complex_sizes[d] = nfft_fast(dims[d])
    real_sizes[d] = complex_sizes[d]
    d = d + 1
  }
}

///|
/// Computes the transform sizes used for a complex-to-complex transform of
/// an image with the given dimensions.
///
/// Mirrors `FFTMethods.dimensionsComplexToComplexFast`.
pub fn dimensions_complex_to_complex_fast(
  dims : Array[Int32],
  sizes : Array[Int32],
) -> Unit {
  let mut d = 0
  while d < dims.length() {
    sizes[d] = nfft_fast(dims[d])
    d = d + 1
  }
}

///|
/// Computes the complex and real sizes used for a real-to-complex
/// transform of an image with the given dimensions, using the smallest
/// supported lengths instead of the cheapest ones.
///
/// Mirrors `FFTMethods.dimensionsRealToComplexSmall`.
pub fn dimensions_real_to_complex_small(
  dims : Array[Int32],
  complex_sizes : Array[Int32],
  real_sizes : Array[Int32],
) -> Unit {
  real_sizes[0] = nfft_small_real(dims[0])
  complex_sizes[0] = real_sizes[0] / 2 + 1
  let mut d = 1
  while d < dims.length() {
    complex_sizes[d] = nfft_small(dims[d])
    real_sizes[d] = complex_sizes[d]
    d = d + 1
  }
}

///|
/// Computes the complex and real sizes used for a complex-to-real transform
/// of an image with the given dimensions, using the smallest supported
/// lengths instead of the cheapest ones.
///
/// Mirrors `FFTMethods.dimensionsComplexToRealSmall`.
pub fn dimensions_complex_to_real_small(
  dims : Array[Int32],
  complex_sizes : Array[Int32],
  real_sizes : Array[Int32],
) -> Unit {
  let real_size0 = (dims[0] - 1) * 2
  complex_sizes[0] = nfft_small_real(real_size0) / 2 + 1
  real_sizes[0] = (complex_sizes[0] - 1) * 2
  let mut d = 1
  while d < dims.length() {
    complex_sizes[d] = nfft_small(dims[d])
    real_sizes[d] = complex_sizes[d]
    d = d + 1
  }
}

///|
/// Computes the transform sizes used for a complex-to-complex transform of
/// an image with the given dimensions, using the smallest supported lengths
/// instead of the cheapest ones.
///
/// Mirrors `FFTMethods.dimensionsComplexToComplexSmall`.
pub fn dimensions_complex_to_complex_small(
  dims : Array[Int32],
  sizes : Array[Int32],
) -> Unit {
  let mut d = 0
  while d < dims.length() {
    sizes[d] = nfft_small(dims[d])
    d = d + 1
  }
}

///|
/// Copies `input` into an image of the given `target` dimensions, placing
/// the original data at `offset` in every dimension.  The samples that are
/// not covered by `input` are filled with `fill`.
///
/// `offset` is the lower bound of the padded interval, i.e. it is usually
/// negative; the sample at coordinate `c` of `input` ends up at coordinate
/// `c - offset` of the padded image.
fn pad_real(
  input : RealImage,
  target : Array[Int32],
  offset : Array[Int32],
  fill : Float,
) -> RealImage {
  let data = Array::Array(capacity=total_size(target))
  let mut i = 0
  while i < total_size(target) {
    data.push(fill)
    i = i + 1
  }
  let out = RealImage::from_data(target, data)
  let in_stride = linear_strides(input.dims)
  let out_stride = linear_strides(target)
  let nd = input.dims.length()
  let coord = zeros(nd)
  let total = total_size(input.dims)
  let mut idx = 0
  while idx < total {
    let mut src = 0
    let mut dst = 0
    let mut d = 0
    while d < nd {
      src = src + coord[d] * in_stride[d]
      dst = dst + (coord[d] - offset[d]) * out_stride[d]
      d = d + 1
    }
    out.data[dst] = input.data[src]
    let mut d = nd - 1
    while d >= 0 {
      coord[d] = coord[d] + 1
      if coord[d] < input.dims[d] {
        break
      }
      coord[d] = 0
      d = d - 1
    }
    idx = idx + 1
  }
  out
}

///|
/// Computes the N-dimensional forward FFT of a real valued image.
///
/// The image is zero padded to the nearest supported transform size, the
/// first dimension is transformed real-to-complex and the remaining
/// dimensions complex-to-complex.
///
/// Mirrors `FFT.realToComplex`.
pub fn fft_real_to_complex(input : RealImage) -> ComplexImage {
  fft_real_to_complex_with_fill(input, Float::from_double(0.0))
}

///|
/// Computes the N-dimensional forward FFT of a real valued image, filling the
/// padding with `fill` instead of with zero.
///
/// The Java original extends the input with an out of bounds strategy before
/// it pads it.  The strategy of the default overload
/// `FFT.realToComplex(input, factory)` is a constant of zero, the strategy of
/// `FFT.realToComplex(input, oobs, factory)` is the one of the caller.  Only
/// the constant strategy is expressible in the data model of the port, the
/// others (mirror, wrap, ...) would need the coordinate based access of
/// `net.imglib2.RandomAccessible`.
///
/// Mirrors `FFT.realToComplex` with a constant out of bounds factory.
pub fn fft_real_to_complex_with_fill(
  input : RealImage,
  fill : Float,
) -> ComplexImage {
  let nd = input.dims.length()
  let complex_sizes = zeros(nd)
  let real_sizes = zeros(nd)
  dimensions_real_to_complex_fast(input.dims, complex_sizes, real_sizes)
  let output = ComplexImage::new(complex_sizes)
  let padded_input = if dimensions_equal(input.dims, real_sizes) {
    input
  } else {
    let interval = padding_interval_centered(
      Interval::new(input.dims),
      real_sizes,
    )
    pad_real(input, real_sizes, interval.min, fill)
  }
  let _ = real_to_complex(padded_input, output, None, 0, false)
  let mut d = 1
  while d < nd {
    let _ = complex_to_complex(output, d, true, false)
    d = d + 1
  }
  output
}

///|
/// Computes the N-dimensional forward complex-to-complex FFT of `data` in
/// place.
///
/// Mirrors `FFT.complexToComplexForward`.
pub fn fft_complex_to_complex_forward(data : ComplexImage) -> Unit {
  let mut d = 0
  while d < data.dims.length() {
    let _ = complex_to_complex(data, d, true, false)
    d = d + 1
  }
}

///|
/// Computes the N-dimensional inverse complex-to-complex FFT of `data` in
/// place.
///
/// The result is scaled, so that a forward followed by an inverse transform
/// reproduces the original data.
///
/// Mirrors `FFT.complexToComplexInverse`.
pub fn fft_complex_to_complex_inverse(data : ComplexImage) -> Unit {
  let mut d = 0
  while d < data.dims.length() {
    let _ = complex_to_complex(data, d, false, true)
    d = d + 1
  }
}

///|
/// Returns true if `dims` can be handled by `fft_complex_to_real`.
///
/// The original implementation reads the input through a view of the
/// *unextended* input image.  When the extent of the result differs from the
/// extent of the input, that view reaches outside the image and the original
/// fails with an `IndexOutOfBoundsException`.  This predicate tells whether
/// the given extent is one of the supported ones.
pub fn fft_complex_to_real_supported(dims : Array[Int32]) -> Bool {
  let nd = dims.length()
  let complex_sizes = zeros(nd)
  let real_sizes = zeros(nd)
  dimensions_complex_to_real_fast(dims, complex_sizes, real_sizes)
  dimensions_equal(dims, complex_sizes)
}

///|
/// Computes the N-dimensional inverse FFT of a complex valued image and
/// returns the real valued result.
///
/// The complex image is zero padded to the nearest supported transform size,
/// the remaining dimensions are transformed complex-to-complex and the first
/// dimension complex-to-real.
///
/// The original implementation reads the padded input through a view of the
/// input image itself, which is not extended.  As soon as the padded extent
/// differs from the extent of the input, the original reads outside the
/// image and fails with an `IndexOutOfBoundsException`.  The port refuses
/// those extents as well, `fft_complex_to_real_supported` tells whether a
/// given extent is supported.
///
/// Mirrors `FFT.complexToReal`.
pub fn fft_complex_to_real(input : ComplexImage) -> RealImage {
  let nd = input.dims.length()
  let complex_sizes = zeros(nd)
  let real_sizes = zeros(nd)
  dimensions_complex_to_real_fast(input.dims, complex_sizes, real_sizes)
  if !dimensions_equal(input.dims, complex_sizes) {
    abort(
      "FFT.complexToReal: the original implementation reads outside the " +
      "input image for this extent",
    )
  }
  let mut d = nd - 1
  while d > 0 {
    let _ = complex_to_complex(input, d, false, true)
    d = d - 1
  }
  let output = RealImage::new(real_sizes)
  let _ = complex_to_real(input, output, None, 0, true)
  output
}

///|
/// Computes the N-dimensional inverse FFT of a complex valued image and
/// returns the real valued result.
///
/// The complex image is *not* padded, the caller has to supply a complex
/// image whose first dimension matches the wanted number of real samples.
///
/// Mirrors `FFT.complexToReal`.
pub fn fft_complex_to_real_inplace(
  input : ComplexImage,
  output : RealImage,
) -> Unit {
  let nd = input.dims.length()
  let mut d = 1
  while d < nd {
    let _ = complex_to_complex(input, d, false, true)
    d = d + 1
  }
  let _ = complex_to_real(input, output, None, 0, true)
}

///|
/// Computes the N-dimensional inverse FFT of a complex valued image and
/// returns the real valued result cropped to `output_dims`.
///
/// Unlike `fft_complex_to_real` the complex image is *not* padded, so the
/// caller has to supply a complex image whose first dimension matches
/// `output_dims`.
///
/// Mirrors `FFT.complexToRealUnpad`.
pub fn fft_complex_to_real_unpad(
  input : ComplexImage,
  output_dims : Array[Int32],
) -> RealImage {
  let nd = input.dims.length()
  let mut d = 1
  while d < nd {
    let _ = complex_to_complex(input, d, false, true)
    d = d + 1
  }
  let range = unpadding_interval_centered(
    Interval::new(input.dims),
    output_dims,
  )
  let output = RealImage::new(output_dims)
  let _ = complex_to_real(input, output, Some(range), 0, true)
  output
}

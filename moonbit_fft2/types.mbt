///|
/// Creates an array of `n` zeros.
fn zeros(n : Int32) -> Array[Int32] {
  let a = Array::Array(capacity=n)
  let mut i = 0
  while i < n {
    a.push(0)
    i = i + 1
  }
  a
}

///|
/// Creates an array of `n` zero floats.
fn zerosf(n : Int32) -> Array[Float] {
  let a = Array::Array(capacity=n)
  let zero = Float::from_int(0)
  let mut i = 0
  while i < n {
    a.push(zero)
    i = i + 1
  }
  a
}

///|
/// A real-valued N-dimensional image.
///
/// `data` holds the samples in the linear order of `net.imglib2`, i.e. the
/// first dimension is contiguous, `dims` holds the extent of every dimension.
/// The origin of every image is `(0, 0, ...)`.
pub struct RealImage {
  dims : Array[Int32]
  data : Array[Float]
}

///|
/// A complex-valued N-dimensional image.
///
/// `data` holds interleaved `(real, imaginary)` float pairs in the linear
/// order of `net.imglib2`, i.e. the first dimension is contiguous, `dims` holds
/// the extent of every dimension.  The origin of every image is `(0, 0, ...)`.
pub struct ComplexImage {
  dims : Array[Int32]
  data : Array[Float]
}

///|
/// An axis aligned range of positions, one `(min, max)` pair per dimension.
pub struct Interval {
  min : Array[Int32]
  max : Array[Int32]
}

///|
/// Number of elements described by `dims`.
pub fn total_size(dims : Array[Int32]) -> Int32 {
  let mut n = 1
  for d in dims {
    n = n * d
  }
  n
}

///|
/// Strides of the linear index of an image with the given extent.
///
/// The layout follows `net.imglib2`: the *first* dimension is contiguous, the
/// linear index of the element at position `p` is
/// `p[0] + p[1] * dims[0] + p[2] * dims[0] * dims[1] + ...`.
pub fn linear_strides(dims : Array[Int32]) -> Array[Int32] {
  let nd = dims.length()
  let strides = zeros(nd)
  if nd > 0 {
    strides[0] = 1
    let mut d = 1
    while d < nd {
      strides[d] = strides[d - 1] * dims[d - 1]
      d = d + 1
    }
  }
  strides
}

///|
/// Creates a zero filled real image with the given extent.
pub fn RealImage::new(dims : Array[Int32]) -> RealImage {
  { dims: dims.copy(), data: zerosf(total_size(dims)), }
}

///|
/// Creates a real image backed by `data`, which must hold
/// `total_size(dims)` samples in linear order.
pub fn RealImage::from_data(
  dims : Array[Int32],
  data : Array[Float],
) -> RealImage {
  { dims: dims.copy(), data, }
}

///|
/// Creates a zero filled complex image with the given extent.
pub fn ComplexImage::new(dims : Array[Int32]) -> ComplexImage {
  { dims: dims.copy(), data: zerosf(total_size(dims) * 2), }
}

///|
/// Creates a complex image backed by `data`, which must hold
/// `2 * total_size(dims)` interleaved `(real, imaginary)` samples in the
/// linear order of `net.imglib2`.
pub fn ComplexImage::from_data(
  dims : Array[Int32],
  data : Array[Float],
) -> ComplexImage {
  { dims: dims.copy(), data, }
}

///|
/// The real parts of a complex image, in linear order.
pub fn ComplexImage::real_part(self : ComplexImage) -> Array[Float] {
  let n = self.data.length() / 2
  let out = zerosf(n)
  let mut i = 0
  while i < n {
    out[i] = self.data[2 * i]
    i = i + 1
  }
  out
}

///|
/// The imaginary parts of a complex image, in linear order.
pub fn ComplexImage::imag_part(self : ComplexImage) -> Array[Float] {
  let n = self.data.length() / 2
  let out = zerosf(n)
  let mut i = 0
  while i < n {
    out[i] = self.data[2 * i + 1]
    i = i + 1
  }
  out
}

///|
/// Creates the interval covering the whole extent of an image with the
/// given dimensions, i.e. `[0, dims[d] - 1]` for every dimension `d`.
pub fn Interval::new(dims : Array[Int32]) -> Interval {
  let nd = dims.length()
  let min = zeros(nd)
  let max = zeros(nd)
  let mut d = 0
  while d < nd {
    max[d] = dims[d] - 1
    d = d + 1
  }
  { min, max, }
}

///|
/// The extent of the interval along dimension `d`.
pub fn Interval::dimension(self : Interval, d : Int32) -> Int32 {
  self.max[d] - self.min[d] + 1
}

///|
/// The extents of the interval, one per dimension.
pub fn Interval::dims(self : Interval) -> Array[Int32] {
  let nd = self.min.length()
  let out = zeros(nd)
  let mut d = 0
  while d < nd {
    out[d] = self.dimension(d)
    d = d + 1
  }
  out
}

///|
/// Returns true if the two extent arrays describe the same shape.
pub fn dimensions_equal(a : Array[Int32], b : Array[Int32]) -> Bool {
  if a.length() != b.length() {
    return false
  }
  let mut d = 0
  while d < a.length() {
    if a[d] != b[d] {
      return false
    }
    d = d + 1
  }
  true
}

///|
/// Returns true if the interval has exactly the given extent in every
/// dimension.
pub fn dimensions_equal_interval(
  interval : Interval,
  dims : Array[Int32],
) -> Bool {
  if interval.min.length() != dims.length() {
    return false
  }
  let mut d = 0
  while d < dims.length() {
    if interval.dimension(d) != dims[d] {
      return false
    }
    d = d + 1
  }
  true
}

///|
/// The window functions that a transform is usually fed with.
///
/// They are **not** part of the port of `imglib2-fft2`, and the Java original
/// has no window at all: a caller multiplies its samples by one of these before
/// the transform, which is what every package of the ecosystem does too - none
/// of them puts a window in the signature of a transform.
///
/// The coefficients are those of `numpy` for the five closed forms and of
/// `numpy.kaiser` for the Kaiser window, and `tools/gen_windows.py` holds them
/// to it.  They are `Double` and not `Float`, which is the convention of the
/// ecosystem; `to_floats` bridges to the `Float` samples that the transforms of
/// this module take.
let two_pi : Double = 6.283185307179586

///|
/// The coefficients of the flat top window of MATLAB and SciPy.
let flattop_a : Array[Double] = [
  0.21557895, 0.41663158, 0.277263158, 0.083578947, 0.006947368,
]

///|
/// A window of one point: the only sensible answer is a weight of one.
///
/// A window of no points at all is empty, and a symmetric window of two points
/// would divide by `n - 1`, which is why every function of this file starts
/// here.
fn degenerate(n : Int32) -> Array[Double]? {
  if n <= 0 {
    Some(Array::Array(capacity=0))
  } else if n == 1 {
    let one : Array[Double] = []
    one.push(1.0)
    Some(one)
  } else {
    None
  }
}

///|
/// The denominator of the argument of a window: `n - 1` for the symmetric
/// convention of `numpy`, `n` for the periodic one, which is the convention
/// that keeps a window free of the discontinuity at the wrap of a transform.
fn span_of(n : Int32, periodic : Bool) -> Double {
  if periodic {
    n.to_double()
  } else {
    (n - 1).to_double()
  }
}

///|
/// The Hann window, `0.5 - 0.5 * cos(2 * pi * i / span)`.
///
/// `numpy.hanning` is the symmetric one, which is the default here; pass
/// `periodic=true` for the window that belongs to a transform, where the
/// symmetric one leaves a step between the last sample and the first.
pub fn hanning(n : Int32, periodic~ : Bool = false) -> Array[Double] {
  match degenerate(n) {
    Some(answer) => answer
    None => {
      let span = span_of(n, periodic)
      let out : Array[Double] = Array::Array(capacity=n)
      let mut i = 0
      while i < n {
        out.push(0.5 - 0.5 * @math.cos(two_pi * i.to_double() / span))
        i = i + 1
      }
      out
    }
  }
}

///|
/// The Hamming window, `0.54 - 0.46 * cos(2 * pi * i / span)`.
pub fn hamming(n : Int32, periodic~ : Bool = false) -> Array[Double] {
  match degenerate(n) {
    Some(answer) => answer
    None => {
      let span = span_of(n, periodic)
      let out : Array[Double] = Array::Array(capacity=n)
      let mut i = 0
      while i < n {
        out.push(0.54 - 0.46 * @math.cos(two_pi * i.to_double() / span))
        i = i + 1
      }
      out
    }
  }
}

///|
/// The Blackman window,
/// `0.42 - 0.5 * cos(2 * pi * i / span) + 0.08 * cos(4 * pi * i / span)`.
pub fn blackman(n : Int32, periodic~ : Bool = false) -> Array[Double] {
  match degenerate(n) {
    Some(answer) => answer
    None => {
      let span = span_of(n, periodic)
      let out : Array[Double] = Array::Array(capacity=n)
      let mut i = 0
      while i < n {
        let t = two_pi * i.to_double() / span
        out.push(0.42 - 0.5 * @math.cos(t) + 0.08 * @math.cos(2.0 * t))
        i = i + 1
      }
      out
    }
  }
}

///|
/// The Bartlett window, the triangle `1 - |2 * i / span - 1|`.
pub fn bartlett(n : Int32, periodic~ : Bool = false) -> Array[Double] {
  match degenerate(n) {
    Some(answer) => answer
    None => {
      let span = span_of(n, periodic)
      let out : Array[Double] = Array::Array(capacity=n)
      let mut i = 0
      while i < n {
        out.push(1.0 - (2.0 * i.to_double() / span - 1.0).abs())
        i = i + 1
      }
      out
    }
  }
}

///|
/// The flat top window, the five term cosine window of MATLAB and SciPy.
///
/// It is the window to reach for when the **amplitude** of a line of the
/// spectrum matters more than its width, because its main lobe is flat.
pub fn flattop(n : Int32, periodic~ : Bool = false) -> Array[Double] {
  match degenerate(n) {
    Some(answer) => answer
    None => {
      let span = span_of(n, periodic)
      let out : Array[Double] = Array::Array(capacity=n)
      let mut i = 0
      while i < n {
        let t = two_pi * i.to_double() / span
        let mut value = flattop_a[0]
        let mut k = 1
        let mut sign = -1.0
        while k < 5 {
          value = value + sign * flattop_a[k] * @math.cos(k.to_double() * t)
          sign = -sign
          k = k + 1
        }
        out.push(value)
        i = i + 1
      }
      out
    }
  }
}

///|
/// The modified Bessel function of the first kind, of order zero.
///
/// The series `sum over k of (x / 2) ** (2k) / (k!) ** 2`, summed until a term
/// stops changing the sum: enough for the argument of a Kaiser window, which is
/// what it is here for.
pub fn bessel_i0(x : Double) -> Double {
  let half = x * 0.5
  let mut term = 1.0
  let mut sum = 1.0
  let mut k = 1
  while k <= 300 {
    let step = half / k.to_double()
    term = term * step * step
    sum = sum + term
    if term <= sum * 1.0e-18 {
      return sum
    }
    k = k + 1
  }
  sum
}

///|
/// The Kaiser window of the shape `beta`, `i0(beta * sqrt(1 - r * r)) / i0(beta)`
/// with `r` the position mapped to `-1 .. 1`.
///
/// `beta = 5.0` is close to a Hamming window, `8.6` is the usual choice for a
/// transform, and larger values trade a wider main lobe for a lower sidelobe.
pub fn kaiser(
  n : Int32,
  beta : Double,
  periodic~ : Bool = false,
) -> Array[Double] {
  match degenerate(n) {
    Some(answer) => answer
    None => {
      let span = span_of(n, periodic)
      let denominator = bessel_i0(beta)
      let out : Array[Double] = Array::Array(capacity=n)
      let mut i = 0
      while i < n {
        let r = 2.0 * i.to_double() / span - 1.0
        let mut inside = 1.0 - r * r
        // The ends of the window sit at zero, and the rounding of `r` may put
        // them a hair on the wrong side of it.
        if inside < 0.0 {
          inside = 0.0
        }
        out.push(bessel_i0(beta * @math.pow(inside, 0.5)) / denominator)
        i = i + 1
      }
      out
    }
  }
}

///|
/// Multiplies `data` by a window, in place, over the shorter of the two.
pub fn apply_window(data : Array[Double], window : Array[Double]) -> Unit {
  let n = if data.length() < window.length() {
    data.length()
  } else {
    window.length()
  }
  let mut i = 0
  while i < n {
    data[i] = data[i] * window[i]
    i = i + 1
  }
}

///|
/// The same window in the single precision of the transforms of this module.
pub fn to_floats(window : Array[Double]) -> Array[Float] {
  let out : Array[Float] = Array::Array(capacity=window.length())
  let mut i = 0
  while i < window.length() {
    out.push(Float::from_double(window[i]))
    i = i + 1
  }
  out
}

///|
/// Multiplies single precision samples by a window, in place, over the shorter
/// of the two.
pub fn apply_window_floats(data : Array[Float], window : Array[Double]) -> Unit {
  let n = if data.length() < window.length() {
    data.length()
  } else {
    window.length()
  }
  let mut i = 0
  while i < n {
    data[i] = Float::from_double(data[i].to_double() * window[i])
    i = i + 1
  }
}

///|
/// The separable two dimensional window `wx * wy`, row major, which is what an
/// image is multiplied by before a transform of both of its dimensions.
///
/// None of the packages of the ecosystem has one: their windows are one
/// dimensional, and an image is the thing this module has that they do not.
pub fn window_2d(
  rows : Int32,
  cols : Int32,
  wx : Array[Double],
  wy : Array[Double],
) -> Array[Double] {
  let out : Array[Double] = Array::Array(capacity=rows * cols)
  let mut r = 0
  while r < rows {
    let mut c = 0
    while c < cols {
      out.push(wx[r] * wy[c])
      c = c + 1
    }
    r = r + 1
  }
  out
}

///|
/// The helpers of the window package, which have no external reference: the
/// coefficients of the windows are held to `numpy` by `window_wbtest.mbt`, and
/// what is left is the element-wise application and the separable window of an
/// image, which are ours and are checked here.

///|
test "a window is applied over the shorter of the two" {
  let data : Array[Double] = [1.0, 2.0, 3.0]
  let window : Array[Double] = [2.0, 3.0]
  apply_window(data, window)
  assert_true(data[0] == 2.0, msg="data[0] is \{data[0]}")
  assert_true(data[1] == 6.0, msg="data[1] is \{data[1]}")
  // The sample past the window is left alone instead of being zeroed.
  assert_true(data[2] == 3.0, msg="data[2] is \{data[2]}")
}

///|
test "the coefficients reach the single precision of a transform" {
  let window = hanning(5)
  let floats = to_floats(window)
  assert_true(floats.length() == 5, msg="\{floats.length()} coefficients")
  let mut i = 0
  while i < 5 {
    // The coefficient is rounded to single precision on purpose, so the single
    // precision value is the thing to compare with.
    assert_true(
      floats[i] == Float::from_double(window[i]),
      msg="coefficient \{i}: \{floats[i]} against \{window[i]}",
    )
    i = i + 1
  }
  let data : Array[Float] = [1.0, 1.0, 1.0]
  apply_window_floats(data, window)
  assert_true(data[0].to_double() == 0.0, msg="data[0] is \{data[0]}")
  assert_true(data[1].to_double() == 0.5, msg="data[1] is \{data[1]}")
  assert_true(data[2].to_double() == 1.0, msg="data[2] is \{data[2]}")
}

///|
test "the window of an image is the product of its two dimensions" {
  let wx = hanning(3)
  let wy = hamming(4)
  let w = window_2d(3, 4, wx, wy)
  assert_true(w.length() == 12, msg="\{w.length()} coefficients")
  let mut r = 0
  while r < 3 {
    let mut c = 0
    while c < 4 {
      let expected = wx[r] * wy[c]
      assert_true(
        w[r * 4 + c] == expected,
        msg="at \{r}, \{c}: \{w[r * 4 + c]} against \{expected}",
      )
      c = c + 1
    }
    r = r + 1
  }
}

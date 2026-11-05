///|
/// Tests of the plan handle of `plan.mbt`.
///
/// A plan has to be the same transform as `FftComplex` of the same length, it
/// has to stay out of the cache of the module, and it has to be a workspace
/// that the caller owns: the plan may carry nothing from one transform into
/// the next.  That is the whole contract on which a caller relies when it
/// keeps a plan instead of calling `FftComplex`.

///|
/// The interleaved single precision samples of a deterministic test signal of
/// `n` points.
fn plan_samples(n : Int32) -> Array[Float] {
  let cx = Array::Array(capacity=2 * n)
  let mut j = 0
  while j < n {
    // The real and the imaginary part are different pseudo random sequences.
    let re = (j * 37 % 41).to_double() / 20.0 - 0.5
    let im = (j * 53 % 47).to_double() / 30.0 - 0.75
    cx.push(Float::from_double(re))
    cx.push(Float::from_double(im))
    j = j + 1
  }
  cx
}

///|
/// The `2 * n` samples of a spectrum, compared bit by bit with the ones of
/// `want`.
fn assert_same_samples(
  got : Array[Float],
  want : Array[Float],
  n : Int32,
  what : String,
) -> Unit raise {
  let mut j = 0
  while j < 2 * n {
    assert_true(
      got[j] == want[j],
      msg="\{what}: sample \{j} is \{got[j]}, it has to be \{want[j]}",
    )
    j = j + 1
  }
}

///|
/// A plan of a length has to be the transform that `FftComplex` of the same
/// length computes, for the forward direction and for every length.
test "a plan transforms as FftComplex of the same length" {
  let lengths : Array[Int32] = [2, 4, 12, 60, 105, 240, 360]
  let mut i = 0
  while i < lengths.length() {
    let n = lengths[i]
    let cx = plan_samples(n)
    let want = Array::make(2 * n, Float::from_double(0.0))
    FftComplex::new(n).complex_to_complex(-1, cx, want)
    let got = Array::make(2 * n, Float::from_double(0.0))
    FftPlan::create(n).complex_to_complex(-1, cx, got)
    assert_same_samples(got, want, n, "the forward transform of \{n} points")
    i = i + 1
  }
}

///|
/// The unnormalised inverse transform of a plan has to be the one of
/// `FftComplex` of the same length.
test "the inverse transform of a plan is the one of FftComplex" {
  let lengths : Array[Int32] = [4, 60, 105]
  let mut i = 0
  while i < lengths.length() {
    let n = lengths[i]
    let cx = plan_samples(n)
    let want = Array::make(2 * n, Float::from_double(0.0))
    FftComplex::new(n).complex_to_complex(1, cx, want)
    let got = Array::make(2 * n, Float::from_double(0.0))
    FftPlan::create(n).complex_to_complex(1, cx, got)
    assert_same_samples(got, want, n, "the inverse transform of \{n} points")
    i = i + 1
  }
}

///|
/// The entry that carries its own buffers has to compute the transform of the
/// same samples, in both directions.
///
/// The buffers are filled with the samples **after** the rounding to single
/// precision, so that the two entries see the same numbers and the comparison
/// is exact rather than approximate.
test "the buffers of a plan are the transform of the same samples" {
  let lengths : Array[Int32] = [4, 60, 105]
  let mut i = 0
  while i < lengths.length() {
    let n = lengths[i]
    let cx = plan_samples(n)
    let mut sign = -1
    while sign <= 1 {
      let want = Array::make(2 * n, Float::from_double(0.0))
      FftComplex::new(n).complex_to_complex(sign, cx, want)
      let re = Array::Array(capacity=n)
      let im = Array::Array(capacity=n)
      let mut j = 0
      while j < n {
        re.push(cx[2 * j].to_double())
        im.push(cx[2 * j + 1].to_double())
        j = j + 1
      }
      FftPlan::create(n).complex_to_complex_buffers(sign, re, im)
      j = 0
      while j < n {
        assert_true(
          Float::from_double(re[j]) == want[2 * j],
          msg="the real part of the sample \{j} of \{n} points, sign \{sign}, is \{Float::from_double(re[j])}, it has to be \{want[2 * j]}",
        )
        assert_true(
          Float::from_double(im[j]) == want[2 * j + 1],
          msg="the imaginary part of the sample \{j} of \{n} points, sign \{sign}, is \{Float::from_double(im[j])}, it has to be \{want[2 * j + 1]}",
        )
        j = j + 1
      }
      sign = sign + 2
    }
    i = i + 1
  }
}

///|
/// The normalised inverse transform of a plan has to divide by the length, the
/// same way `FftComplex::ifft` does.
test "the normalised inverse transform of a plan is the one of FftComplex" {
  let lengths : Array[Int32] = [4, 60, 105]
  let mut i = 0
  while i < lengths.length() {
    let n = lengths[i]
    let cx = plan_samples(n)
    let want = Array::make(2 * n, Float::from_double(0.0))
    FftComplex::new(n).ifft(cx, want)
    let got = Array::make(2 * n, Float::from_double(0.0))
    FftPlan::create(n).ifft(cx, got)
    assert_same_samples(got, want, n, "the normalised inverse of \{n} points")
    i = i + 1
  }
}

///|
/// A plan that the caller builds is not entered into the cache of the module:
/// the cache is the memory of `FftComplex`, and a caller that keeps its own
/// plan keeps its memory too.
test "a plan is not entered into the cache" {
  let n : Int32 = 60
  // The cache is emptied first, so that the test does not depend on what the
  // tests before it have built.
  let mut i = 0
  while i < plan_cache.length() {
    plan_cache[i] = None
    i = i + 1
  }
  plan_cache_cost[0] = 0
  let plan = FftPlan::create(n)
  let cx = plan_samples(n)
  let cy = Array::make(2 * n, Float::from_double(0.0))
  plan.complex_to_complex(-1, cx, cy)
  assert_true(
    plan_cache_cost[0] == 0,
    msg="a plan of its own must not charge the cache of the module, the cache holds \{plan_cache_cost[0]} elements",
  )
  // The cache builds a plan of its own when it is asked for one, and that is
  // the one that pays.
  let _ = plan_for(n)
  assert_true(
    plan_cache_cost[0] == n,
    msg="the cache of the module is the one that pays for a cached plan, it holds \{plan_cache_cost[0]} elements",
  )
}

///|
/// The plan may carry nothing from one transform into the next: the same
/// input has to give the same spectrum twice.
test "a plan carries nothing from one transform to the next" {
  let n : Int32 = 60
  let plan = FftPlan::create(n)
  let cx = plan_samples(n)
  let first = Array::make(2 * n, Float::from_double(0.0))
  plan.complex_to_complex(-1, cx, first)
  // A transform of another length in between, through the same module.
  let other = plan_samples(105)
  let other_out = Array::make(2 * 105, Float::from_double(0.0))
  FftComplex::new(105).complex_to_complex(-1, other, other_out)
  let second = Array::make(2 * n, Float::from_double(0.0))
  plan.complex_to_complex(-1, cx, second)
  assert_same_samples(
    second, first, n, "the second transform of the same input",
  )
}

///|
/// Two plans of the same length are two workspaces: a transform through one of
/// them may not reach the other.
test "two plans of the same length are independent" {
  let n : Int32 = 60
  let a = FftPlan::create(n)
  let b = FftPlan::create(n)
  let cx = plan_samples(n)
  let want = Array::make(2 * n, Float::from_double(0.0))
  FftComplex::new(n).complex_to_complex(-1, cx, want)
  let got_a = Array::make(2 * n, Float::from_double(0.0))
  let got_b = Array::make(2 * n, Float::from_double(0.0))
  // The transforms are interleaved, so a workspace that leaked into the other
  // plan would show in the second result.
  a.complex_to_complex(-1, cx, got_a)
  b.complex_to_complex(-1, cx, got_b)
  a.complex_to_complex(-1, cx, got_a)
  assert_same_samples(got_a, want, n, "the transform through the first plan")
  assert_same_samples(got_b, want, n, "the transform through the second plan")
}

///|
/// The plan reports the length it was built for.
test "a plan reports the length it was built for" {
  assert_true(
    FftPlan::create(4).nfft() == 4,
    msg="the length of the plan of 4 is \{FftPlan::create(4).nfft()}",
  )
  assert_true(
    FftPlan::create(60).nfft() == 60,
    msg="the length of the plan of 60 is \{FftPlan::create(60).nfft()}",
  )
}

///|
/// The mixed radix discrete Fourier transform.
///
/// The original Java implementation uses the Good-Thomas prime factor
/// algorithm of `edu.mines.jtk.dsp.Pfacc`: the length is split into its prime
/// factors and every factor selects a small kernel.  That is `O(n log n)` for
/// every valid length.
///
/// This module implements the same idea.  The length is split into factors
/// that are pairwise coprime, and the factors are applied as the stages of a
/// transform.  Because the factors are coprime, the stages need no twiddle
/// factor at all: the twist of the original, which the Java code absorbs into
/// the roots of unity of its small transforms, is the only thing that is left.
///
/// The valid lengths of the original are built from the primes 2, 3, 5, 7, 11
/// and 13, so a radix of at most 16 is enough and every valid length is
/// covered.
///
/// The name of the file is the one of the first version of this module, which
/// held a mixed radix Cooley-Tukey transform; the algorithm in it is the
/// prime factor one.

///|
/// The number of transform elements that are kept in the plan cache at the
/// same time.
///
/// A plan holds the factors of one length and the work buffers.  Every element
/// of a length costs two doubles of work buffer, so a plan costs about sixteen
/// bytes per element of its length: the budget of two million elements holds
/// about thirty megabytes of plans.
///
/// The 240 valid lengths of the original add up to 3.2 million elements, so
/// the budget holds 237 of them.  A program that uses more lengths than that
/// makes the cache drop its plans when the budget is exceeded; the plans are
/// then rebuilt, which costs about 2 % of a transform of the same length.
///
/// The budget is a limit of the memory the library holds, not a limit of the
/// work: a transform of a length that is not cached is still correct, it
/// only pays for building its plan.
let plan_cache_budget : Int32 = 2000000

///|
/// A transform plan: everything that depends on the length of the transform
/// but not on its direction.
///
/// The plan holds the factors of the length, the twist of every stage and the
/// work buffers of the transform.  The roots of unity of the stages are
/// literals in the butterflies of `kernels.mbt`, so the plan does not hold
/// them.
///
/// A plan is **immutable once it is built**: the transform reads `radix`, `m`
/// and `kfac`, and it writes nothing but the buffers it is given.  That is
/// what makes a plan the unit of concurrency the module can offer, and it is
/// the reason a plan can be kept by a caller without the cache of the module
/// (see `plan.mbt`): one plan can serve any number of callers that bring
/// their own buffers.  The buffers of the plan itself are the workspace of
/// the convenience entry `FftPlan::complex_to_complex`, so two calls that
/// overlap on the same plan must not both take that path.
///
/// The runtime of MoonBit has no OS threads yet (`core/async` has coroutines,
/// which are cooperative and single threaded), so this contract is
/// structural: it says what the module does not share, not what has been
/// measured under two threads.
pub struct FftPlan {
  /// The length of the transform.
  priv n : Int32
  /// The radix of every stage, the stages are applied from the largest radix
  /// to the smallest one.
  priv radix : Array[Int32]
  /// The number of butterflies of every stage, it is the length of the
  /// transform divided by the radix of the stage.
  priv m : Array[Int32]
  /// The inverse of the number of butterflies modulo the radix, of every
  /// stage.  It is the twist of the roots of unity of the stage.
  priv kfac : Array[Int32]
  /// The real parts of the working buffer of the transform.
  priv buf_re : Array[Double]
  /// The imaginary parts of the working buffer of the transform.
  priv buf_im : Array[Double]
}

///|
/// The factors of the length, in the order the original applies them.
///
/// The factors are pairwise coprime, which is what lets the transform run
/// without twiddle factors.  A prime power of the length becomes a factor of
/// its own, so the length 32760 becomes `13 * 9 * 8 * 7 * 5` and not
/// `13 * 7 * 5 * 3 * 3 * 2 * 2 * 2`.
///
/// The order is the one of the original, from the largest factor to the
/// smallest one.
fn coprime_factors(n : Int32) -> Array[Int32] {
  let order : Array[Int32] = [16, 13, 11, 9, 8, 7, 5, 4, 3, 2]
  let factors = Array::Array(capacity=10)
  let mut left = n
  let mut i = 0
  while i < order.length() {
    let f = order[i]
    if left % f == 0 {
      left = left / f
      factors.push(f)
    }
    i = i + 1
  }
  if left != 1 {
    abort("the transform length " + n.to_string() + " is not supported")
  }
  factors
}

///|
/// The inverse of `m` modulo `r`.
///
/// The factors of a length are pairwise coprime, so the inverse exists.  The
/// radices are small, so the inverse is looked for instead of computed.
fn mod_inverse(m : Int32, r : Int32) -> Int32 {
  let mut k = 1
  let mut found = 0
  while k < r && found == 0 {
    if k * m % r == 1 {
      found = k
    }
    k = k + 1
  }
  if found == 0 {
    abort("the factors of the length are not coprime")
  }
  found
}

///|
/// Builds the transform plan of a length.
fn build_plan(n : Int32) -> FftPlan {
  let radix = coprime_factors(n)
  let k = radix.length()
  let m = Array::Array(capacity=k)
  let kfac = Array::Array(capacity=k)
  let mut j = 0
  while j < k {
    let r = radix[j]
    let mi = n / r
    m.push(mi)
    kfac.push(mod_inverse(mi, r))
    j = j + 1
  }
  // The working buffer of the transform is part of the plan, so that a
  // transform does not allocate.
  let buf_re = zerosd(n)
  let buf_im = zerosd(n)
  { n, radix, m, kfac, buf_re, buf_im, }
}

///|
/// The cached transform plans, indexed by the position of the length in the
/// table of the valid lengths.
let plan_cache : Array[FftPlan?] = {
  let a = Array::Array(capacity=ntable.length())
  let mut i = 0
  while i < ntable.length() {
    a.push(None)
    i = i + 1
  }
  a
}

///|
/// The number of transform elements that the cached plans hold.
let plan_cache_cost : Array[Int32] = [0]

///|
/// Returns the transform plan of a length, building it if it is not cached
/// yet.
///
/// The plan of a length never changes, so it is built once and reused.  This
/// matters because the roots of unity of a length are worth as much as the
/// transform itself.
fn plan_for(n : Int32) -> FftPlan {
  let index = lower_bound(n)
  if index >= ntable.length() || ntable[index] != n {
    abort("the transform length " + n.to_string() + " is not supported")
  }
  match plan_cache[index] {
    Some(plan) => plan
    None => {
      let plan = build_plan(n)
      if plan_cache_cost[0] + n > plan_cache_budget {
        let mut i = 0
        while i < plan_cache.length() {
          plan_cache[i] = None
          i = i + 1
        }
        plan_cache_cost[0] = 0
      }
      plan_cache[index] = Some(plan)
      plan_cache_cost[0] = plan_cache_cost[0] + n
      plan
    }
  }
}

///|
/// Computes the forward discrete Fourier transform of the `n` points in `re`
/// and `im` with the plan, in place.
///
/// The transform is the unnormalised
/// `X[k] = sum_j x[j] * exp(-2 * pi * i * j * k / n)`.  The inverse transform
/// is the conjugate of the forward transform of the conjugated input, the
/// caller takes care of that.
fn dft_plan(plan : FftPlan, re : Array[Double], im : Array[Double]) -> Unit {
  let radices = plan.radix
  let counts = plan.m
  let twists = plan.kfac
  let mut stage = 0
  while stage < radices.length() {
    let r = radices[stage]
    let mi = counts[stage]
    let kk = twists[stage]
    // The twist of the stage is the exponent of the roots of unity of its
    // small transform.  The original uses `r - kfac` for the forward
    // transform, which is the same roots of unity as the ones of the port,
    // in the order in which the original uses them.
    let mu = r - kk
    // The specialised butterflies of `kernels.mbt`.
    stage_dispatch(r, mu, mi, kk, re, im)
    stage = stage + 1
  }
}

///|
/// The mixed radix discrete Fourier transform.
///
/// The original Java implementation uses the Good-Thomas prime factor
/// algorithm of `edu.mines.jtk.dsp.Pfacc`: the length is split into its prime
/// factors and every factor selects a small kernel.  That is `O(n log n)` for
/// every valid length.
///
/// This module implements the same idea in a generic way.  The length is
/// split into its prime factors, the factors are applied as the stages of a
/// decimation in time transform, and the small discrete Fourier transforms
/// of the stages are evaluated with a precomputed matrix.
///
/// The valid lengths of the original are built from the primes 2, 3, 5, 7, 11
/// and 13, so a radix of at most 13 is enough and every valid length is
/// covered.

///|
/// The number of transform elements that are kept in the plan cache at the
/// same time.
///
/// A plan holds the twiddle factors, the permutation and the work buffers of
/// one length.  The twiddle table of a length has about twice as many entries
/// as the length has points, and every entry is two doubles, so a plan costs
/// about 51 bytes per element of its length: the budget of two million
/// elements holds about 100 megabytes of plans.
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
/// The plan holds the factorization of the length into the radices of the
/// transform, the twiddle factors of every stage, the small discrete Fourier
/// matrices of the radices and the permutation of the decimation in time
/// transform.
priv struct FftPlan {
  n : Int32
  /// The radix of every stage, the stages are applied from the largest radix
  /// to the smallest one.
  radix : Array[Int32]
  /// The size of the block of every stage.
  block : Array[Int32]
  /// The offset of the twiddle table of every stage.
  twiddle_off : Array[Int32]
  /// The real parts of the twiddle factors of all the stages.
  twiddle_re : Array[Double]
  /// The imaginary parts of the twiddle factors of all the stages.
  twiddle_im : Array[Double]
  /// The real parts of the small Fourier matrices of all the radices, the
  /// matrix of the radix `r` starts at `matrix_off[r]` and holds the entry
  /// `W_r^(s * p)` at the index `p * r + s`.
  matrix_re : Array[Double]
  /// The imaginary parts of the small Fourier matrices of all the radices.
  matrix_im : Array[Double]
  /// The offset of the matrix of every radix.
  matrix_off : Array[Int32]
  /// The index of the source sample of every position of the permuted array.
  perm : Array[Int32]
  /// The real parts of the working buffer of the transform.
  buf_re : Array[Double]
  /// The imaginary parts of the working buffer of the transform.
  buf_im : Array[Double]
  /// The real parts of the scratch space of the butterfly.
  scratch_re : Array[Double]
  /// The imaginary parts of the scratch space of the butterfly.
  scratch_im : Array[Double]
}

///|
/// Factors `n` into its prime factors, in ascending order.
fn factorize(n : Int32) -> Array[Int32] {
  let factors = Array::Array(capacity=8)
  let mut rest = n
  let mut p = 2
  while p * p <= rest {
    while rest % p == 0 {
      factors.push(p)
      rest = rest / p
    }
    p = p + 1
  }
  if rest > 1 {
    factors.push(rest)
  }
  factors
}

///|
/// Builds the transform plan of a length.
fn build_plan(n : Int32) -> FftPlan {
  let factors = factorize(n)
  let k = factors.length()
  // The stages are applied from the largest radix to the smallest one, so
  // that the first stage works on the smallest blocks.  The block of a stage
  // is the product of the radices of that stage and of all the stages after
  // it.
  let radix = Array::Array(capacity=k)
  let block = Array::Array(capacity=k)
  let twiddle_off = Array::Array(capacity=k)
  let mut j = 0
  let mut len = 1
  while j < k {
    let r = factors[k - 1 - j]
    radix.push(r)
    len = len * r
    block.push(len)
    twiddle_off.push(0)
    j = j + 1
  }
  // The weight of every digit of the mixed radix representation of an index.
  let weight = Array::Array(capacity=k)
  let mut w = 1
  j = 0
  while j < k {
    w = w * factors[j]
    weight.push(w)
    j = j + 1
  }
  // The twiddle factors of the stages.  A stage of the block size `l` and the
  // radix `r` needs the factors `W_l^(s * k)` for `s` in `0 .. r` and `k` in
  // `0 .. l / r`; they are stored with `k` in the outer position, so that the
  // inner loop over the radix reads them consecutively.
  let mut total = 0
  j = 0
  while j < k {
    total = total + block[j]
    j = j + 1
  }
  let twiddle_re = Array::Array(capacity=total)
  let twiddle_im = Array::Array(capacity=total)
  j = 0
  while j < k {
    let r = radix[j]
    let l = block[j]
    let m = l / r
    let off = twiddle_re.length()
    twiddle_off[j] = off
    // The base of the stage is `W_l^k`, the factors of the stage are its
    // powers.
    let base_re = Array::Array(capacity=m)
    let base_im = Array::Array(capacity=m)
    let mut k0 = 0
    while k0 < m {
      let ang = -two_pi * k0.to_double() / l.to_double()
      base_re.push(@math.cos(ang))
      base_im.push(@math.sin(ang))
      k0 = k0 + 1
    }
    k0 = 0
    while k0 < m {
      let mut pr = 1.0
      let mut pi = 0.0
      let mut s = 0
      while s < r {
        twiddle_re.push(pr)
        twiddle_im.push(pi)
        let nr = pr * base_re[k0] - pi * base_im[k0]
        let ni = pr * base_im[k0] + pi * base_re[k0]
        pr = nr
        pi = ni
        s = s + 1
      }
      k0 = k0 + 1
    }
    j = j + 1
  }
  // The largest radix of the plan.  The table of the small Fourier matrices
  // and the scratch space of the butterfly have to be that large.  The valid
  // lengths of the original need at most the radix 13, but a plan of any
  // length has to work, so the sizes follow the plan and not a constant.
  let mut max_r = 1
  j = 0
  while j < k {
    if radix[j] > max_r {
      max_r = radix[j]
    }
    j = j + 1
  }
  // The small Fourier matrices of the radices that occur in the length.
  let matrix_re = Array::Array(capacity=0)
  let matrix_im = Array::Array(capacity=0)
  let matrix_off = zeros(max_r + 1)
  let used = zeros(max_r + 1)
  j = 0
  while j < k {
    let r = radix[j]
    if used[r] == 0 {
      used[r] = 1
      matrix_off[r] = matrix_re.length()
      let br = @math.cos(-two_pi / r.to_double())
      let bi = @math.sin(-two_pi / r.to_double())
      // The entry `p * r + s` of the matrix is `W_r^(s * p)`, so the row `p`
      // holds the powers of `W_r^p`.
      let mut p = 0
      let mut wpr = 1.0
      let mut wpi = 0.0
      while p < r {
        let mut pr = 1.0
        let mut pi = 0.0
        let mut s = 0
        while s < r {
          matrix_re.push(pr)
          matrix_im.push(pi)
          let nr = pr * wpr - pi * wpi
          let ni = pr * wpi + pi * wpr
          pr = nr
          pi = ni
          s = s + 1
        }
        let nr = wpr * br - wpi * bi
        let ni = wpr * bi + wpi * br
        wpr = nr
        wpi = ni
        p = p + 1
      }
    }
    j = j + 1
  }
  // The permutation of the decimation in time transform.  The index of a
  // sample is written as
  //
  //   i = d_0 + r_0 * d_1 + r_0 * r_1 * d_2 + ...
  //
  // and the sample is read from the position
  //
  //   pos = sum over l of d_l * (n / (r_0 * ... * r_l))
  //
  // which is the mixed radix digit reversal.
  let perm = zeros(n)
  let mut i = 0
  while i < n {
    let mut rem = i
    let mut pos = 0
    j = 0
    while j < k {
      let d = rem % factors[j]
      rem = rem / factors[j]
      pos = pos + d * (n / weight[j])
      j = j + 1
    }
    perm[pos] = i
    i = i + 1
  }
  // The working buffer of the transform and the scratch space of the
  // butterfly are part of the plan, so that a transform does not allocate.
  let buf_re = zerosd(n)
  let buf_im = zerosd(n)
  let scratch_re = zerosd(max_r)
  let scratch_im = zerosd(max_r)
  {
    n,
    radix,
    block,
    twiddle_off,
    twiddle_re,
    twiddle_im,
    matrix_re,
    matrix_im,
    matrix_off,
    perm,
    buf_re,
    buf_im,
    scratch_re,
    scratch_im,
  }
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
/// matters because the twiddle factors of a length are worth as much as the
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
  let n = plan.n
  let k = plan.radix.length()
  // The tables are hoisted into locals, so that the inner loops do not have
  // to load them from the plan again and again.
  let radices = plan.radix
  let blocks = plan.block
  let offs = plan.twiddle_off
  let tw_re = plan.twiddle_re
  let tw_im = plan.twiddle_im
  let mut stage = 0
  while stage < k {
    let r = radices[stage]
    let l = blocks[stage]
    let m = l / r
    let tw_off = offs[stage]
    // The specialised butterflies of `kernels.mbt`.  Their constants of the
    // small transform are literals, so that the butterfly does not have to
    // read a matrix.
    if r == 2 {
      stage_r2(n, l, m, tw_off, tw_re, tw_im, re, im)
    } else if r == 3 {
      stage_r3(n, l, m, tw_off, tw_re, tw_im, re, im)
    } else if r == 5 {
      stage_r5(n, l, m, tw_off, tw_re, tw_im, re, im)
    } else if r == 7 {
      stage_r7(n, l, m, tw_off, tw_re, tw_im, re, im)
    } else if r == 11 {
      stage_r11(n, l, m, tw_off, tw_re, tw_im, re, im)
    } else if r == 13 {
      stage_r13(n, l, m, tw_off, tw_re, tw_im, re, im)
    } else {
      // A radix that the valid lengths of the original do not use, the
      // generic butterfly reads the matrix of the plan.  The valid lengths
      // only use the radices 2, 3, 5, 7, 11 and 13, all of which have a
      // specialised butterfly, so this path is only reached by a plan that
      // is built for a length of its own.
      stage_generic(plan, stage, re, im)
    }
    stage = stage + 1
  }
}

///|
/// The generic butterfly of a stage, used for the radices that the
/// specialised butterflies of `kernels.mbt` do not cover.
///
/// It evaluates the small discrete Fourier transform of the butterfly with the
/// matrix of the plan.  The valid lengths of the original only use the
/// radices 2, 3, 5, 7, 11 and 13, so this butterfly is not reached by a
/// transform of a valid length; it is exercised by the tests, with a plan
/// that is built for a length the original does not support.
fn stage_generic(
  plan : FftPlan,
  stage : Int32,
  re : Array[Double],
  im : Array[Double],
) -> Unit {
  let n = plan.n
  let r = plan.radix[stage]
  let l = plan.block[stage]
  let m = l / r
  let nblocks = n / l
  let tw_off = plan.twiddle_off[stage]
  let mat_off = plan.matrix_off[r]
  let tw_re = plan.twiddle_re
  let tw_im = plan.twiddle_im
  let mat_re = plan.matrix_re
  let mat_im = plan.matrix_im
  let u_re = plan.scratch_re
  let u_im = plan.scratch_im
  let mut b = 0
  while b < nblocks {
    let base = b * l
    let mut k0 = 0
    while k0 < m {
      // Gather the values of the butterfly and apply the twiddle factors.
      // The factor of the first value is one, it is skipped.
      let mut s = 0
      while s < r {
        let idx = base + k0 + s * m
        let mut vr = re[idx]
        let mut vi = im[idx]
        if s > 0 {
          let tw = tw_off + k0 * r + s
          let wr = tw_re[tw]
          let wi = tw_im[tw]
          let nr = vr * wr - vi * wi
          vi = vr * wi + vi * wr
          vr = nr
        }
        u_re[s] = vr
        u_im[s] = vi
        s = s + 1
      }
      // The small discrete Fourier transform of the butterfly.
      let mut p = 0
      while p < r {
        let mut sr = 0.0
        let mut si = 0.0
        s = 0
        while s < r {
          let ur = u_re[s]
          let ui = u_im[s]
          let mi = mat_off + p * r + s
          let mr = mat_re[mi]
          let mi_im = mat_im[mi]
          sr = sr + (ur * mr - ui * mi_im)
          si = si + (ur * mi_im + ui * mr)
          s = s + 1
        }
        re[base + k0 + p * m] = sr
        im[base + k0 + p * m] = si
        p = p + 1
      }
      k0 = k0 + 1
    }
    b = b + 1
  }
}

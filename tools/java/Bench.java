import java.util.Locale;

import edu.mines.jtk.dsp.FftComplex;
import edu.mines.jtk.dsp.FftReal;
import net.imglib2.FinalDimensions;
import net.imglib2.algorithm.fft2.FFTMethods;
import net.imglib2.img.list.ListImg;
import net.imglib2.type.numeric.complex.ComplexFloatType;
import net.imglib2.type.numeric.real.FloatType;

/**
 * Benchmark of the original Java implementation, the counterpart of
 * {@code moonbit_fft2/benchmark}.
 *
 * <p>The measurement protocol is identical on both sides:
 * <ol>
 * <li>a probe that grows the batch size until the probe itself lasts long
 * enough to be timed accurately; the probe doubles as the warm up,</li>
 * <li>an iteration count derived from the probe so that one measured round
 * takes about one second,</li>
 * <li>the best of three measured rounds.</li>
 * </ol>
 *
 * <p>Every line is printed as
 * {@code CASE <impl> <workload> n=<length> ns_per_op=<nanoseconds>} so that
 * the two sides can be joined.
 */
public class Bench
{
	/** The measured section should take about this long. */
	private static final long TARGET_NS = 1000000000L;

	/** A probe shorter than this is not accurate enough to derive the iteration count. */
	private static final long MIN_MEASURE_NS = 100000L;

	/** The largest batch size used by the probe. */
	private static final int MAX_BATCH = 1000000;

	/** The largest number of iterations of a measured round. */
	private static final int MAX_ITERS = 1000000;

	/** The number of measured rounds, the best one is reported. */
	private static final int ROUNDS = 3;

	private static double checksum;

	public static void main( final String[] args )
	{
		Locale.setDefault( Locale.ROOT );

		// complex to complex, the length has to be a valid FFT length
		final int[] c2c = { 16, 120, 240, 720, 4095, 5460, 10920, 32760 };
		for ( final int n : c2c )
			benchComplex( n );

		// real to complex, the length has to be even and its half a valid
		// complex length
		final int[] r2c = { 32, 480, 1440, 8190, 21840, 65520 };
		for ( final int n : r2c )
			benchReal( n );

		// the same transform through the image API of the original.  The
		// original only supports the lengths whose spectrum is the half
		// spectrum of the transform itself, i.e. the even ones.
		final int[] api = { 16, 120, 240, 720, 5460, 10920, 32760, 65520 };
		for ( final int n : api )
			benchApi( n );

		System.out.println( "CHECKSUM " + checksum );
	}

	// ------------------------------------------------------------------
	// the workloads
	// ------------------------------------------------------------------

	private static void benchComplex( final int n )
	{
		final FftComplex fft = new FftComplex( n );
		final float[] cx = new float[ 2 * n ];
		final float[] cy = new float[ 2 * n ];
		fill( cx );
		final long ns = measure( new Runnable()
		{
			@Override
			public void run()
			{
				fft.complexToComplex( -1, cx, cy );
			}
		} );
		report( "c2c", n, ns, cy );
	}

	private static void benchReal( final int n )
	{
		final FftReal fft = new FftReal( n );
		final float[] rx = new float[ n ];
		final float[] cy = new float[ n + 2 ];
		fill( rx );
		final long ns = measure( new Runnable()
		{
			@Override
			public void run()
			{
				fft.realToComplex( -1, rx, cy );
			}
		} );
		report( "r2c", n, ns, cy );
	}

	private static void benchApi( final int n )
	{
		final ListImg< FloatType > real = new ListImg<>( new long[] { n }, new FloatType() );
		final float[] values = new float[ n ];
		fill( values );
		final net.imglib2.RandomAccess< FloatType > access = real.randomAccess();
		for ( int i = 0; i < n; ++i )
		{
			access.setPosition( new long[] { i } );
			access.get().set( values[ i ] );
		}
		final ListImg< ComplexFloatType > cplx = new ListImg<>( new long[] { n / 2 + 1 },
				new ComplexFloatType() );
		final long ns = measure( new Runnable()
		{
			@Override
			public void run()
			{
				FFTMethods.realToComplex( real, cplx, 0, false );
			}
		} );
		final float[] out = new float[ 2 * ( n / 2 + 1 ) ];
		final net.imglib2.RandomAccess< ComplexFloatType > caccess = cplx.randomAccess();
		for ( int i = 0; i < n / 2 + 1; ++i )
		{
			caccess.setPosition( new long[] { i } );
			out[ 2 * i ] = caccess.get().getRealFloat();
			out[ 2 * i + 1 ] = caccess.get().getImaginaryFloat();
		}
		report( "api", n, ns, out );
	}

	// ------------------------------------------------------------------
	// the measurement
	// ------------------------------------------------------------------

	private static long measure( final Runnable r )
	{
		// probe, the batch grows until the probe is long enough to be timed
		// accurately; this is also where the JIT compiles the hot code
		int batch = 1;
		long probe = timeBatch( r, batch );
		while ( probe < MIN_MEASURE_NS && batch < MAX_BATCH )
		{
			batch = Math.min( batch * 10, MAX_BATCH );
			probe = timeBatch( r, batch );
		}

		// pick an iteration count that fills about one second
		final double single = ( double ) probe / batch;
		int iters = MAX_ITERS;
		if ( single > 0.0 )
		{
			final long cand = ( long ) ( TARGET_NS / single );
			iters = ( int ) Math.min( MAX_ITERS, Math.max( 1L, cand ) );
		}

		// warm up
		final int warmup = Math.min( 20, iters );
		for ( int i = 0; i < warmup; ++i )
			r.run();

		// measure, the best of three rounds
		long best = Long.MAX_VALUE;
		for ( int round = 0; round < ROUNDS; ++round )
		{
			final long total = timeBatch( r, iters );
			best = Math.min( best, total / iters );
		}
		return best;
	}

	private static long timeBatch( final Runnable r, final int count )
	{
		final long s0 = System.nanoTime();
		for ( int i = 0; i < count; ++i )
			r.run();
		return System.nanoTime() - s0;
	}

	private static void fill( final float[] a )
	{
		for ( int i = 0; i < a.length; ++i )
			a[ i ] = ( float ) ( ( i * 2654435761L ) % 1000 ) / 1000.0f - 0.5f;
	}

	private static void report( final String workload, final int n, final long ns, final float[] out )
	{
		double sum = 0.0;
		for ( int i = 0; i < out.length; ++i )
			sum += out[ i ];
		checksum += sum;
		System.out.println( "CASE java " + workload + " n=" + n + " ns_per_op=" + ns );
	}
}

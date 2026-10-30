import java.io.BufferedReader;
import java.io.DataInputStream;
import java.io.FileInputStream;
import java.io.FileReader;
import java.io.PrintWriter;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;

import edu.mines.jtk.dsp.FftComplex;
import edu.mines.jtk.dsp.FftReal;
import net.imglib2.FinalDimensions;
import net.imglib2.FinalInterval;
import net.imglib2.Interval;
import net.imglib2.algorithm.fft2.FFT;
import net.imglib2.algorithm.fft2.FFTMethods;
import net.imglib2.img.list.ListImg;
import net.imglib2.img.list.ListImgFactory;
import net.imglib2.type.numeric.complex.ComplexFloatType;
import net.imglib2.type.numeric.real.FloatType;
import net.imglib2.view.Views;

/**
 * Reference oracle for the moonbit_fft2 port.
 *
 * <p>Drives the <em>original</em> {@code net.imglib2.algorithm.fft2} classes
 * (compiled bytecode shipped in {@code fft2/}) over deterministic test data and
 * dumps the results in a simple text format that the MoonBit port reproduces
 * bit for bit.
 */
public class Oracle
{
	// ------------------------------------------------------------------
	// small helpers
	// ------------------------------------------------------------------

	private static long prod( final int[] dims )
	{
		long n = 1;
		for ( final int d : dims )
			n *= d;
		return n;
	}

	private static long[] toLong( final int[] dims )
	{
		final long[] l = new long[ dims.length ];
		for ( int i = 0; i < dims.length; ++i )
			l[ i ] = dims[ i ];
		return l;
	}

	private static float[] readFloats( final String path ) throws Exception
	{
		try ( DataInputStream in = new DataInputStream( new FileInputStream( path ) ) )
		{
			final byte[] raw = in.readAllBytes();
			final float[] v = new float[ raw.length / 4 ];
			for ( int i = 0; i < v.length; ++i )
			{
				final int b = ( raw[ 4 * i ] & 0xff ) | ( ( raw[ 4 * i + 1 ] & 0xff ) << 8 )
						| ( ( raw[ 4 * i + 2 ] & 0xff ) << 16 ) | ( ( raw[ 4 * i + 3 ] & 0xff ) << 24 );
				v[ i ] = Float.intBitsToFloat( b );
			}
			return v;
		}
	}

	/**
	 * Fills the image with the given values in row major (C) order, i.e. the
	 * first dimension varies fastest.  {@code ListImg} keeps its data in
	 * column major order, so the values are placed through explicit
	 * coordinates instead of relying on the iteration order of the cursor.
	 */
	private static void fillReal( final ListImg< FloatType > img, final int[] dims,
			final float[] vals )
	{
		final net.imglib2.RandomAccess< FloatType > access = img.randomAccess();
		final long[] position = new long[ dims.length ];
		int i = 0;
		for ( int flat = 0; flat < vals.length; ++flat )
		{
			int rest = flat;
			for ( int d = 0; d < dims.length; ++d )
			{
				position[ d ] = rest % dims[ d ];
				rest = rest / dims[ d ];
			}
			access.setPosition( position );
			access.get().set( vals[ i++ ] );
		}
	}

	private static void fillComplex( final ListImg< ComplexFloatType > img, final int[] dims,
			final float[] vals )
	{
		final net.imglib2.RandomAccess< ComplexFloatType > access = img.randomAccess();
		final long[] position = new long[ dims.length ];
		int i = 0;
		for ( int flat = 0; flat < vals.length / 2; ++flat )
		{
			int rest = flat;
			for ( int d = 0; d < dims.length; ++d )
			{
				position[ d ] = rest % dims[ d ];
				rest = rest / dims[ d ];
			}
			access.setPosition( position );
			final ComplexFloatType t = access.get();
			t.setReal( vals[ 2 * i ] );
			t.setImaginary( vals[ 2 * i + 1 ] );
			++i;
		}
	}

	/**
	 * Reads the image back in row major (C) order.
	 */
	private static < T > float[] drain( final net.imglib2.img.Img< T > img, final int[] dims,
			final boolean complex )
	{
		final int n = ( int ) prod( dims );
		final float[] out = new float[ complex ? 2 * n : n ];
		final net.imglib2.RandomAccess< T > access = img.randomAccess();
		final long[] position = new long[ dims.length ];
		for ( int flat = 0; flat < n; ++flat )
		{
			int rest = flat;
			for ( int d = 0; d < dims.length; ++d )
			{
				position[ d ] = rest % dims[ d ];
				rest = rest / dims[ d ];
			}
			access.setPosition( position );
			final T t = access.get();
			if ( complex )
			{
				final net.imglib2.type.numeric.ComplexType< ? > c =
						(net.imglib2.type.numeric.ComplexType< ? >) t;
				out[ 2 * flat ] = c.getRealFloat();
				out[ 2 * flat + 1 ] = c.getImaginaryFloat();
			}
			else
			{
				final net.imglib2.type.numeric.RealType< ? > r =
						(net.imglib2.type.numeric.RealType< ? >) t;
				out[ flat ] = r.getRealFloat();
			}
		}
		return out;
	}

	private static ListImg< FloatType > makeReal( final int[] dims, final float[] vals )
	{
		final ListImg< FloatType > img = new ListImg<>( toLong( dims ), new FloatType() );
		fillReal( img, dims, vals );
		return img;
	}

	private static ListImg< ComplexFloatType > makeComplex( final int[] dims, final float[] vals )
	{
		final ListImg< ComplexFloatType > img = new ListImg<>( toLong( dims ), new ComplexFloatType() );
		fillComplex( img, dims, vals );
		return img;
	}

	private static int[] dimsOf( final net.imglib2.img.Img< ? > img )
	{
		final int[] d = new int[ img.numDimensions() ];
		for ( int i = 0; i < d.length; ++i )
			d[ i ] = ( int ) img.dimension( i );
		return d;
	}

	// ------------------------------------------------------------------
	// manifest
	// ------------------------------------------------------------------

	private static class Case
	{
		String name;
		String kind;
		int[] dims = new int[ 0 ];
		int[] target = new int[ 0 ];
		String in;
		int dim = 0;
		boolean scale = false;
		boolean forward = true;
		float fill = 0.0f;
	}

	private static List< Case > readManifest( final String path ) throws Exception
	{
		final List< Case > cases = new ArrayList<>();
		Case cur = null;
		try ( BufferedReader r = new BufferedReader( new FileReader( path ) ) )
		{
			String line;
			while ( ( line = r.readLine() ) != null )
			{
				line = line.trim();
				if ( line.isEmpty() )
					continue;
				final String[] parts = line.split( "\\s+" );
				switch ( parts[ 0 ] )
				{
					case "CASE":
						cur = new Case();
						cur.name = parts[ 1 ];
						cases.add( cur );
						break;
					case "KIND":
						cur.kind = parts[ 1 ];
						break;
					case "DIMS":
						cur.dims = parseInts( parts, 1 );
						break;
					case "TARGET":
						cur.target = parseInts( parts, 1 );
						break;
					case "IN":
						cur.in = parts[ 1 ];
						break;
					case "DIM":
						cur.dim = Integer.parseInt( parts[ 1 ] );
						break;
					case "SCALE":
						cur.scale = parts[ 1 ].equals( "1" );
						break;
					case "FORWARD":
						cur.forward = parts[ 1 ].equals( "1" );
						break;
					case "FILL":
						cur.fill = Float.parseFloat( parts[ 1 ] );
						break;
					default:
						break;
				}
			}
		}
		return cases;
	}

	private static int[] parseInts( final String[] parts, final int from )
	{
		final int[] r = new int[ parts.length - from ];
		for ( int i = from; i < parts.length; ++i )
			r[ i - from ] = Integer.parseInt( parts[ i ] );
		return r;
	}

	// ------------------------------------------------------------------
	// per case execution
	// ------------------------------------------------------------------

	private static void run( final Case c, final PrintWriter out ) throws Exception
	{
		final float[] in = readFloats( c.in );
		int[] outDims = new int[ 0 ];
		float[] values = new float[ 0 ];
		boolean status = true;
		final List< Integer > extra = new ArrayList<>();

		switch ( c.kind )
		{
			case "R2C":
			{
				final ListImg< FloatType > real = makeReal( c.dims, in );
				final int[] cdims = c.dims.clone();
				cdims[ c.dim ] = c.dims[ c.dim ] / 2 + 1;
				final ListImg< ComplexFloatType > cplx = new ListImg<>( toLong( cdims ),
						new ComplexFloatType() );
				status = FFTMethods.realToComplex( real, cplx, c.dim, c.scale );
				outDims = cdims;
				values = drain( cplx, dimsOf( cplx ), true );
				break;
			}
			case "C2C":
			{
				final ListImg< ComplexFloatType > cplx = makeComplex( c.dims, in );
				status = FFTMethods.complexToComplex( cplx, c.dim, c.forward, c.scale );
				outDims = c.dims;
				values = drain( cplx, dimsOf( cplx ), true );
				break;
			}
			case "C2R":
			{
				final ListImg< ComplexFloatType > cplx = makeComplex( c.dims, in );
				final int[] rdims = c.dims.clone();
				rdims[ c.dim ] = 2 * ( c.dims[ c.dim ] - 1 );
				final ListImg< FloatType > real = new ListImg<>( toLong( rdims ), new FloatType() );
				status = FFTMethods.complexToReal( cplx, real, real, c.dim, c.scale );
				outDims = rdims;
				values = drain( real, dimsOf( real ), false );
				break;
			}
			case "FFT_R2C":
			{
				final ListImg< FloatType > real = makeReal( c.dims, in );
				final ListImgFactory< ComplexFloatType > factory = new ListImgFactory<>(
						new ComplexFloatType() );
				final net.imglib2.img.Img< ComplexFloatType > fft = FFT.realToComplex( real, factory );
				outDims = dimsOf( fft );
				values = drain( fft, dimsOf( fft ), true );
				break;
			}
			case "FFT_R2C_OOB_CONST":
			{
				// the original extends the input with an out of bounds strategy
				// before it pads it, here the strategy is a constant
				final ListImg< FloatType > real = makeReal( c.dims, in );
				final ListImgFactory< ComplexFloatType > factory = new ListImgFactory<>(
						new ComplexFloatType() );
				final net.imglib2.outofbounds.OutOfBoundsConstantValueFactory< FloatType,
						net.imglib2.RandomAccessibleInterval< FloatType > > oobs =
						new net.imglib2.outofbounds.OutOfBoundsConstantValueFactory<>(
								new FloatType( c.fill ) );
				final net.imglib2.img.Img< ComplexFloatType > fft = FFT.realToComplex( real,
						oobs, factory );
				outDims = dimsOf( fft );
				values = drain( fft, dimsOf( fft ), true );
				break;
			}
			case "FFT_C2C_FWD":
			{
				final ListImg< ComplexFloatType > cplx = makeComplex( c.dims, in );
				FFT.complexToComplexForward( cplx );
				outDims = c.dims;
				values = drain( cplx, dimsOf( cplx ), true );
				break;
			}
			case "FFT_C2C_INV":
			{
				final ListImg< ComplexFloatType > cplx = makeComplex( c.dims, in );
				FFT.complexToComplexInverse( cplx );
				outDims = c.dims;
				values = drain( cplx, dimsOf( cplx ), true );
				break;
			}
			case "FFT_C2R":
			{
				final ListImg< ComplexFloatType > cplx = makeComplex( c.dims, in );
				final int[] rdims = c.dims.clone();
				rdims[ c.dim ] = 2 * ( c.dims[ c.dim ] - 1 );
				final ListImg< FloatType > real = new ListImg<>( toLong( rdims ), new FloatType() );
				FFT.complexToReal( cplx, real );
				outDims = rdims;
				values = drain( real, dimsOf( real ), false );
				break;
			}
			case "FFT_C2R_UNPAD":
			{
				// the output keeps the original (unpadded) extent, the range
				// that is written is derived from it
				final ListImg< ComplexFloatType > cplx = makeComplex( c.dims, in );
				final int[] rdims = c.target.clone();
				final ListImg< FloatType > real = new ListImg<>( toLong( rdims ), new FloatType() );
				FFT.complexToRealUnpad( cplx, real );
				outDims = rdims;
				values = drain( real, dimsOf( real ), false );
				break;
			}
			case "FFT_C2R_FACTORY":
			{
				// the padded variant, the extent of the result is computed by
				// the original implementation itself
				final ListImg< ComplexFloatType > cplx = makeComplex( c.dims, in );
				final ListImgFactory< FloatType > factory = new ListImgFactory<>(
						new FloatType() );
				final net.imglib2.img.Img< FloatType > real = FFT.complexToReal( cplx, factory,
						new FloatType() );
				outDims = dimsOf( real );
				values = drain( real, dimsOf( real ), false );
				break;
			}
			case "SIZES":
			{
				// the transform length tables of the original implementation,
				// for every n from 1 to the requested maximum
				final int max = c.target.length > 0 ? c.target[ 0 ] : 128;
				outDims = new int[ 0 ];
				for ( int n = 1; n <= max; ++n )
				{
					extra.add( FftReal.nfftFast( n ) );
					extra.add( FftReal.nfftSmall( n ) );
					extra.add( FftComplex.nfftFast( n ) );
					extra.add( FftComplex.nfftSmall( n ) );
				}
				values = new float[ 0 ];
				break;
			}
			case "PAD":
			{
				final Interval src = new FinalInterval( toLong( c.dims ) );
				final Interval padded = FFTMethods.paddingIntervalCentered( src,
						FinalDimensions.wrap( toLong( c.target ) ) );
				outDims = new int[ c.dims.length ];
				for ( int d = 0; d < c.dims.length; ++d )
				{
					outDims[ d ] = ( int ) ( padded.max( d ) - padded.min( d ) + 1 );
					extra.add( ( int ) padded.min( d ) );
					extra.add( ( int ) padded.max( d ) );
				}
				values = new float[ 0 ];
				break;
			}
			case "UNPAD":
			{
				final Interval src = new FinalInterval( toLong( c.dims ) );
				final Interval unpadded = FFTMethods.unpaddingIntervalCentered( src,
						FinalDimensions.wrap( toLong( c.target ) ) );
				outDims = new int[ c.dims.length ];
				for ( int d = 0; d < c.dims.length; ++d )
				{
					outDims[ d ] = ( int ) ( unpadded.max( d ) - unpadded.min( d ) + 1 );
					extra.add( ( int ) unpadded.min( d ) );
					extra.add( ( int ) unpadded.max( d ) );
				}
				values = new float[ 0 ];
				break;
			}
			case "DIMS_R2C":
			{
				final long[] cs = new long[ c.dims.length ];
				final long[] rs = new long[ c.dims.length ];
				FFTMethods.dimensionsRealToComplexFast( FinalDimensions.wrap( toLong( c.dims ) ), cs, rs );
				outDims = new int[ c.dims.length ];
				for ( int d = 0; d < c.dims.length; ++d )
				{
					outDims[ d ] = ( int ) cs[ d ];
					extra.add( ( int ) cs[ d ] );
					extra.add( ( int ) rs[ d ] );
				}
				values = new float[ 0 ];
				break;
			}
			case "DIMS_C2R":
			{
				final long[] cs = new long[ c.dims.length ];
				final long[] rs = new long[ c.dims.length ];
				FFTMethods.dimensionsComplexToRealFast( FinalDimensions.wrap( toLong( c.dims ) ), cs, rs );
				outDims = new int[ c.dims.length ];
				for ( int d = 0; d < c.dims.length; ++d )
				{
					outDims[ d ] = ( int ) cs[ d ];
					extra.add( ( int ) cs[ d ] );
					extra.add( ( int ) rs[ d ] );
				}
				values = new float[ 0 ];
				break;
			}
			case "DIMS_C2C":
			{
				final long[] cs = new long[ c.dims.length ];
				FFTMethods.dimensionsComplexToComplexFast( FinalDimensions.wrap( toLong( c.dims ) ), cs );
				outDims = new int[ c.dims.length ];
				for ( int d = 0; d < c.dims.length; ++d )
				{
					outDims[ d ] = ( int ) cs[ d ];
					extra.add( ( int ) cs[ d ] );
				}
				values = new float[ 0 ];
				break;
			}
			case "DIMS_R2C_SMALL":
			{
				final long[] cs = new long[ c.dims.length ];
				final long[] rs = new long[ c.dims.length ];
				FFTMethods.dimensionsRealToComplexSmall( FinalDimensions.wrap( toLong( c.dims ) ), cs, rs );
				outDims = new int[ c.dims.length ];
				for ( int d = 0; d < c.dims.length; ++d )
				{
					outDims[ d ] = ( int ) cs[ d ];
					extra.add( ( int ) cs[ d ] );
					extra.add( ( int ) rs[ d ] );
				}
				values = new float[ 0 ];
				break;
			}
			case "DIMS_C2R_SMALL":
			{
				final long[] cs = new long[ c.dims.length ];
				final long[] rs = new long[ c.dims.length ];
				FFTMethods.dimensionsComplexToRealSmall( FinalDimensions.wrap( toLong( c.dims ) ), cs, rs );
				outDims = new int[ c.dims.length ];
				for ( int d = 0; d < c.dims.length; ++d )
				{
					outDims[ d ] = ( int ) cs[ d ];
					extra.add( ( int ) cs[ d ] );
					extra.add( ( int ) rs[ d ] );
				}
				values = new float[ 0 ];
				break;
			}
			case "DIMS_C2C_SMALL":
			{
				final long[] cs = new long[ c.dims.length ];
				FFTMethods.dimensionsComplexToComplexSmall( FinalDimensions.wrap( toLong( c.dims ) ), cs );
				outDims = new int[ c.dims.length ];
				for ( int d = 0; d < c.dims.length; ++d )
				{
					outDims[ d ] = ( int ) cs[ d ];
					extra.add( ( int ) cs[ d ] );
				}
				values = new float[ 0 ];
				break;
			}
			default:
				throw new IllegalArgumentException( "unknown kind " + c.kind );
		}

		out.println( "CASE " + c.name );
		out.println( "KIND " + c.kind );
		out.println( "NDIMS " + outDims.length );
		final StringBuilder sb = new StringBuilder();
		for ( final int d : outDims )
			sb.append( d ).append( ' ' );
		out.println( "DIMS " + sb.toString().trim() );
		out.println( "STATUS " + ( status ? "ok" : "unsupported" ) );
		out.println( "N " + values.length );
		for ( final float v : values )
			out.println( String.format( "%08x", Float.floatToRawIntBits( v ) ) );
		out.println( "EXTRA " + extra.size() );
		for ( final int v : extra )
			out.println( v );
	}

	public static void main( final String[] args ) throws Exception
	{
		if ( args.length < 2 )
		{
			System.err.println( "usage: Oracle <manifest.txt> <outdir>" );
			System.exit( 2 );
		}
		final Path outDir = Paths.get( args[ 1 ] );
		Files.createDirectories( outDir );
		final List< Case > cases = readManifest( args[ 0 ] );
		for ( final Case c : cases )
		{
			final Path p = outDir.resolve( c.name + ".txt" );
			// The original implementation catches some of its own failures and
			// prints a stack trace, and lets others escape.  Both are recorded
			// as "throws" so that the port can be held to the same behaviour.
			final java.io.PrintStream originalErr = System.err;
			final java.io.ByteArrayOutputStream captured = new java.io.ByteArrayOutputStream();
			System.setErr( new java.io.PrintStream( captured, true ) );
			boolean threw = false;
			try ( PrintWriter out = new PrintWriter( Files.newBufferedWriter( p ) ) )
			{
				run( c, out );
			}
			catch ( Throwable t )
			{
				threw = true;
			}
			finally
			{
				System.setErr( originalErr );
			}
			final String err = captured.toString( "UTF-8" );
			if ( threw || err.contains( "Exception" ) )
			{
				try ( PrintWriter out = new PrintWriter( Files.newBufferedWriter( p ) ) )
				{
					out.println( "CASE " + c.name );
					out.println( "KIND " + c.kind );
					out.println( "NDIMS 0" );
					out.println( "DIMS " );
					out.println( "STATUS throws" );
					out.println( "N 0" );
					out.println( "EXTRA 0" );
				}
				System.out.println( "oracle: " + c.name + " (throws)" );
				continue;
			}
			System.out.println( "oracle: " + c.name );
		}
	}
}

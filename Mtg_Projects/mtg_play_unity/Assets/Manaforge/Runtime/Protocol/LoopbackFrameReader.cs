using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Threading;

namespace Manaforge.Play.Protocol
{
    // Transfers ownership of one connected loopback socket on successful construction.
    // One reader only. Run on a worker; writes/connect/handshake budgets belong to the owner.
    public sealed class LoopbackFrameReader : IDisposable
    {
        private readonly Socket socket;
        private int closed, reading;
        public bool IsClosed => Volatile.Read(ref closed) != 0;
        public bool ReadInProgress => Volatile.Read(ref reading) != 0;
        public LoopbackFrameReader(Socket ownedSocket)
        {
            if (ownedSocket == null || !ownedSocket.Connected
                || !(ownedSocket.LocalEndPoint is IPEndPoint local) || !IPAddress.IsLoopback(local.Address)
                || !(ownedSocket.RemoteEndPoint is IPEndPoint remote) || !IPAddress.IsLoopback(remote.Address))
                throw new ArgumentException("FRAME_SOCKET_CONTEXT");
            // Defensive fallback after readiness; cancellation/deadline checks also poll every <=25 ms.
            ownedSocket.ReceiveTimeout = 25;
            socket = ownedSocket;
        }
        public string Read(int timeoutMilliseconds = 5000, CancellationToken cancellation = default)
        {
            if (timeoutMilliseconds < 1 || timeoutMilliseconds > 60000) throw new ArgumentOutOfRangeException(nameof(timeoutMilliseconds));
            if (IsClosed) throw new TextFrame.FrameException("FRAME_CLOSED");
            if (Interlocked.Exchange(ref reading, 1) != 0)
            { Dispose(); throw new TextFrame.FrameException("FRAME_CONCURRENT"); }
            try
            {
                using var input = new DeadlineStream(this, timeoutMilliseconds, cancellation);
                input.Check();
                string text = TextFrame.Read(input);
                input.Check(); // no completed frame is returned after observed cancellation/deadline
                return text;
            }
            catch (TextFrame.FrameException) { Dispose(); throw; }
            catch (OperationCanceledException) { Dispose(); throw new TextFrame.FrameException("FRAME_CANCELLED"); }
            catch (Exception error) when (error is SocketException || error is IOException || error is ObjectDisposedException)
            {
                string code = IsClosed ? "FRAME_CLOSED" : "FRAME_IO";
                Dispose(); throw new TextFrame.FrameException(code);
            }
            finally { Volatile.Write(ref reading, 0); }
        }
        public void Dispose()
        { if (Interlocked.Exchange(ref closed, 1) == 0) socket.Dispose(); }

        private sealed class DeadlineStream : Stream
        {
            private readonly LoopbackFrameReader owner;
            private readonly int budget;
            private readonly CancellationToken cancellation;
            private readonly Stopwatch timer = Stopwatch.StartNew();
            public DeadlineStream(LoopbackFrameReader owner, int budget, CancellationToken cancellation)
            { this.owner = owner; this.budget = budget; this.cancellation = cancellation; }
            public void Check()
            {
                cancellation.ThrowIfCancellationRequested();
                if (owner.IsClosed) throw new TextFrame.FrameException("FRAME_CLOSED");
                if (timer.Elapsed.TotalMilliseconds >= budget) throw new TextFrame.FrameException("FRAME_TIMEOUT");
            }
            public override int Read(byte[] buffer, int offset, int count)
            {
                if (buffer == null) throw new ArgumentNullException(nameof(buffer));
                if (offset < 0 || count < 0 || offset > buffer.Length - count) throw new ArgumentOutOfRangeException();
                if (count == 0) return 0;
                while (true)
                {
                    Check();
                    int microseconds = Math.Max(1, (int)Math.Ceiling(Math.Min(25, budget - timer.Elapsed.TotalMilliseconds) * 1000));
                    if (!owner.socket.Poll(microseconds, SelectMode.SelectRead)) continue;
                    Check();
                    try { return owner.socket.Receive(buffer, offset, count, SocketFlags.None); }
                    catch (SocketException error) when (error.SocketErrorCode == SocketError.TimedOut || error.SocketErrorCode == SocketError.WouldBlock) { }
                }
            }
            public override bool CanRead => true;
            public override bool CanSeek => false;
            public override bool CanWrite => false;
            public override long Length => throw new NotSupportedException();
            public override long Position { get => throw new NotSupportedException(); set => throw new NotSupportedException(); }
            public override void Flush() { }
            public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
            public override void SetLength(long value) => throw new NotSupportedException();
            public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
        }
    }
}

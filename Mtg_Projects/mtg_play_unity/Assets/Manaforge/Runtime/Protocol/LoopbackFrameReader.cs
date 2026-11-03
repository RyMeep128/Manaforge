using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Threading;

namespace Manaforge.Play.Protocol
{
    // Transfers ownership of one connected loopback socket on successful construction.
    // One reader only. Run on a worker; one writer may run alongside it. Connect/handshake budgets belong to the session owner.
    public sealed class LoopbackFrameReader : IDisposable
    {
        private readonly Socket socket;
        private int closed, reading, writing, handshakeAttempted,challengeAttempted;
        public bool IsClosed => Volatile.Read(ref closed) != 0;
        public bool WriteInProgress => Volatile.Read(ref writing) != 0;
        public bool ReadInProgress => Volatile.Read(ref reading) != 0;
        public LoopbackFrameReader(Socket ownedSocket)
        {
            if (ownedSocket == null || !ownedSocket.Connected
                || !(ownedSocket.LocalEndPoint is IPEndPoint local) || !IPAddress.IsLoopback(local.Address)
                || !(ownedSocket.RemoteEndPoint is IPEndPoint remote) || !IPAddress.IsLoopback(remote.Address))
                throw new ArgumentException("FRAME_SOCKET_CONTEXT");
            // Defensive fallback after readiness; cancellation/deadline checks also poll every <=25 ms.
            ownedSocket.LingerState = new LingerOption(false, 0);
            ownedSocket.ReceiveTimeout = 25;
            ownedSocket.SendTimeout = 25;
            socket = ownedSocket;
        }
        // A connection may attempt viewer authentication once. This marker is NOT authentication proof.
        internal bool BeginViewerHandshake()=>!IsClosed && Interlocked.CompareExchange(ref handshakeAttempted,1,0)==0;
        internal bool BeginViewerChallenge()=>!IsClosed && Volatile.Read(ref handshakeAttempted)==0 && Interlocked.CompareExchange(ref challengeAttempted,1,0)==0;
        public string Read(int timeoutMilliseconds = 5000, CancellationToken cancellation = default)
        {
            if (timeoutMilliseconds < 1 || timeoutMilliseconds > 60000) throw new ArgumentOutOfRangeException(nameof(timeoutMilliseconds));
            return ReadBounded(timeoutMilliseconds, timeoutMilliseconds, cancellation);
        }
        // Authenticated owner-lifetime wait; partial frames retain their deadline.
        public string ReadWhenAvailable(int timeoutMilliseconds, CancellationToken cancellation = default)
        {
            if (timeoutMilliseconds < 1 || timeoutMilliseconds > 60000) throw new ArgumentOutOfRangeException(nameof(timeoutMilliseconds));
            return ReadBounded(timeoutMilliseconds, timeoutMilliseconds, cancellation, true);
        }
        public string ReadWithIdleWait(int waitMilliseconds, int frameMilliseconds, CancellationToken cancellation = default)
        {
            if (waitMilliseconds < 1 || waitMilliseconds > 21600000 || frameMilliseconds < 1 || frameMilliseconds > 60000) throw new ArgumentOutOfRangeException();
            return ReadBounded(waitMilliseconds, frameMilliseconds, cancellation);
        }
        private string ReadBounded(int timeoutMilliseconds, int frameMilliseconds, CancellationToken cancellation, bool idle = false)
        {
            if (IsClosed) throw new TextFrame.FrameException("FRAME_CLOSED");
            if (Interlocked.Exchange(ref reading, 1) != 0)
            { Dispose(); throw new TextFrame.FrameException("FRAME_CONCURRENT"); }
            try
            {
                using var input = new DeadlineStream(this, timeoutMilliseconds, frameMilliseconds, cancellation, idle);
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
        // Success means local socket acceptance only, never an engine acknowledgement.
        public void Write(string text, int timeoutMilliseconds = 5000, CancellationToken cancellation = default)
        {
            if (timeoutMilliseconds < 1 || timeoutMilliseconds > 60000) throw new ArgumentOutOfRangeException(nameof(timeoutMilliseconds));
            if (IsClosed) throw new TextFrame.FrameException("FRAME_CLOSED");
            if (Interlocked.Exchange(ref writing, 1) != 0)
            { Dispose(); throw new TextFrame.FrameException("FRAME_CONCURRENT_WRITE"); }
            using var frame = new MemoryStream();
            var timer = Stopwatch.StartNew();
            try
            {
                // Validate/encode the whole bounded frame before any socket bytes are written.
                TextFrame.Write(frame, text);
                byte[] bytes = frame.GetBuffer(); int size = (int)frame.Length, offset = 0;
                try
                {
                    while (offset < size)
                    {
                        CheckWrite(timer, timeoutMilliseconds, cancellation);
                        int microseconds = Math.Max(1, (int)Math.Ceiling(Math.Min(25, timeoutMilliseconds - timer.Elapsed.TotalMilliseconds) * 1000));
                        if (!socket.Poll(microseconds, SelectMode.SelectWrite)) continue;
                        CheckWrite(timer, timeoutMilliseconds, cancellation);
                        int sent = socket.Send(bytes, offset, Math.Min(16384, size - offset), SocketFlags.None);
                        if (sent <= 0) throw new TextFrame.FrameException("FRAME_WRITE_IO");
                        offset += sent;
                    }
                    CheckWrite(timer, timeoutMilliseconds, cancellation);
                }
                catch (TextFrame.FrameException) { Dispose(); throw; }
                catch (OperationCanceledException) { Dispose(); throw new TextFrame.FrameException("FRAME_WRITE_CANCELLED"); }
                catch (SocketException error)
                {
                    string code = cancellation.IsCancellationRequested ? "FRAME_WRITE_CANCELLED" : IsClosed ? "FRAME_CLOSED" :
                        error.SocketErrorCode == SocketError.TimedOut || error.SocketErrorCode == SocketError.WouldBlock
                            ? "FRAME_WRITE_TIMEOUT" : "FRAME_WRITE_IO";
                    // A failed Send may already have transferred bytes. Never retry that chunk.
                    Dispose(); throw new TextFrame.FrameException(code);
                }
                catch (ObjectDisposedException) { Dispose(); throw new TextFrame.FrameException("FRAME_CLOSED"); }
            }
            finally
            {
                if (frame.TryGetBuffer(out var buffer)) Array.Clear(buffer.Array, buffer.Offset, buffer.Count);
                Volatile.Write(ref writing, 0);
            }
        }
        private void CheckWrite(Stopwatch timer, int budget, CancellationToken cancellation)
        {
            cancellation.ThrowIfCancellationRequested();
            if (IsClosed) throw new TextFrame.FrameException("FRAME_CLOSED");
            if (timer.Elapsed.TotalMilliseconds >= budget) throw new TextFrame.FrameException("FRAME_WRITE_TIMEOUT");
        }
        public void Dispose()
        { if (Interlocked.Exchange(ref closed, 1) == 0) socket.Dispose(); }

        private sealed class DeadlineStream : Stream
        {
            private readonly LoopbackFrameReader owner;
            private readonly int budget, frameBudget;
            private Stopwatch frameTimer;
            private readonly bool idle;
            private readonly CancellationToken cancellation;
            private readonly Stopwatch timer = Stopwatch.StartNew();
            public DeadlineStream(LoopbackFrameReader owner, int budget, int frameBudget, CancellationToken cancellation, bool idle)
            { this.owner = owner; this.budget = budget; this.frameBudget = frameBudget; this.cancellation = cancellation; this.idle = idle; }
            public void Check()
            {
                cancellation.ThrowIfCancellationRequested();
                if (owner.IsClosed) throw new TextFrame.FrameException("FRAME_CLOSED");
                if (!idle && timer.Elapsed.TotalMilliseconds >= budget) throw new TextFrame.FrameException("FRAME_TIMEOUT");
                if (frameTimer != null && frameTimer.Elapsed.TotalMilliseconds >= frameBudget) throw new TextFrame.FrameException("FRAME_TIMEOUT");
            }
            public override int Read(byte[] buffer, int offset, int count)
            {
                if (buffer == null) throw new ArgumentNullException(nameof(buffer));
                if (offset < 0 || count < 0 || offset > buffer.Length - count) throw new ArgumentOutOfRangeException();
                if (count == 0) return 0;
                while (true)
                {
                    Check();
                    double remaining = idle ? 25 : budget - timer.Elapsed.TotalMilliseconds;
                    if (frameTimer != null) remaining = Math.Min(remaining, frameBudget - frameTimer.Elapsed.TotalMilliseconds);
                    int microseconds = Math.Max(1, (int)Math.Ceiling(Math.Min(25, remaining) * 1000));
                    if (!owner.socket.Poll(microseconds, SelectMode.SelectRead)) continue;
                    Check();
                    try { int received = owner.socket.Receive(buffer, offset, count, SocketFlags.None); if (received > 0 && frameTimer == null) frameTimer = Stopwatch.StartNew(); return received; }
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

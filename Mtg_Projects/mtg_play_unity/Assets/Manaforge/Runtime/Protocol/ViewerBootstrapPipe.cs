using System;
using System.Diagnostics;
using System.IO;
using System.IO.Pipes;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Win32.SafeHandles;

namespace Manaforge.Play.Protocol
{
    // Windows owned duplicate of inherited input. Single consumer; never polls on the render thread.
    public sealed class ViewerBootstrapPipe : IDisposable
    {
        private readonly AnonymousPipeClientStream input;private int stopped,stage;
        public sealed class PipeException : IOException
        {public string Code {get;} internal PipeException(string code):base(code){Code=code;}}
        private const int StdInput=-10;
        [DllImport("kernel32.dll")] private static extern IntPtr GetStdHandle(int id);
        [DllImport("kernel32.dll")] private static extern IntPtr GetCurrentProcess();
        [DllImport("kernel32.dll",SetLastError=true)] private static extern uint GetFileType(SafePipeHandle handle);
        [DllImport("kernel32.dll",SetLastError=true)] private static extern bool DuplicateHandle(IntPtr source,SafePipeHandle handle,IntPtr target,out SafePipeHandle duplicate,uint access,bool inherit,uint options);
        [DllImport("kernel32.dll",SetLastError=true)] private static extern bool PeekNamedPipe(SafePipeHandle pipe,IntPtr buffer,uint size,IntPtr read,out uint available,IntPtr left);
        private static PipeException Error(string code)=>new PipeException(code);
        private ViewerBootstrapPipe(SafePipeHandle source)
        {
            SafePipeHandle owned=null;
            try {
                if(!RuntimeInformation.IsOSPlatform(OSPlatform.Windows))throw Error("BOOTSTRAP_PIPE_PLATFORM");
                if(source==null || source.IsClosed || source.IsInvalid || GetFileType(source)!=3)throw Error("BOOTSTRAP_PIPE_INVALID");
                var process=GetCurrentProcess();
                if(!DuplicateHandle(process,source,process,out owned,0,false,2))throw Error("BOOTSTRAP_PIPE_INVALID");
                input=new AnonymousPipeClientStream(PipeDirection.In,owned);owned=null;
            }
            catch(PipeException){throw;}
            catch{throw Error("BOOTSTRAP_PIPE_INVALID");}
            finally{owned?.Dispose();}
        }
        // The source handle remains caller-owned; this reader owns a non-inheritable duplicate.
        public static ViewerBootstrapPipe FromInheritedHandle(SafePipeHandle source)=>new ViewerBootstrapPipe(source);
        public static ViewerBootstrapPipe FromStandardInput()
        {
            if(!RuntimeInformation.IsOSPlatform(OSPlatform.Windows))throw Error("BOOTSTRAP_PIPE_PLATFORM");
            using(var borrowed=new SafePipeHandle(GetStdHandle(StdInput),false))return new ViewerBootstrapPipe(borrowed);
        }
        private void Check(CancellationToken cancellation,Stopwatch timer=null,int milliseconds=0)
        {
            if(cancellation.IsCancellationRequested)throw Error("BOOTSTRAP_PIPE_CANCELLED");
            if(Volatile.Read(ref stopped)!=0)throw Error("BOOTSTRAP_PIPE_CLOSED");
            if(timer!=null && timer.Elapsed.TotalMilliseconds>=milliseconds)throw Error("BOOTSTRAP_PIPE_TIMEOUT");
        }
        private int Available()
        {
            if(PeekNamedPipe(input.SafePipeHandle,IntPtr.Zero,0,IntPtr.Zero,out var count,IntPtr.Zero))return (int)Math.Min(count,4096u);
            int error=Marshal.GetLastWin32Error();if(error==109 || error==232 || error==233)return -1;
            throw Error("BOOTSTRAP_PIPE_READ_FAILED");
        }
        private bool Exact(byte[] bytes,CancellationToken cancellation,Stopwatch timer,int milliseconds)
        {
            int offset=0;
            while(offset<bytes.Length) {
                Check(cancellation,timer,milliseconds);int available=Available();
                if(available<0){if(offset==0)return false;throw Error("BOOTSTRAP_PIPE_TRUNCATED");}
                if(available==0){Thread.Sleep(10);continue;}
                int count=input.Read(bytes,offset,Math.Min(available,bytes.Length-offset));
                if(count==0){if(offset==0)return false;throw Error("BOOTSTRAP_PIPE_TRUNCATED");}offset+=count;
            }
            Check(cancellation,timer,milliseconds);return true;
        }
        public Task<ViewerBootstrap> ReadBootstrapAsync(int milliseconds=5000,CancellationToken cancellation=default)
        {
            if(milliseconds<1 || milliseconds>60000)throw new ArgumentOutOfRangeException(nameof(milliseconds));
            if(Interlocked.CompareExchange(ref stage,1,0)!=0)throw Error("BOOTSTRAP_PIPE_STATE");
            var timer=Stopwatch.StartNew();
            return Task.Run(()=>{
                byte[] header=new byte[4],payload=null;ViewerBootstrap bootstrap=null;
                try {
                    if(!Exact(header,cancellation,timer,milliseconds))throw Error("BOOTSTRAP_PIPE_EOF");
                    uint size=((uint)header[0]<<24)|((uint)header[1]<<16)|((uint)header[2]<<8)|header[3];
                    if(size<1 || size>ViewerBootstrap.MaximumBytes)throw Error("BOOTSTRAP_PIPE_SIZE");
                    payload=new byte[(int)size];if(!Exact(payload,cancellation,timer,milliseconds))throw Error("BOOTSTRAP_PIPE_TRUNCATED");
                    try{bootstrap=ViewerBootstrap.Parse(payload);}catch(IOException){throw Error("BOOTSTRAP_PIPE_PAYLOAD");}
                    Check(cancellation,timer,milliseconds);Volatile.Write(ref stage,2);return bootstrap;
                }
                catch(PipeException){bootstrap?.Dispose();Dispose();throw;}
                catch{bootstrap?.Dispose();string code=cancellation.IsCancellationRequested?"BOOTSTRAP_PIPE_CANCELLED":Volatile.Read(ref stopped)!=0?"BOOTSTRAP_PIPE_CLOSED":"BOOTSTRAP_PIPE_READ_FAILED";Dispose();throw Error(code);}
                finally{Array.Clear(header,0,header.Length);if(payload!=null)Array.Clear(payload,0,payload.Length);}
            });
        }
        // EOF is an owner-lifecycle signal, not a game result. Caller marshals cleanup/quit to UI.
        public Task WaitForOwnerCloseAsync(CancellationToken cancellation=default)
        {
            if(Interlocked.CompareExchange(ref stage,3,2)!=2)throw Error("BOOTSTRAP_PIPE_STATE");
            return Task.Run(()=>{
                try {
                    while(true){Check(cancellation);int available=Available();if(available<0)return;if(available>0)throw Error("BOOTSTRAP_PIPE_UNEXPECTED_DATA");Thread.Sleep(10);}
                }
                catch(PipeException){throw;}
                catch{throw Error(cancellation.IsCancellationRequested?"BOOTSTRAP_PIPE_CANCELLED":Volatile.Read(ref stopped)!=0?"BOOTSTRAP_PIPE_CLOSED":"BOOTSTRAP_PIPE_READ_FAILED");}
                finally{Dispose();}
            });
        }
        public void Dispose(){if(Interlocked.Exchange(ref stopped,1)==0)input.Dispose();}
    }
}

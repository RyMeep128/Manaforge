using System;
using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace Manaforge.Play
{
    public enum PresetStoreStatus { Ready, Missing, RecoveredBackup, Corrupt, UnsupportedVersion, Conflict, ValidationError, IoError, Busy }
    public enum PresetWriteStage { TemporaryFlushed, BeforeReplace }
    public sealed class PresetStoreResult
    {
        public PresetStoreStatus Status { get; }
        public LayoutPresetLibrary Library { get; }
        public string Revision { get; }
        public bool Success=>Status==PresetStoreStatus.Ready || Status==PresetStoreStatus.Missing || Status==PresetStoreStatus.RecoveredBackup;
        public bool CanWrite=>Success || Status==PresetStoreStatus.Corrupt;
        public PresetStoreResult(PresetStoreStatus status,LayoutPresetLibrary library=null,string revision=null)
        {Status=status;Library=library;Revision=revision;}
    }
    public interface ILayoutPresetStore
    {
        Task<PresetStoreResult> ReadAsync(CancellationToken cancellation=default);
        Task<PresetStoreResult> WriteAsync(LayoutPresetLibrary library,string expectedRevision,CancellationToken cancellation=default);
    }
    internal static class PresetStoreCodec
    {
        internal const int MaximumBytes=1048576;
        internal static readonly UTF8Encoding Utf8=new UTF8Encoding(false,true);
        internal static byte[] Encode(LayoutPresetLibrary library)
        {
            var data=Utf8.GetBytes(library.ToJson().ToString(Formatting.Indented));
            if(data.Length>MaximumBytes)throw new ArgumentException("PRESET_FILE_LIMIT");
            if(Decode(data,out _)!=PresetStoreStatus.Ready)throw new ArgumentException("PRESET_FILE_INVALID");return data;
        }
        internal static PresetStoreStatus Decode(byte[] data,out LayoutPresetLibrary library)
        {
            library=null;
            try{
                if(data==null || data.Length>MaximumBytes)return PresetStoreStatus.Corrupt;
                string json=Utf8.GetString(data);if(json.Length>0 && json[0]=='\uFEFF')json=json.Substring(1);
                using(var text=new StringReader(json))
                using(var reader=new JsonTextReader(text){MaxDepth=32,DateParseHandling=DateParseHandling.None}){
                    var root=JObject.Load(reader,new JsonLoadSettings{DuplicatePropertyNameHandling=DuplicatePropertyNameHandling.Error});
                    while(reader.Read())if(reader.TokenType!=JsonToken.Comment)return PresetStoreStatus.Corrupt;
                    if(root["version"]?.Type==JTokenType.Integer && root["version"].ToString(Formatting.None)!=LayoutPresetLibrary.SchemaVersion.ToString(System.Globalization.CultureInfo.InvariantCulture))
                        return PresetStoreStatus.UnsupportedVersion;
                    library=LayoutPresetLibrary.Parse(root);return PresetStoreStatus.Ready;
                }
            }catch(Exception ex) when(ex is JsonException || ex is ArgumentException || ex is OverflowException || ex is InvalidCastException){return PresetStoreStatus.Corrupt;}
        }
        internal static string Hash(byte[] data)
        {using(var sha=SHA256.Create())return BitConverter.ToString(sha.ComputeHash(data)).Replace("-","");}
    }

    public sealed class JsonLayoutPresetStore : ILayoutPresetStore
    {
        private readonly string directory,path,backup;
        private readonly Action<PresetWriteStage> writeStage;
        public JsonLayoutPresetStore(string directory,Action<PresetWriteStage> writeStage=null)
        {
            this.directory=Path.GetFullPath(directory);path=Path.Combine(this.directory,"presets.json");backup=path+".bak";this.writeStage=writeStage;
        }
        public Task<PresetStoreResult> ReadAsync(CancellationToken cancellation=default)=>Task.Run(()=>Locked(Read,cancellation),cancellation);
        public Task<PresetStoreResult> WriteAsync(LayoutPresetLibrary library,string expectedRevision,CancellationToken cancellation=default)
        {
            return Task.Run(()=>Locked(()=>Write(library,expectedRevision,cancellation),cancellation),cancellation);
        }
        private PresetStoreResult Locked(Func<PresetStoreResult> action,CancellationToken cancellation)
        {
            try{
                Directory.CreateDirectory(directory);var timer=Stopwatch.StartNew();
                FileStream owner=null;
                while(owner==null){
                    cancellation.ThrowIfCancellationRequested();
                    try{owner=new FileStream(path+".lock",FileMode.OpenOrCreate,FileAccess.ReadWrite,FileShare.None);}
                    catch(IOException){if(timer.ElapsedMilliseconds>=2000)return new PresetStoreResult(PresetStoreStatus.Busy);Thread.Sleep(25);}
                }
                using(owner){cancellation.ThrowIfCancellationRequested();return action();}
            }catch(Exception ex) when(ex is IOException || ex is UnauthorizedAccessException || ex is System.Security.SecurityException)
            {return new PresetStoreResult(PresetStoreStatus.IoError);}
        }
        private byte[] Bytes(string file)
        {
            if(!File.Exists(file))return null;
            using(var stream=new FileStream(file,FileMode.Open,FileAccess.Read,FileShare.Read)){
                if(stream.Length>PresetStoreCodec.MaximumBytes)return Array.Empty<byte>();
                var data=new byte[(int)stream.Length];int count=0;
                while(count<data.Length){int read=stream.Read(data,count,data.Length-count);if(read==0)throw new IOException("PRESET_READ_CHANGED");count+=read;}
                return data;
            }
        }
        private string Stamp(string file,byte[] bytes)
        {
            if(bytes==null)return "missing";
            if(bytes.Length>0)return PresetStoreCodec.Hash(bytes);
            var info=new FileInfo(file);return "empty-or-oversize:"+info.Length+":"+info.LastWriteTimeUtc.Ticks;
        }
        private PresetStoreResult Read()
        {
            byte[] main=Bytes(path),good=Bytes(backup);string revision=Stamp(path,main)+"/"+Stamp(backup,good);
            var status=main==null?PresetStoreStatus.Missing:PresetStoreCodec.Decode(main,out _);
            if(status==PresetStoreStatus.Ready){
                PresetStoreCodec.Decode(main,out var library);
                // A downgrade must not rotate a newer-version backup out of existence.
                if(good!=null && PresetStoreCodec.Decode(good,out _)==PresetStoreStatus.UnsupportedVersion)
                    return new PresetStoreResult(PresetStoreStatus.UnsupportedVersion,library,revision);
                return new PresetStoreResult(status,library,revision);
            }
            if(status==PresetStoreStatus.UnsupportedVersion)return new PresetStoreResult(status,LayoutPresetLibrary.Empty,revision);
            if(good!=null){
                var backupStatus=PresetStoreCodec.Decode(good,out var library);
                if(backupStatus==PresetStoreStatus.Ready)return new PresetStoreResult(PresetStoreStatus.RecoveredBackup,library,revision);
                if(backupStatus==PresetStoreStatus.UnsupportedVersion)return new PresetStoreResult(backupStatus,LayoutPresetLibrary.Empty,revision);
            }
            return new PresetStoreResult(status==PresetStoreStatus.Missing && good==null?PresetStoreStatus.Missing:PresetStoreStatus.Corrupt,LayoutPresetLibrary.Empty,revision);
        }
        private PresetStoreResult Write(LayoutPresetLibrary library,string expectedRevision,CancellationToken cancellation)
        {
            byte[] data;
            try{data=PresetStoreCodec.Encode(library);}
            catch(Exception ex) when(ex is ArgumentException || ex is NullReferenceException){return new PresetStoreResult(PresetStoreStatus.ValidationError);}
            var current=Read();
            if(!current.CanWrite)return current;
            if(expectedRevision!=current.Revision)return new PresetStoreResult(PresetStoreStatus.Conflict);
            string temporary=path+"."+Guid.NewGuid().ToString("N")+".tmp";
            try{
                using(var stream=new FileStream(temporary,FileMode.CreateNew,FileAccess.Write,FileShare.None)){
                    stream.Write(data,0,data.Length);stream.Flush(true);
                }
                writeStage?.Invoke(PresetWriteStage.TemporaryFlushed);cancellation.ThrowIfCancellationRequested();
                writeStage?.Invoke(PresetWriteStage.BeforeReplace);
                var primary=Bytes(path);bool validPrimary=primary!=null && PresetStoreCodec.Decode(primary,out _)==PresetStoreStatus.Ready;
                if(validPrimary){
                    if(File.Exists(backup) && PresetStoreCodec.Decode(Bytes(backup),out _)!=PresetStoreStatus.Ready)
                        File.Move(backup,backup+".recovery-"+Guid.NewGuid().ToString("N")+".json");
                    File.Replace(temporary,path,backup,true);
                }else{
                    // Never rotate corrupt bytes over the validated last-good backup.
                    if(File.Exists(path))File.Move(path,path+".recovery-"+Guid.NewGuid().ToString("N")+".json");
                    if(!File.Exists(backup))File.Copy(temporary,backup);
                    else if(PresetStoreCodec.Decode(Bytes(backup),out _)!=PresetStoreStatus.Ready){
                        File.Move(backup,backup+".recovery-"+Guid.NewGuid().ToString("N")+".json");File.Copy(temporary,backup);
                    }
                    File.Move(temporary,path);
                }
                return Read();
            }finally{if(File.Exists(temporary))try{File.Delete(temporary);}catch(IOException){}catch(UnauthorizedAccessException){}}
        }
    }

    // Isolated default for programmatic fixtures/captures, never touches a user's profile.
    public sealed class MemoryLayoutPresetStore : ILayoutPresetStore
    {
        private readonly object gate=new object();private LayoutPresetLibrary library=LayoutPresetLibrary.Empty;private int revision;
        public Task<PresetStoreResult> ReadAsync(CancellationToken cancellation=default)
        {cancellation.ThrowIfCancellationRequested();lock(gate)return Task.FromResult(new PresetStoreResult(PresetStoreStatus.Ready,library,revision.ToString()));}
        public Task<PresetStoreResult> WriteAsync(LayoutPresetLibrary value,string expectedRevision,CancellationToken cancellation=default)
        {
            cancellation.ThrowIfCancellationRequested();lock(gate){
                if(expectedRevision!=revision.ToString())return Task.FromResult(new PresetStoreResult(PresetStoreStatus.Conflict));
                try{PresetStoreCodec.Encode(value);}catch(Exception ex) when(ex is ArgumentException || ex is NullReferenceException){return Task.FromResult(new PresetStoreResult(PresetStoreStatus.ValidationError));}
                library=value;revision++;return Task.FromResult(new PresetStoreResult(PresetStoreStatus.Ready,library,revision.ToString()));
            }
        }
    }
}

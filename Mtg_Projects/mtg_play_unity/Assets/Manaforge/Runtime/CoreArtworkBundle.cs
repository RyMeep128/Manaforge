using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Manaforge.Play.Protocol;
using Newtonsoft.Json.Linq;

namespace Manaforge.Play
{
    // Pinned ephemeral launch sidecar. Index only: pixels are read lazily by authorized jobs.
    public sealed class CoreArtworkBundle : IDisposable
    {
        private readonly object gate=new object();
        private readonly string root,session,viewer;
        private readonly Dictionary<string,Entry> entries=new Dictionary<string,Entry>(StringComparer.Ordinal);
        private bool disposed;private bool previewOnly;
        private int resolverPort;private string resolverKey;
        internal sealed class Entry
        {public CatalogArtworkFace Catalog;public string File,Digest;public int Width,Height,Bytes;}
        private static readonly Regex Hash=new Regex("^[0-9a-f]{64}$",RegexOptions.CultureInvariant);
        public int EntryCount {get{lock(gate)return entries.Count;}}
        private CoreArtworkBundle(string root,string session,string viewer){this.root=root;this.session=session;this.viewer=viewer;}
        private static IOException Invalid()=>new IOException("CORE_ARTWORK_BUNDLE_INVALID");
        private static void Fields(JToken token,params string[] names)
        {if(!(token is JObject obj) || !obj.Properties().Select(p=>p.Name).OrderBy(n=>n).SequenceEqual(names.OrderBy(n=>n)))throw Invalid();}
        private static string Text(JToken value)
        {if(value?.Type!=JTokenType.String || string.IsNullOrWhiteSpace((string)value) || ((string)value).Length>1024)throw Invalid();return (string)value;}
        private static int Number(JToken value,int maximum)
        {if(value?.Type!=JTokenType.Integer || (long)value<1 || (long)value>maximum)throw Invalid();return (int)value;}
        private static string PrintedText(JToken value,int maximum)
        {if(value==null || value.Type==JTokenType.Null)return null;if(value.Type!=JTokenType.String || ((string)value).Length>maximum)throw Invalid();return (string)value;}
        private static void DirectorySafe(string root)
        {for(var dir=new DirectoryInfo(root);dir!=null;dir=dir.Parent)if((dir.Attributes&FileAttributes.ReparsePoint)!=0)throw Invalid();}
        internal static byte[] Read(string root,string file,int maximum,CancellationToken cancellation)
        {
            DirectorySafe(root);string path=Path.Combine(root,file);
            if((File.GetAttributes(path)&FileAttributes.ReparsePoint)!=0)throw Invalid();
            using(var stream=new FileStream(path,FileMode.Open,FileAccess.Read,FileShare.Read)) {
                if(stream.Length<1 || stream.Length>maximum)throw Invalid();
                var bytes=new byte[(int)stream.Length];int offset=0;
                try {
                    while(offset<bytes.Length){cancellation.ThrowIfCancellationRequested();int count=stream.Read(bytes,offset,Math.Min(65536,bytes.Length-offset));if(count==0)throw Invalid();offset+=count;}
                    return bytes;
                }
                catch{Array.Clear(bytes,0,bytes.Length);throw;}
            }
        }
        internal static string Digest(byte[] bytes){using(var hash=SHA256.Create())return BitConverter.ToString(hash.ComputeHash(bytes)).Replace("-","").ToLowerInvariant();}
        public static Task<CoreArtworkBundle> OpenAsync(string directory,string manifestSha256,string session,string viewer,CancellationToken cancellation=default)
            =>Task.Run(()=>Open(directory,manifestSha256,session,viewer,cancellation),cancellation);
        public static Task<CoreArtworkBundle> OpenPreviewAsync(string directory,string pin,string preview,CancellationToken cancellation=default)
            =>Task.Run(()=>Open(directory,pin,preview,"deck-preview",cancellation,true),cancellation);
        private static CoreArtworkBundle Open(string directory,string pin,string session,string viewer,CancellationToken cancellation,bool previewOnly=false)
        {
            byte[] bytes=null;CoreArtworkBundle bundle=null;
            try {
                cancellation.ThrowIfCancellationRequested();
                if(string.IsNullOrWhiteSpace(directory) || !Hash.IsMatch(pin??"") || string.IsNullOrWhiteSpace(session) || string.IsNullOrWhiteSpace(viewer))throw Invalid();
                string root=Path.GetFullPath(directory);bytes=Read(root,"manifest.json",1024*1024,cancellation);
                if(Digest(bytes)!=pin)throw Invalid();
                var manifest=WireEnvelope.ParseObject(new UTF8Encoding(false,true).GetString(bytes));
                int version=Number(manifest["artwork_bundle_version"],3);
                if(version==3)Fields(manifest,"artwork_bundle_version","source","session_id","viewer_id","entries","unavailable","resolver");
                else Fields(manifest,"artwork_bundle_version","source","session_id","viewer_id","entries","unavailable");
                if(Text(manifest["source"])!="manaforge_core_cache"
                    || Text(manifest["session_id"])!=session || Text(manifest["viewer_id"])!=viewer)throw Invalid();
                if(!(manifest["entries"] is JArray records) || !(manifest["unavailable"] is JArray missing)
                    || records.Count+missing.Count<(previewOnly || version==3?0:1) || records.Count+missing.Count>256)throw Invalid();
                bundle=new CoreArtworkBundle(root,session,viewer){previewOnly=previewOnly};var seen=new HashSet<string>(StringComparer.Ordinal);var files=new Dictionary<string,int>();long total=0;
                if(version==3) {
                    if(previewOnly || records.Count!=0 || missing.Count!=0)throw Invalid();
                    var resolver=manifest["resolver"];Fields(resolver,"host","port","key");
                    if(Text(resolver["host"])!="127.0.0.1" || !Hash.IsMatch(Text(resolver["key"])))throw Invalid();
                    bundle.resolverPort=Number(resolver["port"],65535);bundle.resolverKey=Text(resolver["key"]);
                }
                foreach(var record in records) {
                    cancellation.ThrowIfCancellationRequested();
                    var fields=new List<string>{"oracle_id","printing_id","face_key","layout","face_count","standard_compatible","printed_type_line","file","width","height","byte_length","sha256","pixel_format","row_origin"};
                    if(version==2)fields.AddRange(new[]{"printed_name","printed_rules","printed_mana_cost"});
                    Fields(record,fields.ToArray());
                    string printing=Text(record["printing_id"]),digest=Text(record["sha256"]),file=Text(record["file"]);
                    int width=Number(record["width"],1024),height=Number(record["height"],1024),length=Number(record["byte_length"],4*1024*1024);
                    if(!seen.Add(printing) || !Hash.IsMatch(digest) || file!=digest+".rgba" || length!=width*height*4
                        || record["standard_compatible"]?.Type!=JTokenType.Boolean
                        || (!previewOnly && (Text(record["layout"])!="normal" || Number(record["face_count"],1)!=1))
                        || Text(record["pixel_format"])!="RGBA8" || Text(record["row_origin"])!="bottom_left")throw Invalid();
                    if(files.TryGetValue(file,out var previous)){if(previous!=length)throw Invalid();}
                    else{files.Add(file,length);if((total+=length)>256*1024*1024)throw Invalid();}
                    bundle.entries.Add(printing,new Entry{Catalog=new CatalogArtworkFace(Text(record["oracle_id"]),printing,Text(record["face_key"]),Text(record["layout"]),Number(record["face_count"],8),(bool)record["standard_compatible"],Text(record["printed_type_line"]),PrintedText(record["printed_name"],1024),PrintedText(record["printed_rules"],16384),PrintedText(record["printed_mana_cost"],1024)),File=file,Digest=digest,Width=width,Height=height,Bytes=length});
                }
                foreach(var record in missing) {
                    Fields(record,"printing_id","code");if(!seen.Add(Text(record["printing_id"])))throw Invalid();
                    string code=Text(record["code"]);if(code!="ARTWORK_MISSING" && code!="ARTWORK_FACE_UNSUPPORTED" && code!="ARTWORK_METADATA_UNAVAILABLE")throw Invalid();
                }
                return bundle;
            }
            catch(OperationCanceledException){bundle?.Dispose();throw;}
            catch{bundle?.Dispose();throw Invalid();}
            finally{if(bytes!=null)Array.Clear(bytes,0,bytes.Length);}
        }
        public Task<PreparedCardArtwork> LoadAsync(ViewerArtworkRequest request,CancellationToken cancellation)
            =>Task.Run(()=>Load(request,cancellation),cancellation);
        private PreparedCardArtwork Load(ViewerArtworkRequest request,CancellationToken cancellation)
        {
            byte[] bytes=null;PreparedCardArtwork prepared=null;
            try {
                cancellation.ThrowIfCancellationRequested();Entry entry;
                lock(gate) {
                    if(disposed)throw Invalid();
                    if(request==null || request.Ticket.SessionId!=session || request.Ticket.ViewerId!=viewer)throw Invalid();
                    if(!entries.TryGetValue(request.PrintingId,out entry)) {
                        if(resolverPort==0)return null;
                        entry=null;
                    }
                    if(entry!=null && entry.Catalog.OracleId!=request.OracleId)throw Invalid();
                }
                if(entry==null)return LoadPublic(request,cancellation);
                bytes=Read(root,entry.File,entry.Bytes,cancellation);
                if(bytes.Length!=entry.Bytes || Digest(bytes)!=entry.Digest)throw Invalid();
                prepared=PreparedCardArtwork.Prepare(request,entry.Catalog,entry.Width,entry.Height,bytes);
                cancellation.ThrowIfCancellationRequested();return prepared;
            }
            catch(OperationCanceledException){prepared?.Dispose();throw;}
            catch{prepared?.Dispose();throw Invalid();}
            finally{if(bytes!=null)Array.Clear(bytes,0,bytes.Length);}
        }
        // Public catalog requests happen only on artwork workers, after the surface
        // has admitted a visible printing. No hidden deck inventory reaches Unity.
        private PreparedCardArtwork LoadPublic(ViewerArtworkRequest request,CancellationToken cancellation)
        {
            byte[] pixels=null;
            try {
                int port;string key;lock(gate){if(disposed)throw Invalid();port=resolverPort;key=resolverKey;}
                using(var client=new System.Net.Sockets.TcpClient())
                using(cancellation.Register(()=>client.Dispose())) {
                    client.ReceiveTimeout=30000;client.SendTimeout=5000;
                    client.Connect("127.0.0.1",port);cancellation.ThrowIfCancellationRequested();
                    using(var stream=client.GetStream()) {
                        var query=new JObject{["action"]="artwork",["session_id"]=session,["viewer_id"]=viewer,["key"]=key,["oracle_id"]=request.OracleId,["printing_id"]=request.PrintingId};
                        TextFrame.Write(stream,query.ToString(Newtonsoft.Json.Formatting.None));
                        var record=WireEnvelope.ParseObject(TextFrame.Read(stream));
                        if((bool?)record["unavailable"]==true)return null;
                        Fields(record,"oracle_id","printing_id","face_key","layout","standard_compatible","printed_type_line","printed_name","printed_rules","printed_mana_cost","width","height","byte_length","sha256");
                        if(Text(record["oracle_id"])!=request.OracleId || Text(record["printing_id"])!=request.PrintingId || record["standard_compatible"]?.Type!=JTokenType.Boolean)throw Invalid();
                        int width=Number(record["width"],1024),height=Number(record["height"],1024),length=Number(record["byte_length"],4*1024*1024);
                        string digest=Text(record["sha256"]);if(length!=width*height*4 || !Hash.IsMatch(digest))throw Invalid();
                        pixels=new byte[length];int offset=0;
                        while(offset<length){cancellation.ThrowIfCancellationRequested();int count=stream.Read(pixels,offset,Math.Min(65536,length-offset));if(count==0)throw Invalid();offset+=count;}
                        if(Digest(pixels)!=digest)throw Invalid();
                        var catalog=new CatalogArtworkFace(request.OracleId,request.PrintingId,Text(record["face_key"]),Text(record["layout"]),1,(bool)record["standard_compatible"],Text(record["printed_type_line"]),PrintedText(record["printed_name"],1024),PrintedText(record["printed_rules"],16384),PrintedText(record["printed_mana_cost"],1024));
                        return PreparedCardArtwork.Prepare(request,catalog,width,height,pixels);
                    }
                }
            }
            finally{if(pixels!=null)Array.Clear(pixels,0,pixels.Length);}
        }
        public sealed class PreviewPixels : IDisposable
        {
            public CatalogArtworkFace Catalog {get;} public int Width {get;} public int Height {get;}
            public byte[] Bytes {get;private set;}
            internal PreviewPixels(Entry entry,byte[] bytes){Catalog=entry.Catalog;Width=entry.Width;Height=entry.Height;Bytes=bytes;}
            public void Dispose(){if(Bytes!=null){Array.Clear(Bytes,0,Bytes.Length);Bytes=null;}}
        }
        public Task<PreviewPixels> LoadPreviewAsync(string oracle,string printing,CancellationToken cancellation)
            =>Task.Run(()=>{
                Entry entry;lock(gate){if(disposed || !previewOnly)throw Invalid();if(printing==null || !entries.TryGetValue(printing,out entry) || entry.Catalog.OracleId!=oracle)return null;}
                byte[] bytes=Read(root,entry.File,entry.Bytes,cancellation);
                if(bytes.Length!=entry.Bytes || Digest(bytes)!=entry.Digest){Array.Clear(bytes,0,bytes.Length);throw Invalid();}
                return new PreviewPixels(entry,bytes);
            },cancellation);
        public void Dispose(){lock(gate){disposed=true;entries.Clear();resolverKey=null;}}
    }
}

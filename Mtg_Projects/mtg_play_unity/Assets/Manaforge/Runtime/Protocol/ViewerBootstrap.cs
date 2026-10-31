using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using Newtonsoft.Json.Linq;

namespace Manaforge.Play.Protocol
{
    // Private owner-to-viewer configuration. Not a public wire message or authentication proof.
    public sealed class ViewerBootstrap : IDisposable
    {
        public const int MaximumBytes=16384;
        private readonly object gate=new object();private byte[] key;private bool disposed,taken;
        public string Host=>"127.0.0.1";public int Port {get;}
        public string SessionId {get;} public string ViewerId {get;} public string EngineVersion {get;}
        public string ArtifactManifestSha256 {get;} public string ArtworkDirectory {get;} public string ArtworkManifestSha256 {get;}
        private static IOException Invalid()=>new IOException("VIEWER_BOOTSTRAP_INVALID");
        private static void Fields(JToken token,params string[] fields)
        {if(!(token is JObject obj) || !obj.Properties().Select(p=>p.Name).OrderBy(p=>p).SequenceEqual(fields.OrderBy(p=>p)))throw Invalid();}
        private static string Match(JToken token,string pattern)
        {if(token?.Type!=JTokenType.String || !Regex.IsMatch((string)token,"\\A"+pattern+"\\z",RegexOptions.CultureInvariant))throw Invalid();return (string)token;}
        private static void Version(JToken token){if(token?.Type!=JTokenType.Integer || (long)token!=1)throw Invalid();}
        private ViewerBootstrap(JObject value)
        {
            Fields(value,"viewer_bootstrap_version","protocol_version","endpoint","session_id","viewer_id","engine_version","artifact_manifest_sha256","viewer_key_hex","artwork");
            Version(value["viewer_bootstrap_version"]);Version(value["protocol_version"]);var endpoint=value["endpoint"];Fields(endpoint,"host","port");
            if(endpoint["host"]?.Type!=JTokenType.String || (string)endpoint["host"]!="127.0.0.1" || endpoint["port"]?.Type!=JTokenType.Integer || (long)endpoint["port"]<1 || (long)endpoint["port"]>65535)throw Invalid();Port=(int)endpoint["port"];
            SessionId=Match(value["session_id"],"[A-Za-z0-9_.:-]{1,128}");ViewerId=Match(value["viewer_id"],"[A-Za-z0-9_.:-]{1,128}");EngineVersion=Match(value["engine_version"],"[A-Za-z0-9_.:-]{1,128}");ArtifactManifestSha256=Match(value["artifact_manifest_sha256"],"[0-9a-f]{64}");
            string hex=Match(value["viewer_key_hex"],"[0-9a-f]{64}");
            var artwork=value["artwork"];
            if(artwork.Type!=JTokenType.Null) {
                Fields(artwork,"directory","manifest_sha256");
                if(artwork["directory"]?.Type!=JTokenType.String)throw Invalid();string directory=(string)artwork["directory"];
                if(string.IsNullOrEmpty(directory) || directory.Length>4096 || directory.Any(c=>c<32) || directory.StartsWith("\\\\",StringComparison.Ordinal) || directory.StartsWith("//",StringComparison.Ordinal) || !Path.IsPathFullyQualified(directory))throw Invalid();
                ArtworkDirectory=directory;ArtworkManifestSha256=Match(artwork["manifest_sha256"],"[0-9a-f]{64}");
            }
            // Allocate owned secret only after all metadata validation succeeds.
            key=Enumerable.Range(0,32).Select(i=>Convert.ToByte(hex.Substring(i*2,2),16)).ToArray();
        }
        public static ViewerBootstrap Parse(byte[] privateUtf8)
        {
            try {
                if(privateUtf8==null || privateUtf8.Length<1 || privateUtf8.Length>MaximumBytes)throw Invalid();
                return new ViewerBootstrap(WireEnvelope.ParseObject(new UTF8Encoding(false,true).GetString(privateUtf8)));
            }
            catch{throw Invalid();}
        }
        // Transfer once to the handshake owner, which must clear its copy after use.
        public byte[] TakeViewerKey()
        {lock(gate){if(disposed || taken)throw Invalid();taken=true;var result=key;key=null;return result;}}
        public void Dispose(){lock(gate){if(disposed)return;disposed=true;if(key!=null){Array.Clear(key,0,key.Length);key=null;}}}
        public override string ToString()=>"ViewerBootstrap(private)";
    }
}

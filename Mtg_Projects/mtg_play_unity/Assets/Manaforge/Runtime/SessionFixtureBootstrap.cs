using System;
using System.IO;
using System.Text;
using Manaforge.Play.Protocol;
using Newtonsoft.Json.Linq;

namespace Manaforge.Play
{
    // Diagnostic only: reissue the known PUBLIC test key after checking/disposing private input.
    public static class SessionFixtureBootstrap
    {
        public static ViewerBootstrap ValidateAndReissue(ViewerBootstrap input)
        {
            byte[] key=null;
            try {
                if(input==null || input.SessionId!="fixture-session" || input.ViewerId!="one" || input.EngineVersion!="fixture-engine"
                    || input.ArtifactManifestSha256!=new string('a',64) || input.ArtworkDirectory!=null)return null;
                key=input.TakeViewerKey();for(int i=0;i<32;i++)if(key[i]!=(byte)i)return null;
                string hex=BitConverter.ToString(key).Replace("-","").ToLowerInvariant();
                var value=new JObject{["viewer_bootstrap_version"]=1,["protocol_version"]=1,["endpoint"]=new JObject{["host"]="127.0.0.1",["port"]=input.Port},
                    ["session_id"]="fixture-session",["viewer_id"]="one",["engine_version"]="fixture-engine",["artifact_manifest_sha256"]=new string('a',64),["viewer_key_hex"]=hex,["artwork"]=JValue.CreateNull()};
                return ViewerBootstrap.Parse(Encoding.UTF8.GetBytes(value.ToString()));
            }
            catch(IOException){return null;}
            finally{if(key!=null)Array.Clear(key,0,key.Length);input?.Dispose();}
        }
    }
}

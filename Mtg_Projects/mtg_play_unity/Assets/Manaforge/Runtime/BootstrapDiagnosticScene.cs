using System;
using System.Collections;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Manaforge.Play.Protocol;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace Manaforge.Play
{
    // Explicit headless fixture probe. Never mounts a game, artwork provider or seat UI.
    public sealed class BootstrapDiagnosticScene : MonoBehaviour
    {
        private ViewerBootstrapPipe pipe;private CancellationTokenSource cancellation;
        private Task<ViewerBootstrap> reading;private Task closing;private string output;
        public static bool IsPublicFixture(ViewerBootstrap bootstrap)
        {
            if(bootstrap==null || bootstrap.SessionId!="fixture-session" || bootstrap.ViewerId!="seat-one"
                || bootstrap.EngineVersion!="fixture-engine" || bootstrap.ArtifactManifestSha256!=new string('a',64)
                || bootstrap.Port!=43210 || bootstrap.ArtworkDirectory!=null)return false;
            byte[] key=null;
            try{key=bootstrap.TakeViewerKey();for(int i=0;i<32;i++)if(key[i]!=(byte)i)return false;return true;}
            catch(IOException){return false;}
            finally{if(key!=null)Array.Clear(key,0,key.Length);}
        }
        private bool Report(string name,string code)
        {
            try {
                var value=new JObject{["probe_version"]=1,["fixture_only"]=true,["code"]=code};
                string path=Path.Combine(output,name+".json");File.WriteAllText(path+".tmp",value.ToString());File.Move(path+".tmp",path);return true;
            }
            catch{return false;}
        }
        private void Fail(string code){Report("failed",code);Application.Quit(1);}
        private static string Code(Task task)=>task.Exception?.GetBaseException() is ViewerBootstrapPipe.PipeException error?error.Code:"BOOTSTRAP_DIAGNOSTIC_FAILED";
        private IEnumerator Start()
        {
            output=ArtworkFixtureScene.Argument("-manaforgeBootstrapDiagnostic");
            try{Directory.CreateDirectory(output);cancellation=new CancellationTokenSource();pipe=ViewerBootstrapPipe.FromStandardInput();reading=pipe.ReadBootstrapAsync(5000,cancellation.Token);}
            catch{Fail("BOOTSTRAP_DIAGNOSTIC_START_FAILED");yield break;}
            while(!reading.IsCompleted)yield return null;
            if(reading.Status!=TaskStatus.RanToCompletion){Fail(Code(reading));yield break;}
            bool fixture;using(var bootstrap=reading.Result)fixture=IsPublicFixture(bootstrap);
            if(!fixture){Fail("BOOTSTRAP_DIAGNOSTIC_CONTEXT");yield break;}
            if(!Report("received","BOOTSTRAP_RECEIVED")){Application.Quit(1);yield break;}
            try{closing=pipe.WaitForOwnerCloseAsync(cancellation.Token);}catch{Fail("BOOTSTRAP_DIAGNOSTIC_STATE");yield break;}
            while(!closing.IsCompleted)yield return null;
            if(closing.Status!=TaskStatus.RanToCompletion){Fail(Code(closing));yield break;}
            Application.Quit(Report("closed","OWNER_EOF")?0:1);
        }
        private void OnDestroy()
        {
            cancellation?.Cancel();pipe?.Dispose();
            reading?.ContinueWith(task=>{if(task.Status==TaskStatus.RanToCompletion)task.Result.Dispose();else _=task.Exception;},TaskScheduler.Default);
            closing?.ContinueWith(task=>{_=task.Exception;},TaskScheduler.Default);cancellation?.Dispose();
        }
    }
}

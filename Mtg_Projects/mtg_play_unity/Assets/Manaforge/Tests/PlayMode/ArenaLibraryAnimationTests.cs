using System.Collections;
using System.IO;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using UnityEngine.UIElements;
namespace Manaforge.Play.Tests
{
    public sealed class ArenaLibraryAnimationTests
    {
        [UnityTest] public IEnumerator ConfirmedCountFlightCancelsForReducedMotionAndDisposal()
        {
            var node=new GameObject("Library animation test");var settings=ScriptableObject.CreateInstance<PanelSettings>();settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");
            var doc=node.AddComponent<UIDocument>();doc.panelSettings=settings;var root=doc.rootVisualElement;root.style.width=1280;root.style.height=720;
            var local=new Label();var opponent=new Label();root.Add(local);root.Add(opponent);bool reduced=false;
            var motion=new ArenaLibraryMotion(root,player=>new LibraryMotionAnchors(new Vector2(40,100),new Vector2(600,600)),()=>reduced);
            try{
                var envelope=(JObject)JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/receive-history-v1.json")))["cases"][0]["steps"][0]["envelope"].DeepClone();
                var snapshot=envelope["body"]["snapshot"];snapshot["phase"]="PRECOMBAT_MAIN";var player=snapshot["players"][0];player["library_count"]=50;player["hand_count"]=6;
                System.Func<ProjectedDecisionFrame> frame=()=>ViewerDecisionProjection.ParseSnapshot(envelope.ToString(),"fixture-session","one",0,true);
                yield return null;motion.Observe(frame());Assert.That(root.Query<VisualElement>(className:"library-flight").ToList().Count,Is.Zero);
                snapshot["revision"]=8;player["library_count"]=48;player["hand_count"]=8;motion.Observe(frame());Assert.That(root.Query<VisualElement>(className:"library-flight").ToList().Count,Is.EqualTo(2));
                reduced=true;yield return new WaitForSecondsRealtime(.05f);Assert.That(root.Query<VisualElement>(className:"library-flight").ToList().Count,Is.Zero);
                snapshot["revision"]=9;player["library_count"]=47;player["hand_count"]=9;motion.Observe(frame());Assert.That(root.Query<VisualElement>(className:"library-flight").ToList().Count,Is.Zero);
                reduced=false;snapshot["revision"]=10;player["library_count"]=46;player["hand_count"]=10;motion.Observe(frame());Assert.That(root.Query<VisualElement>(className:"library-flight").ToList().Count,Is.EqualTo(1));
                motion.Dispose();yield return new WaitForSecondsRealtime(.05f);Assert.That(root.Query<VisualElement>(className:"library-flight").ToList().Count,Is.Zero);
            }finally{motion.Dispose();Object.Destroy(node);Object.Destroy(settings);}yield return null;
        }
    }
}

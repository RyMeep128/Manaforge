using System;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using Manaforge.Play.Protocol;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine;
namespace Manaforge.Play.Tests
{
    public sealed class ReceiveHistoryTests
    {
        private static JObject Corpus() => JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,
            "../../mtg_play/protocol/fixtures/receive-history-v1.json")));
        private static string Snapshot() => Corpus()["cases"][0]["steps"][0]["envelope"].ToString();
        [Test] public void SharedOrderedStreamCasesRejectReplayConflictsRollbackAndOverflow()
        {
            foreach(var test in Corpus()["cases"])
            {
                using var history=new ReceiveHistory("fixture-session","one",(bool)test["fixture_mode"],(int)test["capacity"]);
                foreach(var step in test["steps"])
                {
                    string outcome=(string)step["outcome"],text=step["envelope"].ToString();
                    if(outcome=="applied" || outcome=="duplicate") Assert.That(history.Accept(text)!=null,Is.EqualTo(outcome=="applied"),(string)test["name"]);
                    else {
                        var error=Assert.Throws<WireEnvelope.EnvelopeException>(()=>history.Accept(text),(string)test["name"]);
                        Assert.That(error.Code,Is.EqualTo(outcome),(string)test["name"]);Assert.That(error.Message,Is.EqualTo(error.Code));
                    }
                }
            }
        }
        [Test] public void MutatingReturnedTreesCannotRewriteRetainedIdentity()
        {
            using var history=new ReceiveHistory("fixture-session","one",true);
            var tree=history.Accept(Snapshot());tree["body"]["snapshot"]["turn"]=99;
            Assert.That(history.Accept(Snapshot()),Is.Null);
            Assert.That(history.Revision,Is.EqualTo(7));Assert.That(history.Count,Is.EqualTo(1));
        }
        [Test] public void ConcurrentDuplicateIsAdmittedOnlyOnce()
        {
            using var history=new ReceiveHistory("fixture-session","one",true);
            string text=Snapshot();
            var tasks=Enumerable.Range(0,8).Select(_=>Task.Run(()=>history.Accept(text)!=null)).ToArray();
            Assert.That(Task.WaitAll(tasks,5000),Is.True);
            Assert.That(tasks.Count(task=>task.Result),Is.EqualTo(1));Assert.That(history.Count,Is.EqualTo(1));
        }
        [Test] public void DisposalClearsHistoryAndRefusesFurtherAdmission()
        {
            var history=new ReceiveHistory("fixture-session","one",true);history.Accept(Snapshot());history.Dispose();history.Dispose();
            Assert.That(history.Count,Is.Zero);
            Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>history.Accept(Snapshot())).Code,Is.EqualTo("HISTORY_CLOSED"));
        }
        [TestCase(0)] [TestCase(65537)] public void InvalidCapacityCannotDisableReplayProtection(int capacity) =>
            Assert.Throws<ArgumentException>(()=>new ReceiveHistory("fixture-session","one",true,capacity));
    }
}

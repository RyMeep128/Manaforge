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
    public sealed class ViewerAuthenticationTests
    {
        private static JObject Corpus() => JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,
            "../../mtg_play/protocol/fixtures/viewer-auth-v1.json")));
        private static byte[] Key(JObject corpus) => Enumerable.Range(0,32).Select(i=>Convert.ToByte(((string)corpus["viewer_key_hex"]).Substring(i*2,2),16)).ToArray();
        [Test] public void BothRolesMatchIndependentKnownAnswersAndCannotReplay()
        {
            var corpus=Corpus();
            foreach(var test in corpus["positive"])
            {
                string text=test["envelope"].ToString();
                Assert.That(ViewerAuthentication.ComputeProof(text,Key(corpus)),Is.EqualTo((string)test["envelope"]["body"]["proof"]));
                using var verifier=new ViewerAuthentication.Verifier(text,Key(corpus));
                Assert.That(verifier.Verify(text),Is.True);
                Assert.That(verifier.Verify(text),Is.False);
            }
        }
        [Test] public void TamperedBindingsFailAndConsumeTheAttempt()
        {
            var corpus=Corpus(); string expected=corpus["positive"][0]["envelope"].ToString();
            foreach(var test in corpus["negative"])
            {
                using var verifier=new ViewerAuthentication.Verifier(expected,Key(corpus));
                Assert.That(verifier.Verify(test["envelope"].ToString()),Is.False,(string)test["name"]);
                Assert.That(verifier.Verify(expected),Is.False,"Failure closes the attempt");
            }
        }
        [Test] public void ConcurrentAttemptsAuthorizeAtMostOnce()
        {
            var corpus=Corpus(); string expected=corpus["positive"][0]["envelope"].ToString();
            using var verifier=new ViewerAuthentication.Verifier(expected,Key(corpus));
            bool first=false, second=false;
            Parallel.Invoke(()=>first=verifier.Verify(expected),()=>second=verifier.Verify(expected));
            Assert.That(new[] {first,second}.Count(value=>value),Is.EqualTo(1));
        }
        [Test] public void WrongKeyAndDisposedVerifierNeverAuthorize()
        {
            var corpus=Corpus(); string expected=corpus["positive"][0]["envelope"].ToString();
            using var wrong=new ViewerAuthentication.Verifier(expected,new byte[32]);
            Assert.That(wrong.Verify(expected),Is.False);
            using var disposed=new ViewerAuthentication.Verifier(expected,Key(corpus));
            disposed.Dispose(); Assert.That(disposed.Verify(expected),Is.False);
            Assert.Throws<ArgumentException>(()=>ViewerAuthentication.ComputeProof(expected,new byte[31]));
        }
    }
}

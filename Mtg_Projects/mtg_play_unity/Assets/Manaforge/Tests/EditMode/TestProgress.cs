using System;
using System.IO;
using NUnit.Framework.Interfaces;
using UnityEngine;
using UnityEngine.TestRunner;

[assembly: TestRunCallback(typeof(Manaforge.Play.Tests.TestProgress))]

namespace Manaforge.Play.Tests
{
    // Persist only test identities/results so a stalled CI process remains diagnosable.
    public sealed class TestProgress : ITestRunCallback
    {
        private static string PathName => Path.GetFullPath(Path.Combine(Application.dataPath, "../Artifacts/test-progress.log"));
        private static void Record(string message)
        {
            if (Environment.GetEnvironmentVariable("GITHUB_ACTIONS") != "true") return;
            Directory.CreateDirectory(Path.GetDirectoryName(PathName));
            File.AppendAllText(PathName, DateTime.UtcNow.ToString("O") + " " + message + Environment.NewLine);
        }
        public void RunStarted(ITest testsToRun) => Record("RUN START");
        public void RunFinished(ITestResult result) => Record("RUN FINISH " + result.ResultState);
        public void TestStarted(ITest test) { if (!test.IsSuite) Record("START " + test.FullName); }
        public void TestFinished(ITestResult result) { if (!result.Test.IsSuite) Record("FINISH " + result.Test.FullName + " " + result.ResultState); }
    }
}

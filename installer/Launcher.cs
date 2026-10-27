// Small .NET Framework GUI launcher: no Python runtime, shell, or version scanning.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Web.Script.Serialization;
using System.Windows.Forms;

class Launcher {
    [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
    static extern int SetCurrentProcessExplicitAppUserModelID(string id);
    public class Stamp { public long size; public long modified; public string sha256; }
    public class Entry { public string version; public string sha256; public Dictionary<string, Stamp> files; }
    public class State { public Entry[] installations; }
    static JavaScriptSerializer Json() { return new JavaScriptSerializer { MaxJsonLength = 16777216 }; }
    static string Digest(string path) {
        using (var hash = SHA256.Create()) using (var stream = File.OpenRead(path))
            return BitConverter.ToString(hash.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
    }
    static bool ValidPayload(string directory, Entry entry) {
        if (entry.files == null || !entry.files.ContainsKey("Manaforge.exe")) return false;
        foreach (var item in entry.files) {
            string name = item.Key;
            if (String.IsNullOrEmpty(name) || name.Contains('\\') || name.Contains(':') ||
                name.StartsWith("/") || name.Split('/').Any(part => part == ".." || part == "")) return false;
            string path = Path.Combine(directory, name.Replace('/', Path.DirectorySeparatorChar));
            var file = new FileInfo(path);
            var stamp = item.Value;
            if (stamp == null || stamp.sha256 == null || !Regex.IsMatch(stamp.sha256, "^[a-f0-9]{64}$") ||
                !file.Exists || Linked(path) || file.Length != stamp.size) return false;
            // Only changed files need rehashing; unchanged dependencies add no bulk reads.
            if ((name == "Manaforge.exe" || file.LastWriteTimeUtc.ToFileTimeUtc() != stamp.modified) &&
                Digest(path) != stamp.sha256) return false;
        }
        return entry.files["Manaforge.exe"].sha256 == entry.sha256;
    }
    static bool Linked(string path) {
        for (var dir = new FileInfo(path) as FileSystemInfo; dir != null;) {
            if ((dir.Attributes & FileAttributes.ReparsePoint) != 0) return true;
            var parent = dir is FileInfo ? ((FileInfo)dir).Directory : ((DirectoryInfo)dir).Parent;
            dir = parent;
        }
        return false;
    }
    // Windows CommandLineToArgvW quoting, including empty arguments and trailing slashes.
    public static string Quote(string arg) {
        var result = new StringBuilder("\"");
        int slashes = 0;
        foreach (char c in arg) {
            if (c == '\\') { slashes++; continue; }
            result.Append('\\', c == '"' ? slashes * 2 + 1 : slashes);
            result.Append(c);
            slashes = 0;
        }
        result.Append('\\', slashes * 2);
        return result.Append('"').ToString();
    }
    [STAThread]
    static int Main(string[] args) {
        SetCurrentProcessExplicitAppUserModelID("Manaforge.Desktop");
        string root = AppDomain.CurrentDomain.BaseDirectory;
        var attempted = new HashSet<string>();
        foreach (string metadata in new[] { "active-install.json", "active-install.backup.json" }) {
            try {
                var state = Json().Deserialize<State>(File.ReadAllText(Path.Combine(root, metadata)));
                if (state == null || state.installations == null || state.installations.Length > 2) continue;
                foreach (var entry in state.installations) {
                    try {
                        if (entry == null || entry.version == null || entry.sha256 == null ||
                            !Regex.IsMatch(entry.version, @"^\d+\.\d+\.\d+-(alpha|beta)\.\d+$") ||
                            !Regex.IsMatch(entry.sha256, "^[a-f0-9]{64}$") || attempted.Contains(entry.version)) continue;
                        string directory = Path.Combine(root, "versions", entry.version);
                        string exe = Path.Combine(directory, "Manaforge.exe");
                        if (!File.Exists(exe) || Linked(exe) || !Directory.Exists(Path.Combine(directory, "_internal"))) continue;
                        var receipt = Json().Deserialize<Dictionary<string, object>>(
                            File.ReadAllText(Path.Combine(directory, "manaforge-install.json")));
                        if ((string)receipt["version"] != entry.version) continue;
                        if (!ValidPayload(directory, entry)) continue;
                        attempted.Add(entry.version);
                        var process = Process.Start(new ProcessStartInfo(exe, String.Join(" ", args.Select(Quote))) {
                            UseShellExecute = false, WorkingDirectory = directory
                        });
                        // Catch immediate loader failures while keeping the launch itself asynchronous.
                        if (process == null) continue;
                        using (process) { if (process.WaitForExit(750) && process.ExitCode != 0) continue; }
                        return 0;
                    } catch (Exception) { /* Try the last verified installation. */ }
                }
            } catch (Exception) { /* Backup record may survive interrupted metadata writes. */ }
        }
        MessageBox.Show("No usable Manaforge installation was found. Run Manaforge-Setup.exe again to repair the application. Your decks and settings have not been removed.",
            "Manaforge needs repair", MessageBoxButtons.OK, MessageBoxIcon.Error);
        return 1;
    }
}

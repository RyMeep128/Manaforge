using System;
using System.Collections.Generic;
using System.Threading;
using UnityEngine;

namespace Manaforge.Play
{
    // Public fixture resources only. Borrowers must clear views before disposal.
    // No IO/decode here: only validated raw pixel upload on the creating Unity thread.
    public sealed class FixtureTextures : IDisposable
    {
        private readonly int thread = Thread.CurrentThread.ManagedThreadId;
        private readonly Dictionary<ArtworkFixture.Asset, Texture2D> textures = new Dictionary<ArtworkFixture.Asset, Texture2D>();
        private readonly long budget;
        private bool disposed;
        public long Bytes { get; private set; }
        public int Count => textures.Count;
        public FixtureTextures(long budgetBytes = 64 * 1024 * 1024)
        {
            if (budgetBytes < 1 || budgetBytes > 64 * 1024 * 1024) throw new ArgumentOutOfRangeException(nameof(budgetBytes));
            budget = budgetBytes;
        }
        private void CheckThread()
        {
            if (Thread.CurrentThread.ManagedThreadId != thread) throw new InvalidOperationException("FIXTURE_TEXTURE_THREAD");
        }
        public Texture2D Get(ArtworkFixture.Asset asset)
        {
            CheckThread();
            if (disposed) throw new ObjectDisposedException(nameof(FixtureTextures));
            if (asset == null) return null;
            if (textures.TryGetValue(asset, out var existing)) return existing;
            long size = (long)asset.Width * asset.Height * 4;
            if (size > budget - Bytes) throw new InvalidOperationException("FIXTURE_TEXTURE_BUDGET");
            var texture = new Texture2D(asset.Width, asset.Height, TextureFormat.RGBA32, false, false)
            { name = "Public fixture artwork", wrapMode = TextureWrapMode.Clamp, filterMode = FilterMode.Bilinear };
            try
            {
                texture.LoadRawTextureData(asset.CopyPixels());
                texture.Apply(false, true); // release Unity CPU copy; no mip allocation
                textures.Add(asset, texture);
                Bytes += size;
                return texture;
            }
            catch { Release(texture); throw; }
        }
        private static void Release(Texture2D texture)
        {
            if (Application.isPlaying) UnityEngine.Object.Destroy(texture);
            else UnityEngine.Object.DestroyImmediate(texture); // owned transient preview/test texture only
        }
        public void Dispose()
        {
            CheckThread();
            if (disposed) return;
            disposed = true;
            foreach (var texture in textures.Values) Release(texture);
            textures.Clear(); Bytes = 0;
        }
    }
}

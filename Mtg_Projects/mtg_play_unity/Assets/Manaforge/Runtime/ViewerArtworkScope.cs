using System;
using System.Collections.Generic;
using System.Threading;
using UnityEngine;

namespace Manaforge.Play
{
    // Private to one viewer epoch. Creates its own textures; cannot take/destroy borrowed public textures.
    public sealed class ViewerArtworkScope : IDisposable
    {
        private readonly int thread=Thread.CurrentThread.ManagedThreadId;
        private readonly Dictionary<string,Texture2D> textures=new Dictionary<string,Texture2D>(StringComparer.Ordinal);
        private readonly long budget;
        private ViewerSurfaceTicket owner;
        private bool disposed;
        public long Bytes {get;private set;}
        public int Count=>textures.Count;
        public ViewerArtworkScope(long budgetBytes=64*1024*1024)
        {if(budgetBytes<1 || budgetBytes>64*1024*1024)throw new ArgumentOutOfRangeException(nameof(budgetBytes));budget=budgetBytes;}
        private void ThreadOnly(){if(thread!=Thread.CurrentThread.ManagedThreadId)throw new InvalidOperationException("ARTWORK_SCOPE_THREAD");}
        internal void CheckUnowned(){ThreadOnly();if(disposed || owner!=null)throw new InvalidOperationException("ARTWORK_SCOPE_UNAVAILABLE");}
        internal void Claim(ViewerSurfaceTicket ticket){CheckUnowned();owner=ticket;}
        internal bool TryUpload(PreparedCardArtwork prepared,out Texture2D texture)
        {
            ThreadOnly();texture=null;
            if(disposed || !ReferenceEquals(owner,prepared.Request.Ticket))return false;
            string key=prepared.Width+"x"+prepared.Height+":"+prepared.Digest;
            if(textures.TryGetValue(key,out texture))return true;
            long bytes=(long)prepared.Width*prepared.Height*4;
            if(textures.Count>=256 || bytes>budget-Bytes)return false;
            var created=new Texture2D(prepared.Width,prepared.Height,TextureFormat.RGBA32,false,false)
                {name="Viewer artwork",wrapMode=TextureWrapMode.Clamp,filterMode=FilterMode.Bilinear};
            byte[] upload=null;
            try {
                upload=prepared.CopyPixels();created.LoadRawTextureData(upload);created.Apply(false,true);
                textures.Add(key,created);Bytes+=bytes;texture=created;return true;
            }
            catch{Release(created);throw new InvalidOperationException("ARTWORK_UPLOAD_FAILED");}
            finally{if(upload!=null)Array.Clear(upload,0,upload.Length);}
        }
        private static void Release(Texture2D texture)
        {if(Application.isPlaying)UnityEngine.Object.Destroy(texture);else UnityEngine.Object.DestroyImmediate(texture);}
        public void Dispose()
        {
            ThreadOnly();if(disposed)return;disposed=true;owner=null;
            foreach(var texture in textures.Values)Release(texture);textures.Clear();Bytes=0;
        }
    }
}

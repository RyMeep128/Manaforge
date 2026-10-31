using System;
using System.Security.Cryptography;

namespace Manaforge.Play
{
    // Issued only by a current surface. Contains no texture, file path or persistent deck identity.
    public sealed class ViewerArtworkRequest
    {
        internal ViewerSurfaceTicket Ticket {get;}
        public string ObjectId {get;} public long Revision {get;}
        public string OracleId {get;} public string PrintingId {get;}
        internal ViewerArtworkRequest(ViewerSurfaceTicket ticket,ProjectedCard card)
        {Ticket=ticket;ObjectId=card.ObjectId;Revision=card.Context.Revision;OracleId=card.Printing.OracleId;PrintingId=card.Printing.PrintingId;}
    }
    // Ephemeral metadata from the trusted existing Core catalog, not a second card database.
    public sealed class CatalogArtworkFace
    {
        public string OracleId {get;} public string PrintingId {get;} public string FaceKey {get;}
        public string Layout {get;} public string PrintedTypeLine {get;}
        public int FaceCount {get;} public bool StandardCompatible {get;}
        public CatalogArtworkFace(string oracle,string printing,string face,string layout,int faceCount,bool standardCompatible,string printedTypeLine)
        {OracleId=oracle;PrintingId=printing;FaceKey=face;Layout=layout;FaceCount=faceCount;StandardCompatible=standardCompatible;PrintedTypeLine=printedTypeLine;}
    }
    public sealed class PreparedCardArtwork : IDisposable
    {
        private readonly object gate=new object();
        private byte[] pixels;
        public ViewerArtworkRequest Request {get;}
        public CardVisualIdentity Identity {get;}
        public CardCompactProfile Profile {get;}
        public int Width {get;} public int Height {get;}
        internal string Digest {get;}
        public bool IsDisposed {get{lock(gate)return pixels==null;}}
        private PreparedCardArtwork(ViewerArtworkRequest request,CatalogArtworkFace catalog,int width,int height,byte[] bytes)
        {
            Request=request;Width=width;Height=height;pixels=(byte[])bytes.Clone();
            using(var hash=SHA256.Create())Digest=BitConverter.ToString(hash.ComputeHash(pixels)).Replace("-","");
            Identity=VisualPrintingPolicy.Resolve(false,new VisualPrintingCandidate(catalog.OracleId,catalog.PrintingId,catalog.FaceKey,true,true),Array.Empty<VisualPrintingCandidate>());
            Profile=CardCompactProfile.FromMetadata("normal",catalog.PrintedTypeLine);
        }
        // Worker-side: caller already used Core's decoder. RGBA8 rows must be bottom-left origin.
        // This method never reads files, downloads images, decodes PNGs or touches Unity graphics.
        public static PreparedCardArtwork Prepare(ViewerArtworkRequest request,CatalogArtworkFace catalog,int width,int height,byte[] rgba)
        {
            if(request==null || catalog==null)throw new ArgumentException("ARTWORK_CONTEXT");
            if(catalog.OracleId!=request.OracleId || catalog.PrintingId!=request.PrintingId)
                throw new ArgumentException("ARTWORK_IDENTITY");
            if(catalog.Layout!="normal" || catalog.FaceCount!=1 || !catalog.StandardCompatible || string.IsNullOrWhiteSpace(catalog.FaceKey)
                || catalog.FaceKey.Length>1024 || string.IsNullOrWhiteSpace(catalog.PrintedTypeLine))
                throw new ArgumentException("ARTWORK_FACE_UNSUPPORTED");
            var profile=CardCompactProfile.FromMetadata("normal",catalog.PrintedTypeLine);
            if(profile!=null && !string.IsNullOrEmpty(profile.Kind))throw new ArgumentException("ARTWORK_FACE_UNSUPPORTED");
            if(width<1 || height<1 || width>1024 || height>1024 || rgba==null || rgba.Length!=(long)width*height*4)
                throw new ArgumentException("ARTWORK_PIXELS");
            return new PreparedCardArtwork(request,catalog,width,height,rgba);
        }
        internal byte[] CopyPixels(){lock(gate){if(pixels==null)throw new ObjectDisposedException(nameof(PreparedCardArtwork));return (byte[])pixels.Clone();}}
        public void Dispose(){lock(gate){if(pixels!=null){Array.Clear(pixels,0,pixels.Length);pixels=null;}}}
    }
}

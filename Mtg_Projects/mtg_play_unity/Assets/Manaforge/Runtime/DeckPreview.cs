using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Manaforge.Play.Protocol;
using Newtonsoft.Json.Linq;

namespace Manaforge.Play
{
    // Immutable preview projection only. Entry IDs are deck entries, never engine object IDs.
    public sealed class DeckPreview : IDisposable
    {
        public sealed class Card
        {
            public string EntryId {get;} public int Quantity {get;} public string Section {get;}
            public string Oracle {get;} public string Printing {get;} public string ArtworkPrinting {get;} public CardDisplayValues Values {get;}
            internal Card(JToken row){EntryId=Text(row["entry_id"],128);Quantity=Number(row["quantity"],10000);Section=Text(row["section"],128);
                Oracle=Optional(row["oracle_id"]);Printing=Optional(row["printing_id"]);ArtworkPrinting=Optional(row["artwork_printing_id"]);
                string power=Optional(row["power"]),toughness=Optional(row["toughness"]);
                Values=new CardDisplayValues(Text(row["name"]),Optional(row["mana_cost"]),Optional(row["type_line"]),Optional(row["rules_text"]),
                    power==null || toughness==null?null:power+"/"+toughness,"PRINTED PREVIEW",loyalty:Optional(row["loyalty"]),defense:Optional(row["defense"]));}
        }
        public sealed class Startup
        {
            public string Directory {get;private set;} public string DeckPin {get;private set;}
            public string ArtworkPin {get;private set;} public string PreviewId {get;private set;}
            public static Startup Parse(byte[] bytes) {
                if(bytes==null || bytes.Length>16384)throw Invalid();
                var obj=WireEnvelope.ParseObject(new UTF8Encoding(false,true).GetString(bytes));
                Fields(obj,"deck_preview_version","mode","directory","deck_sha256","artwork_sha256","preview_id");Version(obj);
                string path=Text(obj["directory"],4096);
                if(!Path.IsPathFullyQualified(path) || path.StartsWith("\\\\") || path.StartsWith("//"))throw Invalid();
                string deck=Text(obj["deck_sha256"]),art=Text(obj["artwork_sha256"]),id=Text(obj["preview_id"]);
                if(!Regex.IsMatch(deck,"^[0-9a-f]{64}$") || !Regex.IsMatch(art,"^[0-9a-f]{64}$") || !Regex.IsMatch(id,"^[0-9a-f]{32}$"))throw Invalid();
                return new Startup{Directory=path,DeckPin=deck,ArtworkPin=art,PreviewId=id};
            }
        }
        public string Name {get;private set;} public string Format {get;private set;} public int TotalEntries {get;private set;}
        public IReadOnlyList<Card> Cards {get;private set;} public CoreArtworkBundle Artwork {get;private set;}
        public string Directory {get;private set;}
        private static IOException Invalid()=>new IOException("DECK_PREVIEW_INVALID");
        private static void Fields(JToken value,params string[] fields) {
            if(!(value is JObject obj) || !obj.Properties().Select(p=>p.Name).OrderBy(n=>n).SequenceEqual(fields.OrderBy(n=>n)))throw Invalid();
        }
        private static string Text(JToken token,int maximum=16384) {
            if(token?.Type!=JTokenType.String || string.IsNullOrWhiteSpace((string)token) || ((string)token).Length>maximum
                || ((string)token).Any(c=>char.IsControl(c) && c!='\n' && c!='\r' && c!='\t'))throw Invalid();return (string)token;
        }
        private static string Optional(JToken token) {
            if(token?.Type==JTokenType.Null)return null;
            if(token?.Type!=JTokenType.String || ((string)token).Length>16384 || ((string)token).Any(c=>char.IsControl(c) && c!='\n' && c!='\r' && c!='\t'))throw Invalid();
            return (string)token;
        }
        private static int Number(JToken token,int maximum) {
            if(token?.Type!=JTokenType.Integer || (long)token<1 || (long)token>maximum)throw Invalid();return (int)token;
        }
        private static void Version(JToken value){if(Number(value["deck_preview_version"],1)!=1 || Text(value["mode"])!="deck_preview")throw Invalid();}
        public static void ValidateDocument(byte[] bytes) {ParseDocument(bytes);}
        private static DeckPreview ParseDocument(byte[] bytes) {
            if(bytes==null || bytes.Length<1 || bytes.Length>1024*1024)throw Invalid();
            var obj=WireEnvelope.ParseObject(new UTF8Encoding(false,true).GetString(bytes));
            Fields(obj,"deck_preview_version","mode","deck_name","format","total_entries","cards");Version(obj);
            string format=Text(obj["format"]);if(format!="freeform" && format!="commander")throw Invalid();
            int total=Number(obj["total_entries"],2048);
            if(!(obj["cards"] is JArray rows) || rows.Count<1 || rows.Count>24 || rows.Count>total)throw Invalid();
            var cards=new List<Card>();var seen=new HashSet<string>(StringComparer.Ordinal);
            foreach(var row in rows){Fields(row,"entry_id","quantity","section","oracle_id","printing_id","artwork_printing_id","name","mana_cost","type_line","rules_text","power","toughness","loyalty","defense");
                var card=new Card(row);if(!seen.Add(card.EntryId))throw Invalid();cards.Add(card);}
            return new DeckPreview{Name=Text(obj["deck_name"],1024),Format=format,TotalEntries=total,Cards=cards.AsReadOnly()};
        }
        public static Task<DeckPreview> LoadAsync(Startup startup,CancellationToken cancellation)=>Task.Run(async()=>{
            byte[] bytes=null;DeckPreview result=null;
            try {
                bytes=CoreArtworkBundle.Read(startup.Directory,"deck.json",1024*1024,cancellation);
                if(CoreArtworkBundle.Digest(bytes)!=startup.DeckPin)throw Invalid();result=ParseDocument(bytes);result.Directory=startup.Directory;
                result.Artwork=await CoreArtworkBundle.OpenPreviewAsync(Path.Combine(startup.Directory,"artwork"),startup.ArtworkPin,startup.PreviewId,cancellation);
                cancellation.ThrowIfCancellationRequested();return result;
            }catch{result?.Dispose();throw Invalid();}finally{if(bytes!=null)Array.Clear(bytes,0,bytes.Length);}
        },cancellation);
        public void Dispose(){Artwork?.Dispose();Artwork=null;Cards=Array.Empty<Card>();Name=null;}
    }
}

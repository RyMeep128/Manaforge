using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Manaforge.Play.Protocol;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // Product preview: same CardView bricks, no fake snapshots, legal actions or game zones.
    public sealed class DeckPreviewScene : MonoBehaviour
    {
        private readonly CancellationTokenSource cancel=new CancellationTokenSource();
        private readonly List<CardView> views=new List<CardView>();
        private readonly Dictionary<string,Texture2D> textures=new Dictionary<string,Texture2D>();
        private readonly Dictionary<string,CatalogArtworkFace> catalogs=new Dictionary<string,CatalogArtworkFace>();
        private readonly Dictionary<string,CardVisualIdentity> identities=new Dictionary<string,CardVisualIdentity>();
        private ViewerBootstrapPipe pipe;private Task lifeline;private DeckPreview deck;private PanelSettings settings;
        private CardView inspection,selected;private long textureBytes;
        private Task<DeckPreview> loading;private Task<CoreArtworkBundle.PreviewPixels> imageJob;
        private static Label Label(string text,int size=15){var value=new Label(text){enableRichText=false};value.style.color=Color.white;value.style.fontSize=size;return value;}
        private IEnumerator Start() {
            settings=ScriptableObject.CreateInstance<PanelSettings>();settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");
            settings.scaleMode=PanelScaleMode.ScaleWithScreenSize;settings.referenceResolution=new Vector2Int(1366,768);
            var doc=gameObject.AddComponent<UIDocument>();doc.panelSettings=settings;var root=doc.rootVisualElement;
            root.style.flexGrow=1;root.style.paddingLeft=root.style.paddingRight=20;root.style.paddingTop=16;
            root.style.backgroundColor=new Color(.025f,.055f,.065f);
            root.Add(Label("Deck Preview — Not a Live Game",26));
            var message=Label("Loading your saved deck from the offline cache…");root.Add(message);
            var close=new Button(()=>Application.Quit()){text="Close Preview"};close.style.alignSelf=Align.FlexEnd;root.Add(close);
            Task<DeckPreview.Startup> startup;
            try{pipe=ViewerBootstrapPipe.FromStandardInput();startup=pipe.ReadPayloadAsync(DeckPreview.Startup.Parse,10000,cancel.Token);}
            catch{message.text="Preview startup failed. Close this window and retry from Manaforge.";Application.Quit(1);yield break;}
            while(!startup.IsCompleted)yield return null;
            if(startup.IsFaulted || startup.IsCanceled){Application.Quit(1);yield break;}
            lifeline=pipe.WaitForOwnerCloseAsync(cancel.Token);
            loading=DeckPreview.LoadAsync(startup.Result,cancel.Token);
            while(!loading.IsCompleted)yield return null;
            if(loading.IsFaulted || loading.IsCanceled){Application.Quit(1);yield break;}
            deck=loading.Result;
            message.text=deck.Name+" · "+deck.Format+" · "+deck.Cards.Count+" of "+deck.TotalEntries+" entries · Printed values only";
            root.Add(Label("1v1 table layout preview · No opponent deck is loaded"));
            var table=new VisualElement();table.style.flexDirection=FlexDirection.Row;table.style.flexGrow=1;table.style.marginTop=16;root.Add(table);
            var scroll=new ScrollView(ScrollViewMode.Vertical);scroll.style.flexGrow=1;scroll.style.flexBasis=0;table.Add(scroll);
            var collection=new VisualElement();collection.style.flexDirection=FlexDirection.Row;collection.style.flexWrap=Wrap.Wrap;
            collection.style.backgroundColor=new Color(.045f,.13f,.12f);collection.style.paddingTop=20;collection.style.paddingBottom=20;scroll.Add(collection);
            var inspectScroll=new ScrollView(ScrollViewMode.Vertical);inspectScroll.style.width=370;inspectScroll.style.marginLeft=18;table.Add(inspectScroll);
            inspectScroll.Add(Label("Card inspection · hover or select a card"));inspection=new CardView();inspection.SetPresentation(CardPresentationMode.Full,340);inspectScroll.Add(inspection);
            foreach(var card in deck.Cards) {
                if(!string.IsNullOrEmpty(card.ArtworkPrinting) && !textures.ContainsKey(card.ArtworkPrinting)) {
                    imageJob=deck.Artwork.LoadPreviewAsync(card.Oracle,card.ArtworkPrinting,cancel.Token);
                    while(!imageJob.IsCompleted)yield return null;
                    if(!imageJob.IsFaulted && !imageJob.IsCanceled && imageJob.Result!=null) {
                        using(var pixels=imageJob.Result) {
                            if(textureBytes+pixels.Bytes.Length<=64*1024*1024) {
                                var texture=new Texture2D(pixels.Width,pixels.Height,TextureFormat.RGBA32,false,false){name="Owned deck preview artwork",filterMode=FilterMode.Bilinear,wrapMode=TextureWrapMode.Clamp};
                                texture.LoadRawTextureData(pixels.Bytes);texture.Apply(false,true);textures.Add(card.ArtworkPrinting,texture);textureBytes+=pixels.Bytes.Length;
                                var face=pixels.Catalog;
                                catalogs.Add(card.ArtworkPrinting,face);
                            }
                        }
                        yield return null; // at most one GPU upload each rendered frame
                    }
                }
                if(card.Printing!=null && card.ArtworkPrinting!=null && catalogs.TryGetValue(card.ArtworkPrinting,out var catalog) && !identities.ContainsKey(card.Printing)) {
                    var rendered=new VisualPrintingCandidate(catalog.OracleId,catalog.PrintingId,catalog.FaceKey,catalog.StandardCompatible,true);
                    var original=new VisualPrintingCandidate(card.Oracle,card.Printing,catalog.FaceKey,card.Printing==card.ArtworkPrinting && catalog.StandardCompatible,card.Printing==card.ArtworkPrinting);
                    identities.Add(card.Printing,VisualPrintingPolicy.Resolve(false,original,new[]{rendered}));
                }
                var cell=new VisualElement();cell.style.marginLeft=cell.style.marginRight=8;cell.style.marginBottom=18;
                var view=new CardView();view.SetPresentation(CardPresentationMode.Compact,160);Bind(view,card);views.Add(view);cell.Add(view);
                var quantity=Label("×"+card.Quantity+" · "+card.Section,12);quantity.style.width=160;cell.Add(quantity);collection.Add(cell);
                view.focusable=true;
                view.RegisterCallback<PointerEnterEvent>(_=>Inspect(card));
                view.RegisterCallback<PointerDownEvent>(_=>{selected?.SetSelected(false);selected=view;view.SetSelected(true);Inspect(card);});
                view.RegisterCallback<FocusInEvent>(_=>Inspect(card));
                view.RegisterCallback<KeyDownEvent>(e=>{if(e.keyCode==KeyCode.Return){selected?.SetSelected(false);selected=view;view.SetSelected(true);Inspect(card);}});
            }
            Inspect(deck.Cards[0]);
            var acknowledge=Task.Run(()=>File.WriteAllText(Path.Combine(deck.Directory,"preview-ready.json"),"{\"deck_preview_version\":1,\"ready\":true}",new System.Text.UTF8Encoding(false)),cancel.Token);
            while(!acknowledge.IsCompleted)yield return null;
            if(acknowledge.IsFaulted || acknowledge.IsCanceled){Application.Quit(1);yield break;}
            // Explicit CI diagnostics only. Desktop launch never supplies this switch.
            string screenshot=ArtworkFixtureScene.Argument("-manaforgePreviewScreenshot");
            if(screenshot!=null) {
                for(int frame=0;frame<60;frame++)yield return null;
                yield return new WaitForEndOfFrame();ScreenCapture.CaptureScreenshot(screenshot);
                for(int frame=0;frame<60;frame++)yield return null;
                Application.Quit(0);
            }
        }
        private void Bind(CardView view,DeckPreview.Card card) {
            if(card.Printing!=null && identities.TryGetValue(card.Printing,out var identity) && textures.TryGetValue(card.ArtworkPrinting,out var texture))view.Bind(identity,texture,identity.LayoutProfileId=="standard-v1"?CardCompactProfile.StandardArtCrop:new Rect(0,0,1,1));
            else view.BindUnavailable();
            view.UpdateValues(card.Values);
        }
        private void Inspect(DeckPreview.Card card){Bind(inspection,card);}
        private void Update(){if(lifeline!=null && lifeline.IsCompleted)Application.Quit(lifeline.IsFaulted?1:0);}
        private void OnDestroy() {
            cancel.Cancel();pipe?.Dispose();
            foreach(var view in views)view.Dispose();views.Clear();inspection?.Dispose();selected=null;
            foreach(var texture in textures.Values)Destroy(texture);textures.Clear();catalogs.Clear();identities.Clear();deck?.Dispose();
            // Workers own no graphics. Late success must still clear CPU pixels/indexes.
            if(imageJob!=null)imageJob.ContinueWith(t=>{if(t.Status==TaskStatus.RanToCompletion)t.Result?.Dispose();});
            if(loading!=null)loading.ContinueWith(t=>{if(t.Status==TaskStatus.RanToCompletion)t.Result?.Dispose();});
            if(settings!=null)Destroy(settings);cancel.Dispose();
        }
    }
}

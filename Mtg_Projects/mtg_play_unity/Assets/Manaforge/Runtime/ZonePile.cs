using System;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    public sealed class ZonePile : Label, IDisposable
    {
        private readonly Image art;
        private readonly VisualElement back;
        private readonly Label count, fallback, caption;
        private bool disposed;
        public string OwnerId { get; private set; }
        public string Zone { get; private set; }
        public event Action<string,string> BrowseRequested;
        public static string Title(string zone) => zone=="library" ? "Library" : zone=="graveyard" ? "Graveyard" : "Exile";
        public ZonePile(string zone)
        {
            if(zone!="library" && zone!="graveyard" && zone!="exile")throw new ArgumentException("Unsupported pile zone",nameof(zone));
            Zone=zone; text=""; focusable=true; enableRichText=false; AddToClassList("zone-pile"); AddToClassList("zone-"+zone);
            for(int i=0;i<2;i++){var sheet=new VisualElement{pickingMode=PickingMode.Ignore};sheet.AddToClassList("zone-pile-sheet");sheet.style.left=-3-i*3;sheet.style.top=3+i*3;Add(sheet);}
            back=new VisualElement{name="zone-back",pickingMode=PickingMode.Ignore};back.AddToClassList("zone-pile-face");if(zone=="library")GameplayTheme.Back(back);Add(back);
            art=new Image{name="zone-art",pickingMode=PickingMode.Ignore,scaleMode=ScaleMode.ScaleToFit};art.AddToClassList("zone-pile-face");Add(art);
            fallback=new Label(){name="zone-fallback",enableRichText=false,pickingMode=PickingMode.Ignore};Add(fallback);
            count=new Label("?"){name="zone-count",enableRichText=false,pickingMode=PickingMode.Ignore};Add(count);
            caption=new Label(Title(zone)){name="zone-caption",enableRichText=false,pickingMode=PickingMode.Ignore};Add(caption);
            RegisterCallback<ClickEvent>(Clicked); RegisterCallback<NavigationSubmitEvent>(Submitted);
        }
        private void Clicked(ClickEvent e){if(e.button==0)Browse();}
        private void Submitted(NavigationSubmitEvent e){Browse();e.StopPropagation();}
        public void Browse(){if(!disposed && OwnerId!=null)BrowseRequested?.Invoke(Zone,OwnerId);}
        public void Bind(string ownerId){if(disposed)return;if(ownerId!=OwnerId)ClearBinding();OwnerId=ownerId;}
        // Artwork is borrowed only from the admitted surface, never loaded/owned here.
        public void Present(long? permittedCount, Texture artwork, string visibleName, bool open)
        {
            if(disposed || OwnerId==null)return;
            count.text=permittedCount?.ToString() ?? "?";
            art.image=Zone=="library"?null:artwork;
            fallback.text=Zone=="library" || artwork!=null ? "" : visibleName ?? "Empty";
            EnableInClassList("zone-open",open);
            tooltip=Title(Zone)+" | "+count.text+(Zone=="library"?" cards":" visible cards")+" | Enter to browse";
        }
        public void ClearArtwork(){art.image=null;fallback.text="";}
        public void ClearBinding(){OwnerId=null;ClearArtwork();count.text="?";tooltip="";RemoveFromClassList("zone-open");Blur();}
        public void Dispose(){if(disposed)return;ClearBinding();disposed=true;BrowseRequested=null;UnregisterCallback<ClickEvent>(Clicked);UnregisterCallback<NavigationSubmitEvent>(Submitted);}
    }
}

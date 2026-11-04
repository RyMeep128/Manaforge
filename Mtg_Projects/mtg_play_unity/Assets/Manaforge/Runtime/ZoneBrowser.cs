using System;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // Browser chrome only. The session surface retains its admitted CardViews.
    public sealed class ZoneBrowser : VisualElement, IDisposable
    {
        private readonly Label title, summary;
        private readonly VisualElement tabs;private readonly CardBackView unknown;
        private readonly Button close;private bool disposed;private VisualElement returnFocus;
        public string OwnerId {get; private set;}
        public string Zone {get; private set;}
        public event Action<string,string> BrowseRequested;
        public event Action Closed;
        public ZoneBrowser(ICardBackProvider cardBacks=null)
        {
            name="public-zone-drawer";AddToClassList("mf-zone-browser");
            title=new Label(){name="public-zone-title",enableRichText=false};Add(title);
            tabs=new VisualElement(){name="zone-browser-tabs"};Add(tabs);
            foreach(string zone in new[]{"library","graveyard","exile"}){
                string selected=zone;var tab=new Button(()=>{if(OwnerId!=null)BrowseRequested?.Invoke(selected,OwnerId);}){name="browse-"+zone,text=ZonePile.Title(zone)};GameplayTheme.Button(tab);tabs.Add(tab);
            }
            summary=new Label(){name="zone-browser-summary",enableRichText=false};Add(summary);
            unknown=new CardBackView(cardBacks){name="zone-browser-back"};Add(unknown);
            close=new Button(()=>Closed?.Invoke()){name="close-public-zone",text="Back to battlefield | Esc"};GameplayTheme.Button(close);Add(close);
            ClearBinding();
        }
        public void Present(string owner, string zone, string ownerName, int visible, long? total,int concealedCount=0)
        {
            if(disposed)return;OwnerId=owner;Zone=zone;style.display=DisplayStyle.Flex;
            title.text=ownerName+" / "+ZonePile.Title(zone);
            foreach(var tab in tabs.Children())tab.EnableInClassList("zone-tab-selected",tab.name=="browse-"+zone);
            summary.text=concealedCount>0?visible+" visible cards | "+concealedCount+" face-down cards":zone=="library"?(total.HasValue?total+" cards | ":"Count unavailable | ")+visible+" known. Unrevealed cards and library order remain hidden.":visible==0?"No viewer-visible cards in this zone.":visible+" visible cards | Hover to inspect. Highlighted choices use the current prompt.";
            unknown.Bind(owner);
            unknown.style.display=zone=="library" && visible==0 && total!=0?DisplayStyle.Flex:DisplayStyle.None;
        }
        public void SetReturnFocus(VisualElement origin){if(!disposed)returnFocus=origin;}
        public void ClearBinding(bool restoreFocus=false){OwnerId=Zone=null;unknown.ClearBinding();title.text=summary.text="";style.display=DisplayStyle.None;var origin=returnFocus;returnFocus=null;if(restoreFocus && origin?.panel!=null)origin.Focus();}
        public void Dispose(){if(disposed)return;ClearBinding();disposed=true;BrowseRequested=null;Closed=null;}
    }
}

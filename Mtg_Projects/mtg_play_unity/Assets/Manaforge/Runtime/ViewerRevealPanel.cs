using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    public sealed class ViewerRevealPanel : IDisposable
    {
        private readonly ViewerSessionHost host;private readonly ViewerCardSurface surface;
        private readonly VisualElement overlay,body;private readonly Label title;private readonly Button acknowledge;
        private readonly IVisualElementScheduledItem ticker;private readonly List<Item> items=new List<Item>();
        private ViewerRevealGroup group;private CancellationTokenSource cancel=new CancellationTokenSource();private bool disposed;
        private sealed class Item {public ProjectedObservation Card;public CardView View;public Task<PreparedCardArtwork> Loading;public bool Attempted;}
        public ViewerRevealPanel(VisualElement root,ViewerSessionHost host,ViewerCardSurface surface)
        {
            this.host=host;this.surface=surface;
            overlay=new VisualElement{name="reveal-overlay"};overlay.style.position=Position.Absolute;
            overlay.style.left=overlay.style.right=overlay.style.top=overlay.style.bottom=0;overlay.style.backgroundColor=new Color(0,0,0,.88f);
            var panel=new VisualElement{name="reveal-panel"};panel.AddToClassList("mf-menu");panel.style.position=Position.Absolute;
            panel.style.left=Length.Percent(8);panel.style.right=Length.Percent(8);panel.style.top=Length.Percent(8);panel.style.bottom=Length.Percent(8);overlay.Add(panel);
            title=new Label{enableRichText=false};title.style.fontSize=24;title.style.color=new Color(1,.72f,.38f);panel.Add(title);
            var scroll=new ScrollView(ScrollViewMode.Vertical);scroll.style.flexGrow=1;panel.Add(scroll);
            body=new VisualElement();body.style.flexDirection=FlexDirection.Row;body.style.flexWrap=Wrap.Wrap;scroll.Add(body);
            acknowledge=new Button(()=>{if(group!=null && host.AcknowledgeReveal(group.Id))Clear();}){text="I’ve seen these",name="reveal-acknowledge"};
            GameplayTheme.Button(acknowledge,true);panel.Add(acknowledge);root.Add(overlay);overlay.style.display=DisplayStyle.None;
            surface.Clearing+=Clear;ticker=root.schedule.Execute(Tick).Every(16);
        }
        private static CardDisplayValues Values(ProjectedObservation card,CatalogArtworkFace printed=null,CardCompactProfile profile=null)
            =>new CardDisplayValues(card.Name??"Revealed card",printed?.PrintedManaCost,printed?.PrintedTypeLine,printed?.PrintedRules,null,"Revealed",profile);
        public void Tick()
        {
            if(disposed)return;var next=host.PendingReveal;
            if(!ReferenceEquals(next,group)){
                Clear();group=next;if(group==null)return;
                title.text="Cards revealed ("+group.Cards.Count+")"+(string.IsNullOrWhiteSpace(group.Label)?"":" · "+OpeningHandFan.PlainPrompt(group.Label));
                foreach(var card in group.Cards){
                    var column=new VisualElement();column.style.marginRight=12;column.style.marginBottom=12;
                    var view=new CardView();view.BindUnavailable();view.UpdateValues(Values(card));view.SetPresentation(CardPresentationMode.Full,190);column.Add(view);
                    var inspect=new Button(()=>view.SetPresentation(CardPresentationMode.Full,view.style.width.value.value>200?190:300)){text="Inspect"};GameplayTheme.Button(inspect);column.Add(inspect);body.Add(column);
                    items.Add(new Item{Card=card,View=view});
                }
                overlay.style.display=DisplayStyle.Flex;acknowledge.Focus();
            }
            if(group==null)return;int running=0;
            foreach(var item in items){
                if(item.Loading==null)continue;
                if(!item.Loading.IsCompleted){running++;continue;}
                if(item.Loading.Status==TaskStatus.RanToCompletion && item.Loading.Result!=null){
                    using(var prepared=item.Loading.Result)if(surface.TryApplyRevealArtwork(item.Card,prepared,out var texture)){
                        item.View.Bind(prepared.Identity,texture,prepared.Profile?.Crop??CardCompactProfile.StandardArtCrop);
                        item.View.UpdateValues(Values(item.Card,prepared.Catalog,prepared.Profile));
                    }
                }else{_=item.Loading.Exception;}
                item.Loading=null;
            }
            foreach(var item in items)if(running<4 && !item.Attempted){item.Attempted=true;item.Loading=host.LoadRevealArtworkAsync(item.Card,cancel.Token);running++;}
            overlay.BringToFront();
        }
        private void Clear()
        {
            cancel.Cancel();cancel.Dispose();cancel=new CancellationTokenSource();
            foreach(var item in items){
                item.View.Dispose();if(item.Loading!=null)item.Loading.ContinueWith(task=>{if(task.Status==TaskStatus.RanToCompletion)task.Result?.Dispose();else _=task.Exception;},TaskScheduler.Default);
            }
            items.Clear();body.Clear();group=null;overlay.style.display=DisplayStyle.None;
        }
        public void Dispose(){if(disposed)return;Clear();disposed=true;cancel.Dispose();ticker.Pause();surface.Clearing-=Clear;overlay.RemoveFromHierarchy();}
    }
}

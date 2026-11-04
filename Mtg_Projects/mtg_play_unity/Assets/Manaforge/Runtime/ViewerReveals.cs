using System;
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace Manaforge.Play
{
    // Authorized historical observations, deliberately unrelated to live object IDs.
    public sealed class ProjectedObservation
    {
        public CardProjectionContext Context {get;}
        public string Id {get;} public string GroupId {get;} public string Label {get;} public string Name {get;}
        public string OracleId {get;} public string PrintingId {get;}
        internal ProjectedObservation(CardProjectionContext context,JToken value)
        {
            Context=context;Id=(string)value["observation_id"];GroupId=(string)value["group_id"];Label=(string)value["group_label"];
            Name=(string)value["name"];OracleId=(string)value["oracle_id"];PrintingId=(string)value["printing_id"];
        }
    }
    public sealed class ViewerRevealGroup
    {
        public string Id {get;} public string Label {get;}
        public IReadOnlyList<ProjectedObservation> Cards {get;}
        internal ViewerRevealGroup(string id,IEnumerable<ProjectedObservation> cards)
        {Id=id;Cards=Array.AsReadOnly(cards.ToArray());Label=Cards[0].Label;}
    }
    // Mailbox-lock owned; survives snapshot coalescing. No acknowledged reveal is
    // replayed, and overflow fails explicitly rather than silently discarding cards.
    public sealed class ViewerRevealQueue
    {
        private string session,viewer;
        private readonly HashSet<string> seen=new HashSet<string>(StringComparer.Ordinal);
        private readonly Queue<ViewerRevealGroup> groups=new Queue<ViewerRevealGroup>();
        public bool Pending=>groups.Count>0;
        public ViewerRevealGroup Current=>Pending?groups.Peek():null;
        public void Observe(ProjectedCardFrame frame)
        {
            if(session!=frame.Context.SessionId || viewer!=frame.Context.ViewerId){Clear();session=frame.Context.SessionId;viewer=frame.Context.ViewerId;}
            if(frame.Status!="active" || frame.Result!=null){Clear();return;}
            foreach(var group in frame.Observations.Where(card=>!seen.Contains(card.Id)).GroupBy(card=>card.GroupId)){
                if(groups.Count>=128 || seen.Count+group.Count()>4096)throw new InvalidOperationException("REVEAL_QUEUE_LIMIT");
                var cards=group.ToArray();foreach(var card in cards)seen.Add(card.Id);
                groups.Enqueue(new ViewerRevealGroup(group.Key,cards));
            }
        }
        public bool Acknowledge(string id)
        {if(Current?.Id!=id)return false;groups.Dequeue();return true;}
        public bool Authorizes(ProjectedObservation card)=>card!=null && groups.Any(group=>group.Cards.Any(value=>ReferenceEquals(value,card)));
        public void Clear(){groups.Clear();seen.Clear();session=viewer=null;}
    }
}

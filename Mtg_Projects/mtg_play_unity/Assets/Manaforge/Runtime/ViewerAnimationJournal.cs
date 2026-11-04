using System;
using System.Collections.Generic;
using System.Linq;

namespace Manaforge.Play
{
    public enum GameplayMotionKind { Draw, Cast, Arrive, Tap, Untap, Attack, Block, Damage, Boost, Reduce, Depart, StackChange, Turn, Result, Summary }

    // Presentation hints only: no actions, hidden characteristics, textures or engine-rule inference.
    public sealed class GameplayMotionCue
    {
        public GameplayMotionKind Kind {get;}
        public string SubjectId {get;} public string RelatedId {get;} public string OwnerId {get;}
        public string FromZone {get;} public string ToZone {get;} public string Text {get;}
        public GameplayMotionCue(GameplayMotionKind kind,string id=null,string related=null,string owner=null,string from=null,string to=null,string text=null)
        {Kind=kind;SubjectId=id;RelatedId=related;OwnerId=owner;FromZone=from;ToZone=to;Text=text;}
        public bool Major=>Kind==GameplayMotionKind.Cast || Kind==GameplayMotionKind.Arrive || Kind==GameplayMotionKind.Attack
            || Kind==GameplayMotionKind.Block || Kind==GameplayMotionKind.Damage || Kind==GameplayMotionKind.StackChange || Kind==GameplayMotionKind.Turn;
        public float Duration=>Kind==GameplayMotionKind.Result?2f:Kind==GameplayMotionKind.Turn?1.5f:
            Kind==GameplayMotionKind.Cast || Kind==GameplayMotionKind.Depart?1f:Kind==GameplayMotionKind.Arrive?.9f:
            Kind==GameplayMotionKind.Tap || Kind==GameplayMotionKind.Untap?.6f:Kind==GameplayMotionKind.Boost || Kind==GameplayMotionKind.Reduce?.7f:.8f;
    }
    public sealed class GameplayMotionBatch
    {
        public CardProjectionContext Context {get;}
        public IReadOnlyList<GameplayMotionCue> Cues {get;}
        internal GameplayMotionBatch(CardProjectionContext context,IEnumerable<GameplayMotionCue> cues)
        {Context=context;Cues=Array.AsReadOnly(cues.ToArray());}
    }

    // Called under the mailbox lock before snapshots coalesce. At most one prior immutable
    // frame and 32 batches of 64 small cues are retained. It is never a replay/game model.
    public sealed class ViewerAnimationJournal
    {
        public const int MaximumBatches=32,MaximumCues=64;
        private ProjectedCardFrame previousCards;
        private ProjectedDecisionFrame previousDecision;
        private readonly Queue<GameplayMotionBatch> pending=new Queue<GameplayMotionBatch>();
        public int Count=>pending.Count;
        public bool HasMajor=>pending.Any(batch=>batch.Cues.Any(cue=>cue.Major));
        private bool overflow;
        private static bool Visible(ProjectedCard c)=>!c.Hidden && c.FaceDown==false;
        private static decimal? Number(string value)=>decimal.TryParse(value,System.Globalization.NumberStyles.Integer,
            System.Globalization.CultureInfo.InvariantCulture,out var number)?number:(decimal?)null;
        private static string Delta(decimal value)=>(value>0?"+":"")+value.ToString(System.Globalization.CultureInfo.InvariantCulture);
        public void Observe(ProjectedCardFrame cards,ProjectedDecisionFrame decision=null)
        {
            if(cards==null)return;
            bool initial=previousCards==null || previousCards.Context.SessionId!=cards.Context.SessionId || previousCards.Context.ViewerId!=cards.Context.ViewerId;
            if(!initial && cards.Context.Revision<=previousCards.Context.Revision)return;
            if(initial)Clear();
            var cues=new List<GameplayMotionCue>();int omitted=0;
            void Add(GameplayMotionCue cue){if(cues.Count<MaximumCues-1)cues.Add(cue);else omitted++;}
            bool finished=cards.Result!=null || cards.Status=="finished";
            if(finished){
                if(initial || previousCards.Result!=cards.Result){pending.Clear();overflow=false;
                    Add(new GameplayMotionCue(GameplayMotionKind.Result,text:cards.Result=="win"?"Victory":cards.Result=="loss"?"Defeat":cards.Result=="draw"?"Draw":"Game complete"));}
            }
            else if(!initial){
                var prior=previousCards.Cards.ToDictionary(c=>c.RenderId);
                var next=cards.Cards.ToDictionary(c=>c.RenderId);
                foreach(var card in cards.Cards.Where(Visible)){
                    prior.TryGetValue(card.RenderId,out var old);
                    if(old!=null && !Visible(old))old=null;
                    if(card.Zone=="stack" && old?.Zone!="stack")Add(new GameplayMotionCue(GameplayMotionKind.Cast,card.RenderId,owner:card.OwnerId,from:old?.Zone,to:"stack"));
                    if(card.Zone=="battlefield" && old?.Zone!="battlefield")Add(new GameplayMotionCue(GameplayMotionKind.Arrive,card.RenderId,owner:card.OwnerId,from:old?.Zone,to:card.Zone));
                    if(old==null)continue;
                    if(old.Zone=="battlefield" && card.Zone!="battlefield")Add(new GameplayMotionCue(GameplayMotionKind.Depart,card.RenderId,owner:card.OwnerId,from:old.Zone,to:card.Zone));
                    if(old.Zone=="stack" && card.Zone!="stack" && card.Zone!="battlefield")Add(new GameplayMotionCue(GameplayMotionKind.StackChange,card.RenderId,owner:card.OwnerId,from:"stack",to:card.Zone));
                    if(card.Zone!="battlefield" || old.Zone!="battlefield")continue;
                    if(old.Tapped.HasValue && card.Tapped.HasValue && old.Tapped!=card.Tapped)Add(new GameplayMotionCue(card.Tapped==true?GameplayMotionKind.Tap:GameplayMotionKind.Untap,card.RenderId,owner:card.OwnerId));
                    if(old.Damage.HasValue && card.Damage.HasValue && card.Damage>old.Damage)Add(new GameplayMotionCue(GameplayMotionKind.Damage,card.RenderId,text:Delta(-(decimal)card.Damage.Value+old.Damage.Value)));
                    var p=Number(card.Characteristics?.Power);var t=Number(card.Characteristics?.Toughness);
                    var op=Number(old.Characteristics?.Power);var ot=Number(old.Characteristics?.Toughness);
                    if(p.HasValue && t.HasValue && op.HasValue && ot.HasValue && (p!=op || t!=ot)){
                        bool down=p<op || t<ot;Add(new GameplayMotionCue(down?GameplayMotionKind.Reduce:GameplayMotionKind.Boost,card.RenderId,text:Delta(p.Value-op.Value)+"/"+Delta(t.Value-ot.Value)));
                    }
                }
                foreach(var old in previousCards.Cards.Where(Visible))if(!next.ContainsKey(old.RenderId)){
                    if(old.Zone=="stack")Add(new GameplayMotionCue(GameplayMotionKind.StackChange,owner:old.OwnerId,from:"stack",text:"Stack updated"));
                    else if(old.Zone=="battlefield" && !cards.Cards.Any(card=>card.Hidden || card.FaceDown!=false))Add(new GameplayMotionCue(GameplayMotionKind.Depart,owner:old.OwnerId,from:"battlefield"));
                }
                if(decision!=null && previousDecision!=null){
                    bool opening=decision.Turn==0 || decision.Decision?.Family=="mulligan" || decision.Phase==null;
                    if(!opening)foreach(var player in decision.PlayerLibraryCounts){
                        previousDecision.PlayerLibraryCounts.TryGetValue(player.Key,out var oldLibrary);previousDecision.PlayerHandCounts.TryGetValue(player.Key,out var oldHand);
                        decision.PlayerHandCounts.TryGetValue(player.Key,out var hand);
                        int count=ArenaLibraryMotion.ConfirmedHandArrivals(oldLibrary,player.Value,oldHand,hand);
                        for(int i=0;i<count;i++)Add(new GameplayMotionCue(GameplayMotionKind.Draw,owner:player.Key,from:"library",to:"hand"));
                    }
                    foreach(var player in decision.PlayerLifeTotals){
                        previousDecision.PlayerLifeTotals.TryGetValue(player.Key,out var life);
                        if(life.HasValue && player.Value.HasValue && life!=player.Value)Add(new GameplayMotionCue(player.Value<life?GameplayMotionKind.Damage:GameplayMotionKind.Boost,player.Key,text:Delta((decimal)player.Value.Value-life.Value)));
                    }
                    if(!opening && decision.Turn.HasValue && (decision.Turn!=previousDecision.Turn || decision.ActivePlayerId!=previousDecision.ActivePlayerId))
                        Add(new GameplayMotionCue(GameplayMotionKind.Turn,text:decision.ActivePlayerId==decision.Context.ViewerId?"Your turn":"Opponent’s turn"));
                    var before=new HashSet<string>(CombatKeys(previousDecision,previousCards));
                    string Key(string id)=>MotionKey(cards,id);
                    foreach(var group in decision.Combat){
                        foreach(var attacker in group.AttackerIds)if(!before.Contains("a:"+Key(attacker)+":"+Key(group.DefenderId)) && next.TryGetValue(Key(attacker),out var a) && Visible(a))
                            Add(new GameplayMotionCue(GameplayMotionKind.Attack,Key(attacker),related:Key(group.DefenderId)));
                        if(group.AttackerIds.Count==1)foreach(var blocker in group.BlockerIds)if(!before.Contains("b:"+Key(blocker)+":"+Key(group.AttackerIds[0])) && next.TryGetValue(Key(blocker),out var b) && Visible(b))
                            Add(new GameplayMotionCue(GameplayMotionKind.Block,Key(blocker),related:Key(group.AttackerIds[0])));
                    }
                }
            }
            previousCards=cards;previousDecision=decision;
            if(omitted>0)AddSummary(cues);
            if(cues.Count==0)return;
            if(pending.Count>=MaximumBatches){pending.Clear();overflow=true;}
            if(overflow){cues.Clear();AddSummary(cues);overflow=false;}
            pending.Enqueue(new GameplayMotionBatch(cards.Context,cues));
        }
        private static void AddSummary(List<GameplayMotionCue> cues)=>cues.Add(new GameplayMotionCue(GameplayMotionKind.Summary,text:"Battlefield updated"));
        private static string MotionKey(ProjectedCardFrame cards,string objectId)
            =>objectId==null?null:cards.Cards.FirstOrDefault(card=>card.ObjectId==objectId)?.RenderId??objectId;
        private static IEnumerable<string> CombatKeys(ProjectedDecisionFrame frame,ProjectedCardFrame cards)
        {
            string Key(string id)=>MotionKey(cards,id);
            foreach(var group in frame.Combat){
                foreach(var attacker in group.AttackerIds)yield return "a:"+Key(attacker)+":"+Key(group.DefenderId);
                if(group.AttackerIds.Count==1)foreach(var blocker in group.BlockerIds)yield return "b:"+Key(blocker)+":"+Key(group.AttackerIds[0]);
            }
        }
        public GameplayMotionBatch[] TakeThrough(long revision)
        {
            var result=new List<GameplayMotionBatch>();while(pending.Count>0 && pending.Peek().Context.Revision<=revision)result.Add(pending.Dequeue());return result.ToArray();
        }
        public void Clear(){pending.Clear();previousCards=null;previousDecision=null;overflow=false;}
    }
}

using UnityEngine;

namespace Manaforge.Play
{
    public enum GameplayLayoutSlot { Hand, Battlefield, GameStack }

    public readonly struct GameplayLayoutContext
    {
        public readonly float Width, Height;
        public readonly bool Opening, StackFocused, LibraryOrdering;
        public GameplayLayoutContext(float width, float height, bool opening, bool stackFocused, bool libraryOrdering)
        { Width=width; Height=height; Opening=opening; StackFocused=stackFocused; LibraryOrdering=libraryOrdering; }
    }

    public interface IGameplayLayoutStrategy
    {
        GameplayLayoutPlan Resolve(GameplayLayoutContext context);
    }

    // Geometry only: no card membership, state mutation, Unity hierarchy or commands.
    public sealed class GameplayLayoutPlan
    {
        public GameplayCardLayout.BattlefieldGeometry Battlefield { get; }
        public Rect HandBounds { get; }
        public float HandSize { get; }
        public float HandNavigationY { get; }
        public Rect StackBounds { get; }
        public Rect StackToolbarBounds { get; }
        public Rect StackBackdropBounds { get; }
        public float StackCardSize { get; }
        public float OpponentCommandTop { get; }
        public float LocalCommandTop { get; }
        public float ZoneBankSeparation { get; }
        public float ZoneViewportTop { get; }
        public float ZoneMaxHeight { get; }
        public float PlayerHudHeight { get; }
        public Rect PublicZoneBounds { get; }
        public float PublicZoneCardSize=>185;
        public float ActionViewportWidth { get; }
        public float ActionViewportRight { get; }
        public float? ActionViewportTop { get; }
        public float? ActionViewportBottom { get; }
        public float ActionMaxHeight { get; }
        public float PriorityMaxHeight { get; }
        public GameplayLayoutPlan(GameplayCardLayout.BattlefieldGeometry battlefield,
            Rect handBounds,
            float handSize,
            float handNavigationY,
            Rect stackBounds,
            Rect stackToolbarBounds,
            Rect stackBackdropBounds,
            float stackCardSize,
            float opponentCommandTop,
            float localCommandTop,
            float zoneBankSeparation,
            float zoneViewportTop,
            float zoneMaxHeight,
            float playerHudHeight,
            Rect publicZoneBounds,
            float actionViewportWidth,
            float actionViewportRight,
            float? actionViewportTop,
            float? actionViewportBottom,
            float actionMaxHeight,
            float priorityMaxHeight)
        {
            Battlefield=battlefield;
            HandBounds=handBounds;
            HandSize=handSize;
            HandNavigationY=handNavigationY;
            StackBounds=stackBounds;
            StackToolbarBounds=stackToolbarBounds;
            StackBackdropBounds=stackBackdropBounds;
            StackCardSize=stackCardSize;
            OpponentCommandTop=opponentCommandTop;
            LocalCommandTop=localCommandTop;
            ZoneBankSeparation=zoneBankSeparation;
            ZoneViewportTop=zoneViewportTop;
            ZoneMaxHeight=zoneMaxHeight;
            PlayerHudHeight=playerHudHeight;
            PublicZoneBounds=publicZoneBounds;
            ActionViewportWidth=actionViewportWidth;
            ActionViewportRight=actionViewportRight;
            ActionViewportTop=actionViewportTop;
            ActionViewportBottom=actionViewportBottom;
            ActionMaxHeight=actionMaxHeight;
            PriorityMaxHeight=priorityMaxHeight;
        }
        public Rect Bounds(GameplayLayoutSlot slot)
        {
            switch(slot){
                case GameplayLayoutSlot.Hand:return HandBounds;
                case GameplayLayoutSlot.GameStack:return StackBounds;
                case GameplayLayoutSlot.Battlefield:return new Rect(Battlefield.Left,78,Battlefield.Span,Battlefield.HandTop-24-78);
                default:throw new System.ArgumentOutOfRangeException(nameof(slot));
            }
        }
    }

    public sealed class LegacyGameplayLayoutStrategy : IGameplayLayoutStrategy
    {
        public GameplayLayoutPlan Resolve(GameplayLayoutContext context)
        {
            float width=context.Width,height=context.Height;
            GameplayCardLayout.BattlefieldGeometry battlefield=new GameplayCardLayout.BattlefieldGeometry(width,height);
            float handSpan=context.Opening?Mathf.Max(230,width-240):Mathf.Clamp(width-680,145,900);
            float handSize=context.Opening?210:145;
            Rect handBounds=new Rect((width-handSpan)*.5f,context.Opening?height*.24f:height-handSize*1.4f+55,handSpan,handSize*1.4f);
            float handNavigationY=height-30;
            float stackWidth=context.StackFocused?Mathf.Min(520,Mathf.Max(220,width*.4f)):200;
            float stackLeft=Mathf.Max(260,width-stackWidth-20),stackTop=context.StackFocused?height*.27f:height*.36f;
            stackWidth=Mathf.Max(100,width-stackLeft-20);
            float stackCardSize=context.StackFocused?Mathf.Clamp((height*.42f)/1.4f,120,190):100;
            Rect stackBounds=new Rect(stackLeft,stackTop,stackWidth,stackCardSize*1.4f);
            Rect stackToolbarBounds=new Rect(stackLeft,stackTop-38,stackWidth,0);
            Rect stackBackdropBounds=new Rect(stackLeft-10,stackTop-46,stackWidth+20,stackCardSize*1.4f+75);
            float opponentCommandTop=height*.36f;float localCommandTop=height*.50f;
            float zoneBankSeparation=Mathf.Max(350,height-242)-150;
            float zoneViewportTop=272-height;float zoneMaxHeight=height-182;float playerHudHeight=Mathf.Max(170,height-70);
            Rect publicZoneBounds=new Rect(180,height*.34f,width-360,185*1.4f);
            float actionViewportWidth=context.LibraryOrdering?width*.7f:context.Opening?520:275;
            float actionViewportRight=context.LibraryOrdering?width*.15f-20:context.Opening?width*.5f-280:0;
            float? actionViewportTop=context.LibraryOrdering?(float?)(65-height*.82f):null;
            float? actionViewportBottom=context.LibraryOrdering?null:(float?)32;
            float actionMaxHeight=context.LibraryOrdering?height*.65f-32:context.Opening?170:285;
            float priorityMaxHeight=height*.7f-32;
            return new GameplayLayoutPlan(
                battlefield: battlefield,
                handBounds: handBounds,
                handSize: handSize,
                handNavigationY: handNavigationY,
                stackBounds: stackBounds,
                stackToolbarBounds: stackToolbarBounds,
                stackBackdropBounds: stackBackdropBounds,
                stackCardSize: stackCardSize,
                opponentCommandTop: opponentCommandTop,
                localCommandTop: localCommandTop,
                zoneBankSeparation: zoneBankSeparation,
                zoneViewportTop: zoneViewportTop,
                zoneMaxHeight: zoneMaxHeight,
                playerHudHeight: playerHudHeight,
                publicZoneBounds: publicZoneBounds,
                actionViewportWidth: actionViewportWidth,
                actionViewportRight: actionViewportRight,
                actionViewportTop: actionViewportTop,
                actionViewportBottom: actionViewportBottom,
                actionMaxHeight: actionMaxHeight,
                priorityMaxHeight: priorityMaxHeight);
        }
    }
}

using UnityEngine;

namespace Manaforge.Play
{
    // Printing-layout geometry only. No ability, chapter, loyalty or defense calculation.
    public sealed class CardCompactProfile
    {
        public string Kind {get;}
        public Rect Crop {get;}
        public Rect? SecondaryCrop {get;}
        public int Rotation {get;}
        public int InspectionRotation {get;}
        private CardCompactProfile(string kind,Rect crop,int rotation=0,int inspectionRotation=0,Rect? secondary=null)
        {Kind=kind;Crop=crop;Rotation=rotation;InspectionRotation=inspectionRotation;SecondaryCrop=secondary;}
        public static CardCompactProfile FromMetadata(string layout,string typeLine)
        {
            var types=(typeLine??"").Split('—')[0].Split(' ');
            bool Has(string type)=>System.Array.IndexOf(types,type)>=0;
            var normal=new Rect(.08f,.45f,.84f,.42f);
            if(Has("Battle"))return new CardCompactProfile("Battle",new Rect(.14f,.12f,.42f,.75f),90,90);
            if(Has("Planeswalker"))return new CardCompactProfile("Planeswalker",new Rect(.08f,.52f,.84f,.35f));
            if(System.Array.IndexOf((typeLine??"").Replace('—',' ').Split(' '),"Room")>=0)return new CardCompactProfile("Room",new Rect(.14f,.12f,.39f,.75f),90,90);
            if(Has("Plane") || Has("Phenomenon"))return new CardCompactProfile("Plane",new Rect(.13f,.12f,.42f,.75f),90,90);
            if(Has("Dungeon"))return new CardCompactProfile("Dungeon",new Rect(.08f,.13f,.84f,.73f));
            switch(layout) {
                case "saga":return new CardCompactProfile("Saga",new Rect(.53f,.52f,.40f,.36f));
                case "class":return new CardCompactProfile("Class",new Rect(.08f,.50f,.35f,.35f));
                case "split":case "aftermath":return new CardCompactProfile("Split",new Rect(.13f,.08f,.35f,.36f),90,90,new Rect(.13f,.57f,.35f,.36f));
                case "token":case "double_faced_token":return new CardCompactProfile("Token",new Rect(.08f,.35f,.84f,.5f));
                case "emblem":return new CardCompactProfile("Emblem",normal);
                case "adventure":return new CardCompactProfile("Adventure",normal);
                case "leveler":return new CardCompactProfile("Level up",new Rect(.08f,.52f,.84f,.34f));
                case "prototype":return new CardCompactProfile("Prototype",normal);
                case "mutate":return new CardCompactProfile("Mutate",normal);
                case "case":return new CardCompactProfile("Case",new Rect(.08f,.40f,.38f,.45f));
                case "transform":return new CardCompactProfile("DFC",normal);
                case "modal_dfc":return new CardCompactProfile("Modal DFC",normal);
                case "meld":return new CardCompactProfile("Meld",normal);
                case "scheme":return new CardCompactProfile("Scheme",normal);
                case "vanguard":return new CardCompactProfile("Vanguard",normal);
                case "normal":return new CardCompactProfile("",normal);
                default:return null;
            }
        }
    }
}

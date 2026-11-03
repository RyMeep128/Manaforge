using System;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // Presentation only. Both faces must already be permitted by the caller's viewer projection.
    public sealed class CardInspectionFlip : IDisposable
    {
        private readonly CardView view;
        private IVisualElementScheduledItem timer;
        private Action midpoint;
        private uint expectedRevision;
        private double started;
        private bool disposed;
        public bool Running {get;private set;}
        public CardInspectionFlip(CardView view){this.view=view??throw new ArgumentNullException(nameof(view));}
        public bool Begin(Action showOtherPermittedFace,bool reducedMotion=false)
        {
            if(disposed || Running || view.Identity==null || view.Mode!=CardPresentationMode.Full || showOtherPermittedFace==null)return false;
            if(reducedMotion){showOtherPermittedFace();return true;}
            midpoint=showOtherPermittedFace;expectedRevision=view.ViewRevision;Running=true;started=Time.realtimeSinceStartupAsDouble;
            timer=view.schedule.Execute(()=>Advance((float)((Time.realtimeSinceStartupAsDouble-started)/.36))).Every(16);
            return true;
        }
        public void Advance(float progress)
        {
            if(!Running)return;
            if(float.IsNaN(progress) || view.Identity==null || view.ViewRevision!=expectedRevision || view.Mode!=CardPresentationMode.Full){Cancel();return;}
            progress=Mathf.Clamp01(progress);
            view.style.scale=new Scale(new Vector3(Mathf.Max(.02f,Mathf.Abs(Mathf.Cos(progress*Mathf.PI))),1,1));
            if(progress>=.5f && midpoint!=null){var swap=midpoint;midpoint=null;try{swap();expectedRevision=view.ViewRevision;}catch{Cancel();throw;}}
            if(progress>=1)Cancel();
        }
        public void Cancel(){timer?.Pause();timer=null;midpoint=null;Running=false;view.style.scale=new Scale(Vector3.one);}
        public void Dispose(){Cancel();disposed=true;}
    }
}

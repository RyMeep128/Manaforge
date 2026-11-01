using System;
using System.Text.RegularExpressions;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // Manaforge-owned UI geometry; Arena desktop mulligan reference uses a 4-degree step / 30-degree fan cap.
    public readonly struct OpeningCardPlacement
    {
        public readonly float Left,Top,Width,Angle;
        public OpeningCardPlacement(float left,float top,float width,float angle){Left=left;Top=top;Width=width;Angle=angle;}
    }
    public static class OpeningHandFan
    {
        public static string PlainPrompt(string value)
        {
            if(string.IsNullOrEmpty(value) || value.Length>4096)return value??"";
            const RegexOptions options=RegexOptions.IgnoreCase|RegexOptions.CultureInvariant;
            try{return Regex.Replace(Regex.Replace(value,@"<br\s*/?>","\n",options,TimeSpan.FromMilliseconds(50)),@"</?font\b[^>]*>","",options,TimeSpan.FromMilliseconds(50));}
            catch(RegexMatchTimeoutException){return value;}
        }
        public static OpeningCardPlacement[] Arrange(int count,float availableWidth)
        {
            if(count<0 || count>256 || float.IsNaN(availableWidth) || float.IsInfinity(availableWidth) || availableWidth<=0)throw new ArgumentOutOfRangeException();
            if(count==0)return Array.Empty<OpeningCardPlacement>();
            float width=Mathf.Min(230,availableWidth*.6f),height=width*1.4f;
            float step=Mathf.Min(4,30f/count),edge=(count-1)*.5f*step*Mathf.Deg2Rad;
            float outerWidth=width*Mathf.Cos(edge)+height*Mathf.Sin(edge);
            float radius=count==1?0:Mathf.Max(0,(availableWidth-outerWidth-16)/(2*Mathf.Sin(edge)));
            var result=new OpeningCardPlacement[count];
            for(int i=0;i<count;i++){
                float angle=(i-(count-1)*.5f)*step,radians=angle*Mathf.Deg2Rad;
                result[i]=new OpeningCardPlacement(availableWidth*.5f+radius*Mathf.Sin(radians)-width*.5f,20+radius*(1-Mathf.Cos(radians)),width,angle);
            }
            return result;
        }
        // No card/decision references or callbacks are retained across viewer clearing.
        public static void Present(VisualElement cardsRoot)
        {
            float width=cardsRoot.resolvedStyle.width;if(float.IsNaN(width) || width<=0)return;
            var cards=cardsRoot.Query<CardView>().ToList();var placements=Arrange(cards.Count,width);
            for(int i=0;i<cards.Count;i++){
                var placement=placements[i];var card=cards[i];card.SetPresentation(CardPresentationMode.Full,placement.Width);
                card.style.position=Position.Absolute;card.style.left=placement.Left;card.style.top=placement.Top;
                card.style.rotate=new Rotate(new Angle(placement.Angle,AngleUnit.Degree));
            }
        }
    }
}

using NUnit.Framework;
using UnityEngine;
using UnityEngine.UIElements;
namespace Manaforge.Play.Tests
{
    public sealed class CardBackTests
    {
        private sealed class Sleeves : ICardBackProvider
        {
            public Texture First,Second;
            public Texture Resolve(string owner)=>owner=="one"?First:Second;
        }
        [Test] public void OwnerAppearanceIsSharedAndNeverOwnedByViews()
        {
            var first=new Texture2D(2,2);var second=new Texture2D(2,2);var provider=new Sleeves{First=first,Second=second};
            try{
                var a=new CardBackView(provider);var b=new CardBackView(provider);a.Bind("one");b.Bind("two");
                Assert.That(a.image,Is.SameAs(first));Assert.That(b.image,Is.SameAs(second));
                a.Bind("two");Assert.That(a.image,Is.SameAs(b.image));a.ClearBinding();
                Assert.That(a.image,Is.Null);Assert.That(a.OwnerId,Is.Null);Assert.That(second==null,Is.False);
            }finally{Object.DestroyImmediate(first);Object.DestroyImmediate(second);}
        }
        [Test] public void HiddenFanRetainsViewsAndOnlyUsesPermittedCount()
        {
            var root=new VisualElement();GameplayCardLayout.HiddenHand(root,7,470,180,"one");var first=root[0];
            var texture=((CardBackView)first).image;Assert.That(texture,Is.Not.Null);
            GameplayCardLayout.HiddenHand(root,7,470,180,"one");Assert.That(root[0],Is.SameAs(first));Assert.That(((CardBackView)root[0]).image,Is.SameAs(texture));
            GameplayCardLayout.HiddenHand(root,100,470,180,"one");Assert.That(root.childCount,Is.EqualTo(12));
            GameplayCardLayout.HiddenHand(root,null,470,180);Assert.That(root.childCount,Is.Zero);Assert.That(((CardBackView)first).image,Is.Null);
            GameplayCardLayout.HiddenHand(root,0,470,180);Assert.That(root.childCount,Is.Zero);
        }
        [Test] public void ConcealmentClearsFaceValuesBeforeShowingBackAndUnavailableIsDistinct()
        {
            using(var card=new CardView()){
                card.BindUnavailable();card.UpdateValues(new CardDisplayValues("Secret name",null,"Secret type","Secret rules","2/2","Secret status"));card.tooltip="Secret tooltip";
                card.ShowBack("one");Assert.That(card.Artwork,Is.Null);Assert.That(card.Identity,Is.Null);Assert.That(card.tooltip,Is.Null);
                foreach(var label in card.Query<Label>().ToList())Assert.That(label.text??"",Does.Not.Contain("Secret"));
                var back=card.Q<CardBackView>();var texture=back.image;card.ShowBack("one");Assert.That(back.image,Is.SameAs(texture));
                card.BindUnavailable();Assert.That(back.image,Is.Null);Assert.That(back.style.display.value,Is.EqualTo(DisplayStyle.None));
                card.ShowBack("two");card.Conceal();Assert.That(back.image,Is.Null);Assert.That(back.OwnerId,Is.Null);
            }
        }
        [Test] public void LibraryEmptyUnknownAndConcealedExileUseBackWithoutLeakingFace()
        {
            using(var library=new ZonePile("library")){
                library.Bind("one");library.Present(null,null,"Secret",false);Assert.That(library.Q<CardBackView>().image,Is.Not.Null);Assert.That(library.Q<Label>("zone-count").text,Is.EqualTo("?"));
                library.Present(0,null,"Secret",false);Assert.That(library.Q<CardBackView>().image,Is.Null);
                library.Present(20,null,null,false);library.ClearBinding();Assert.That(library.Q<CardBackView>().image,Is.Null);
            }
            using(var exile=new ZonePile("exile")){
                exile.Bind("two");exile.Present(1,null,"Secret",false,true);Assert.That(exile.Q<CardBackView>().image,Is.Not.Null);Assert.That(exile.Q<Label>("zone-fallback").text,Is.Empty);
            }
        }
    }
}

using UnityEngine;
using UnityEngine.UIElements;
namespace Manaforge.Play
{
    // Appearance is player-scoped, never card-identity scoped. Providers own textures;
    // views borrow them. A future sleeve service can implement this same interface.
    public interface ICardBackProvider { Texture Resolve(string ownerId); }
    public sealed class ClassicCardBackProvider : ICardBackProvider
    {
        public static readonly ICardBackProvider Shared=new ClassicCardBackProvider();
        private Texture texture;private bool loaded;
        public Texture Resolve(string ownerId)
        {if(!loaded){texture=Resources.Load<Texture2D>("CardBackClassic");loaded=true;}return texture;}
    }
    public sealed class CardBackView : Image
    {
        private readonly ICardBackProvider provider;
        public string OwnerId {get;private set;}
        public CardBackView(ICardBackProvider provider=null)
        {
            this.provider=provider??ClassicCardBackProvider.Shared;
            name="card-back";pickingMode=PickingMode.Ignore;scaleMode=ScaleMode.ScaleToFit;AddToClassList("mf-card-back");
        }
        public void Bind(string ownerId){OwnerId=ownerId;image=provider.Resolve(ownerId);}
        public void ClearBinding(){OwnerId=null;image=null;}
    }
}

using System;
using System.Collections.Generic;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // Future feature gates, local to presentation construction. They grant no game authority.
    public sealed class GameplayPresentationCapabilities
    {
        public static GameplayPresentationCapabilities Default { get; } = new GameplayPresentationCapabilities();
        public bool PrivateLayout { get; }
        public bool SharedOrganization { get; }
        public bool VisualStacks { get; }
        public bool AutomaticOrganization { get; }
        public GameplayPresentationCapabilities(bool privateLayout=false, bool sharedOrganization=false,
            bool visualStacks=false, bool automaticOrganization=false)
        { PrivateLayout=privateLayout; SharedOrganization=sharedOrganization; VisualStacks=visualStacks; AutomaticOrganization=automaticOrganization; }
    }

    [Flags]
    public enum GameplayHudCapabilities { None=0, Drawer=1, Move=2, Resize=4, Dock=8, ConvertDrawer=16 }

    public static class GameplayHudIds
    {
        public const string Hand="hand", Players="players", Commanders="commanders", Priority="priority",
            Actions="actions", Zones="zones", Library="zones/library", Graveyard="zones/graveyard",
            Exile="zones/exile", Battlefield="battlefield", GameStack="game-stack";
        // These keys are deliberately session/viewer scoped, never profile preset keys.
        public static string Seat(string family, string session, string viewer, string seat)
            =>family+"/"+Part(session)+Part(viewer)+Part(seat);
        private static string Part(string value)=>value.Length+":"+value;
    }

    public sealed class GameplayHudDescriptor
    {
        public string Id { get; }
        public string DisplayName { get; }
        public string DefaultSlot { get; }
        public string ParentId { get; }
        public string PresetKey { get; }
        public GameplayHudCapabilities Capabilities { get; }
        public GameplayHudDescriptor(string id, string displayName, string defaultSlot,
            GameplayHudCapabilities capabilities=GameplayHudCapabilities.None, string parentId=null, string presetKey=null)
        {
            if(string.IsNullOrWhiteSpace(id) || string.IsNullOrWhiteSpace(displayName) || string.IsNullOrWhiteSpace(defaultSlot))
                throw new ArgumentException("HUD_DESCRIPTOR_REQUIRED");
            if(presetKey!=null && string.IsNullOrWhiteSpace(presetKey))throw new ArgumentException("HUD_PRESET_KEY_REQUIRED");
            PresetKey=presetKey;Id=id; DisplayName=displayName; DefaultSlot=defaultSlot; Capabilities=capabilities; ParentId=parentId;
        }
    }

    // Logical components can share a surface without acquiring or reparenting its views.
    public sealed class GameplayHudLayoutAdapter
    {
        public GameplayLayoutSlot Slot { get; }
        public GameplayHudLayoutAdapter(GameplayLayoutSlot slot) { Slot=slot; }
        public UnityEngine.Rect Bounds(GameplayLayoutPlan plan)=>plan.Bounds(Slot);
    }

    // No view callbacks, hierarchy changes or disposal are owned by this registry.
    public sealed class GameplayHudRegistry : IDisposable
    {
        private readonly Dictionary<string,Registration> entries=new Dictionary<string,Registration>(StringComparer.Ordinal);
        private bool disposed;
        public int Count=>entries.Count;
        public IEnumerable<Registration> Entries=>entries.Values;
        public Registration Find(string id)=>entries.TryGetValue(id,out var entry)?entry:null;
        public Registration Register(GameplayHudDescriptor descriptor, VisualElement element=null,
            GameplayHudLayoutAdapter adapter=null, bool available=true, IGameplayContainerBinding container=null)
        {
            if(disposed)throw new ObjectDisposedException(nameof(GameplayHudRegistry));
            if(descriptor==null)throw new ArgumentNullException(nameof(descriptor));
            if(element==null && adapter==null)throw new ArgumentException("HUD_BINDING_REQUIRED");
            if(entries.ContainsKey(descriptor.Id))throw new InvalidOperationException("HUD_DUPLICATE_ID");
            if(descriptor.PresetKey!=null)foreach(var existing in entries.Values)
                if(existing.Descriptor.PresetKey==descriptor.PresetKey)throw new InvalidOperationException("HUD_DUPLICATE_PRESET_KEY");
            var binding=container??element as IGameplayContainerBinding;
            if(binding!=null && binding.Element!=element)throw new ArgumentException("HUD_CONTAINER_VIEW_MISMATCH");
            var registration=new Registration(this,descriptor,element,adapter,available,binding);
            entries.Add(descriptor.Id,registration);return registration;
        }
        public sealed class Registration : IDisposable
        {
            private GameplayHudRegistry owner;
            public GameplayHudDescriptor Descriptor { get; private set; }
            public VisualElement Element { get; }
            public GameplayHudLayoutAdapter Adapter { get; }
            public IGameplayContainerBinding Container { get; private set; }
            public bool Available { get; set; }
            public bool IsRegistered=>owner!=null;
            internal Registration(GameplayHudRegistry owner, GameplayHudDescriptor descriptor, VisualElement element,
                GameplayHudLayoutAdapter adapter, bool available, IGameplayContainerBinding container)
            { Container=container;this.owner=owner; Descriptor=descriptor; Element=element; Adapter=adapter; Available=available; }
            public void SetContainerBinding(IGameplayContainerBinding container,GameplayHudCapabilities capabilities=GameplayHudCapabilities.Drawer)
            {
                if(owner==null)throw new ObjectDisposedException(nameof(Registration));
                if(container!=null && container.Element!=Element)throw new ArgumentException("HUD_CONTAINER_VIEW_MISMATCH");
                Container=container;var d=Descriptor;
                var caps=container==null?d.Capabilities&~(GameplayHudCapabilities.Move|GameplayHudCapabilities.Resize|GameplayHudCapabilities.Dock):capabilities;
                Descriptor=new GameplayHudDescriptor(d.Id,d.DisplayName,d.DefaultSlot,caps,d.ParentId,d.PresetKey);
            }
            public void Dispose()
            {
                if(owner==null)return;
                owner.entries.Remove(Descriptor.Id);owner=null;Container=null;Available=false;
            }
        }
        public void Dispose()
        {
            if(disposed)return;
            foreach(var entry in new List<Registration>(entries.Values))entry.Dispose();
            disposed=true;
        }
    }
}

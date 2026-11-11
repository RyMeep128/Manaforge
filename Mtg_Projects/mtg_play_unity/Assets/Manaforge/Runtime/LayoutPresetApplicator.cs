using System;
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace Manaforge.Play
{
    public sealed class LayoutPresetApplication
    {
        public IReadOnlyList<ContainerLayoutState> States { get; }
        public IReadOnlyDictionary<string,bool> DrawerExpansion { get; }
        public IReadOnlyList<string> Adjustments { get; }
        internal LayoutPresetApplication(IEnumerable<ContainerLayoutState> states,Dictionary<string,bool> expansion,List<string> adjustments)
        {States=Array.AsReadOnly(states.ToArray());DrawerExpansion=new System.Collections.ObjectModel.ReadOnlyDictionary<string,bool>(expansion);Adjustments=adjustments.AsReadOnly();}
    }
    // Resolves authored preset keys to current local component bindings. Never persists runtime IDs.
    public sealed class LayoutPresetApplicator
    {
        private readonly ContainerLayoutController controller;
        private readonly GameplayHudRegistry registry;
        private readonly Action cancelGestures;
        private readonly Dictionary<string,ContainerLayoutState> defaults;
        public bool IsApplying { get; private set; }
        public LayoutPresetApplicator(ContainerLayoutController controller,GameplayHudRegistry registry,Action cancelGestures)
        {this.controller=controller;this.registry=registry;this.cancelGestures=cancelGestures;defaults=controller.Ids.ToDictionary(id=>id,id=>controller.State(id));}
        private Dictionary<string,GameplayHudRegistry.Registration> Bindings()=>registry.Entries.Where(e=>e.Descriptor.PresetKey!=null && e.Element is GameplayContainerShell)
            .ToDictionary(e=>e.Descriptor.PresetKey,e=>e,StringComparer.Ordinal);
        public HudLayoutPreset Capture(string id,string name,HudLayoutPreset prior=null)
        {
            var entries=prior==null?new Dictionary<string,HudComponentSnapshot>():prior.Components.ToDictionary(e=>e.Key,e=>e.Value);
            var bindings=Bindings();var ids=bindings.ToDictionary(e=>((GameplayContainerShell)e.Value.Element).ComponentId,e=>e.Key);
            foreach(var pair in bindings){
                var shell=(GameplayContainerShell)pair.Value.Element;if(!pair.Value.Available || !controller.Ids.Contains(shell.ComponentId))continue;
                var state=controller.State(shell.ComponentId);string target=null;
                if(state.DockTarget!=null)ids.TryGetValue(state.DockTarget,out target);
                var edge=state.DockTarget!=null && target==null?ContainerDockEdge.None:state.Edge;
                entries.TryGetValue(pair.Key,out var previous);
                entries[pair.Key]=new HudComponentSnapshot(state.FloatingRect,state.Mode,target,edge,state.Order,shell.DrawerExpandedPreference,previous?.ToJson());
            }
            return new HudLayoutPreset(id,name,entries,prior?.ToJson());
        }
        public HudLayoutPreset BuiltInDefault()
        {
            var bindings=Bindings();var ids=bindings.ToDictionary(e=>((GameplayContainerShell)e.Value.Element).ComponentId,e=>e.Key);
            var entries=new Dictionary<string,HudComponentSnapshot>();
            foreach(var pair in bindings){var id=((GameplayContainerShell)pair.Value.Element).ComponentId;if(!defaults.TryGetValue(id,out var state))continue;
                string target=null;if(state.DockTarget!=null)ids.TryGetValue(state.DockTarget,out target);
                entries.Add(pair.Key,new HudComponentSnapshot(state.FloatingRect,state.Mode,target,state.Edge,state.Order,true));}
            return new HudLayoutPreset("built-in","Built-in layout",entries);
        }
        public LayoutPresetApplication Prepare(HudLayoutPreset preset)
        {
            if(preset==null)return null;
            var proposed=controller.Ids.ToDictionary(id=>id,id=>controller.State(id));var expansion=new Dictionary<string,bool>();var adjustments=new List<string>();
            var bindings=Bindings();
            foreach(var pair in bindings){
                var registration=pair.Value;var shell=(GameplayContainerShell)registration.Element;string id=shell.ComponentId;
                if(!registration.Available || !proposed.ContainsKey(id) || !defaults.ContainsKey(id))continue;
                var fallback=defaults[id];var limits=controller.Constraints(id);ContainerLayoutState candidate=fallback;bool expanded=true;
                if(preset.Components.TryGetValue(pair.Key,out var saved)){
                    string target=null;bool missingTarget=false;
                    if(saved.DockTarget!=null){
                        if(bindings.TryGetValue(saved.DockTarget,out var host) && host.Available && proposed.ContainsKey(((GameplayContainerShell)host.Element).ComponentId))
                            target=((GameplayContainerShell)host.Element).ComponentId;
                        else missingTarget=true;
                    }
                    var rect=saved.FloatingRect;
                    bool unsupported=saved.Mode==ContainerMode.Drawer && !limits.Supports(GameplayHudCapabilities.ConvertDrawer)
                        || !limits.Supports(GameplayHudCapabilities.Move) && rect.position!=fallback.FloatingRect.position
                        || !limits.Supports(GameplayHudCapabilities.Resize) && rect.size!=fallback.FloatingRect.size
                        || !limits.Supports(GameplayHudCapabilities.Dock) && saved.Edge!=ContainerDockEdge.None;
                    if(unsupported)adjustments.Add(registration.Descriptor.DisplayName+": default restored");
                    else{
                        var edge=saved.Edge;
                        if(edge!=ContainerDockEdge.None && (missingTarget || !limits.PermitsTarget(target) ||
                            target!=null && !controller.Constraints(target).AcceptsDockedContainers)){
                            target=null;edge=ContainerDockEdge.None;adjustments.Add(registration.Descriptor.DisplayName+": dock target unavailable; floated");
                        }
                        candidate=new ContainerLayoutState(id,rect,saved.Mode,target,edge,saved.Order);expanded=saved.DrawerExpanded;
                    }
                }
                proposed[id]=candidate;expansion[id]=expanded;
            }
            if(controller.PreviewLayout(proposed.Values)==null)return null;
            return new LayoutPresetApplication(proposed.Values,expansion,adjustments);
        }
        public bool Apply(LayoutPresetApplication application)
        {
            if(application==null || controller.PreviewLayout(application.States)==null)return false;
            IsApplying=true;
            try{
                cancelGestures?.Invoke();if(!controller.TryApplyLayout(application.States))return false;
                foreach(var entry in Bindings().Values){var shell=(GameplayContainerShell)entry.Element;
                    if(entry.Available && application.DrawerExpansion.TryGetValue(shell.ComponentId,out var expanded))shell.RestoreDrawerExpanded(expanded);}
                return true;
            }finally{IsApplying=false;}
        }
        public JToken Fingerprint(HudLayoutPreset prior=null)=>Capture("working","Working layout",prior).ToJson()["components"];
    }
}

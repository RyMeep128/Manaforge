using System;
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace Manaforge.Play
{
    public sealed class HudComponentSnapshot
    {
        private readonly JObject raw;
        private bool preserveOriginal;
        public Rect FloatingRect { get; }
        public ContainerMode Mode { get; }
        public string DockTarget { get; }
        public ContainerDockEdge Edge { get; }
        public int Order { get; }
        public bool DrawerExpanded { get; }
        public HudComponentSnapshot(Rect rect,ContainerMode mode,string target,ContainerDockEdge edge,int order,bool expanded,JObject extensions=null)
        {
            if(!ContainerLayoutResolver.Finite(rect.x) || !ContainerLayoutResolver.Finite(rect.y) ||
                !ContainerLayoutResolver.Finite(rect.width) || !ContainerLayoutResolver.Finite(rect.height) || rect.width<=0 || rect.height<=0 ||
                Mathf.Abs(rect.x)>10000 || Mathf.Abs(rect.y)>10000 || rect.width>10000 || rect.height>10000 ||
                !Enum.IsDefined(typeof(ContainerMode),mode) || !Enum.IsDefined(typeof(ContainerDockEdge),edge) || edge==ContainerDockEdge.None && target!=null)
                throw new ArgumentException("PRESET_COMPONENT_GEOMETRY");
            FloatingRect=rect;Mode=mode;DockTarget=target;Edge=edge;Order=order;DrawerExpanded=expanded;
            raw=extensions==null?new JObject():(JObject)extensions.DeepClone();
        }
        public JObject ToJson()
        {
            if(preserveOriginal)return (JObject)raw.DeepClone();
            var value=(JObject)raw.DeepClone();var rect=value["rect"] as JObject;
            rect=rect==null?new JObject():(JObject)rect.DeepClone();
            rect["x"]=FloatingRect.x;rect["y"]=FloatingRect.y;rect["width"]=FloatingRect.width;rect["height"]=FloatingRect.height;
            value["rect"]=rect;value["mode"]=Mode.ToString();value["dockTarget"]=DockTarget;value["edge"]=Edge.ToString();
            value["order"]=Order;value["drawerExpanded"]=DrawerExpanded;return value;
        }
        public static HudComponentSnapshot Parse(JObject value)
        {
            if(!(value?["rect"] is JObject rect) || value["mode"]?.Type!=JTokenType.String ||
                value["edge"]?.Type!=JTokenType.String || value["order"]?.Type!=JTokenType.Integer ||
                value["drawerExpanded"]?.Type!=JTokenType.Boolean || value["dockTarget"]==null ||
                value["dockTarget"].Type!=JTokenType.Null && value["dockTarget"].Type!=JTokenType.String)
                throw new ArgumentException("PRESET_COMPONENT_SHAPE");
            foreach(string key in new[]{"x","y","width","height"})
                if(rect[key]?.Type!=JTokenType.Float && rect[key]?.Type!=JTokenType.Integer)throw new ArgumentException("PRESET_COMPONENT_RECT");
            if(!Enum.TryParse((string)value["mode"],false,out ContainerMode mode) ||
                !Enum.TryParse((string)value["edge"],false,out ContainerDockEdge edge))throw new ArgumentException("PRESET_COMPONENT_MODE");
            string target=(string)value["dockTarget"];if(target!=null && string.IsNullOrWhiteSpace(target))throw new ArgumentException("PRESET_DOCK_TARGET");
            var parsed=new HudComponentSnapshot(new Rect((float)rect["x"],(float)rect["y"],(float)rect["width"],(float)rect["height"]),
                mode,target,edge,checked((int)(long)value["order"]),(bool)value["drawerExpanded"],value);
            parsed.preserveOriginal=true;return parsed;
        }
    }

    public sealed class HudLayoutPreset
    {
        private readonly JObject raw;
        private readonly IReadOnlyDictionary<string,HudComponentSnapshot> components;
        public string Id { get; }
        public string Name { get; }
        public IReadOnlyDictionary<string,HudComponentSnapshot> Components=>components;
        public HudLayoutPreset(string id,string name,IEnumerable<KeyValuePair<string,HudComponentSnapshot>> components,JObject extensions=null)
        {
            if(string.IsNullOrWhiteSpace(id) || id.Length>128 || id=="default")throw new ArgumentException("PRESET_ID");
            Id=id;Name=ValidateName(name);var entries=new Dictionary<string,HudComponentSnapshot>(StringComparer.Ordinal);
            foreach(var entry in components){
                if(string.IsNullOrWhiteSpace(entry.Key) || entry.Key.Length>256 || entry.Value==null || entries.ContainsKey(entry.Key))throw new ArgumentException("PRESET_COMPONENT_KEY");
                entries.Add(entry.Key,entry.Value);
            }
            if(entries.Count>256)throw new ArgumentException("PRESET_COMPONENT_LIMIT");
            // Includes dormant/unknown entries: a cycle cannot hide in an unloaded component.
            foreach(string key in entries.Keys){var seen=new HashSet<string>{key};string parent=entries[key].DockTarget;
                while(parent!=null && entries.ContainsKey(parent)){if(!seen.Add(parent))throw new ArgumentException("PRESET_DOCK_CYCLE");parent=entries[parent].DockTarget;}}
            this.components=new System.Collections.ObjectModel.ReadOnlyDictionary<string,HudComponentSnapshot>(entries);
            raw=extensions==null?new JObject():(JObject)extensions.DeepClone();
        }
        public static string ValidateName(string name)
        {
            name=name?.Trim();if(string.IsNullOrEmpty(name) || name.Length>64 || name.Any(char.IsControl) || string.Equals(name,"Default",StringComparison.OrdinalIgnoreCase))
                throw new ArgumentException("PRESET_NAME");return name;
        }
        public HudLayoutPreset Rename(string name)=>new HudLayoutPreset(Id,name,components,raw);
        public JObject ToJson()
        {
            var value=(JObject)raw.DeepClone();value["id"]=Id;value["name"]=Name;
            var data=new JObject();foreach(var entry in components)data[entry.Key]=entry.Value.ToJson();value["components"]=data;return value;
        }
        public static HudLayoutPreset Parse(JObject value)
        {
            if(value?["id"]?.Type!=JTokenType.String || value["name"]?.Type!=JTokenType.String || !(value["components"] is JObject entries))throw new ArgumentException("PRESET_SHAPE");
            return new HudLayoutPreset((string)value["id"],(string)value["name"],entries.Properties().Select(p=>
                new KeyValuePair<string,HudComponentSnapshot>(p.Name,HudComponentSnapshot.Parse(p.Value as JObject))),value);
        }
    }

    public sealed class LayoutPresetLibrary
    {
        public const int SchemaVersion=1;
        private readonly JObject raw;
        public IReadOnlyList<HudLayoutPreset> Presets { get; }
        public string LastSelectedId { get; }
        public static LayoutPresetLibrary Empty=>new LayoutPresetLibrary(Array.Empty<HudLayoutPreset>());
        public LayoutPresetLibrary(IEnumerable<HudLayoutPreset> presets,string lastSelectedId=null,JObject extensions=null)
        {
            var list=presets.ToArray();if(list.Length>64 || list.Any(p=>p==null) || list.Select(p=>p.Id).Distinct(StringComparer.Ordinal).Count()!=list.Length ||
                list.Select(p=>p.Name).Distinct(StringComparer.OrdinalIgnoreCase).Count()!=list.Length)throw new ArgumentException("PRESET_LIBRARY_CONFLICT");
            Presets=Array.AsReadOnly(list);LastSelectedId=lastSelectedId;raw=extensions==null?new JObject():(JObject)extensions.DeepClone();
        }
        public HudLayoutPreset Find(string id)=>Presets.FirstOrDefault(p=>p.Id==id);
        public LayoutPresetLibrary Save(HudLayoutPreset preset)=>new LayoutPresetLibrary(Presets.Where(p=>p.Id!=preset.Id).Concat(new[]{preset}),preset.Id,raw);
        public LayoutPresetLibrary Rename(string id,string name)
        {if(Find(id)==null)throw new ArgumentException("PRESET_NOT_FOUND");return new LayoutPresetLibrary(Presets.Select(p=>p.Id==id?p.Rename(name):p),LastSelectedId,raw);}
        public LayoutPresetLibrary Delete(string id)
        {if(Find(id)==null)throw new ArgumentException("PRESET_NOT_FOUND");return new LayoutPresetLibrary(Presets.Where(p=>p.Id!=id),LastSelectedId==id?null:LastSelectedId,raw);}
        public LayoutPresetLibrary Select(string id)=>new LayoutPresetLibrary(Presets,id,raw);
        public JObject ToJson()
        {var value=(JObject)raw.DeepClone();value["version"]=SchemaVersion;value["lastSelectedId"]=LastSelectedId;value["presets"]=new JArray(Presets.Select(p=>p.ToJson()));return value;}
        public static LayoutPresetLibrary Parse(JObject value)
        {
            if(value?["version"]?.Type!=JTokenType.Integer || (long)value["version"]!=SchemaVersion || !(value["presets"] is JArray presets) ||
                value["lastSelectedId"]==null || value["lastSelectedId"].Type!=JTokenType.Null && value["lastSelectedId"].Type!=JTokenType.String)
                throw new ArgumentException("PRESET_LIBRARY_SHAPE");
            return new LayoutPresetLibrary(presets.Select(p=>HudLayoutPreset.Parse(p as JObject)),(string)value["lastSelectedId"],value);
        }
    }
}

using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using Newtonsoft.Json.Linq;
namespace Manaforge.Play
{
    public enum BattlefieldGroupPresentationMode { Panel, Drawer }
    public sealed class ProjectedOrganizationGroup
    {
        public BattlefieldGroupPresentationMode PresentationMode {get;}
        public string Id {get;} public string Name {get;} public string Seat {get;}
        public float X {get;} public float Y {get;} public IReadOnlyList<string> Objects {get;}
        internal ProjectedOrganizationGroup(JObject group,string seat,IDictionary<string,string> objects){PresentationMode=(string)group["presentation_mode"]=="drawer"?BattlefieldGroupPresentationMode.Drawer:BattlefieldGroupPresentationMode.Panel;Id=(string)group["group_id"];Name=(string)group["name"];Seat=seat;X=(long)group["x"]/1000000f;Y=(long)group["y"]/1000000f;Objects=Array.AsReadOnly(group["members"].Select(h=>objects[(string)h]).ToArray());}
    }
    public sealed class ProjectedOrganizationFrame
    {
        public string Epoch {get;} public string Viewer {get;} public long GameplayRevision {get;} public long Revision {get;} public long Basis {get;}
        public IReadOnlyList<ProjectedOrganizationGroup> Groups {get;}
        public IReadOnlyDictionary<string,string> Handles {get;}
        public IReadOnlyDictionary<string,IReadOnlyList<string>> Roots {get;}
        internal ProjectedOrganizationFrame(JObject body)
        {
            Epoch=(string)body["match_epoch"];Viewer=(string)body["viewer_id"];GameplayRevision=(long)body["gameplay_revision"];Revision=(long)body["organization_revision"];Basis=(long)body["basis_revision"];
            var objects=body["mappings"].ToDictionary(m=>(string)m["handle"],m=>(string)m["object_reference"],StringComparer.Ordinal);
            Handles=new ReadOnlyDictionary<string,string>(objects.ToDictionary(p=>p.Value,p=>p.Key,StringComparer.Ordinal));
            var roots=new Dictionary<string,IReadOnlyList<string>>(StringComparer.Ordinal);var groups=new List<ProjectedOrganizationGroup>();
            foreach(JObject seat in body["seats"]){string id=(string)seat["seat_id"];roots.Add(id,Array.AsReadOnly(seat["root"].Select(h=>objects[(string)h]).ToArray()));foreach(JObject group in seat["groups"])groups.Add(new ProjectedOrganizationGroup(group,id,objects));}
            Roots=new ReadOnlyDictionary<string,IReadOnlyList<string>>(roots);Groups=groups.AsReadOnly();
        }
    }
    public interface IOrganizationPresentation
    {
        void PresentOrganization(ProjectedOrganizationFrame frame);
    }
}

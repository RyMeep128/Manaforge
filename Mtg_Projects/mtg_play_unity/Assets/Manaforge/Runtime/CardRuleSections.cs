using System.Collections.Generic;
using System.Text.RegularExpressions;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // Typography only: explicit printed headings, never ability evaluation or current-level inference.
    public sealed class CardRuleSection
    {
        public string Heading {get;}
        public string Text {get;}
        public CardRuleSection(string heading,string text){Heading=heading;Text=text??"";}
        public static IReadOnlyList<CardRuleSection> FromPrintedText(string kind,string text)
        {
            text=text??"";var result=new List<CardRuleSection>();
            if(text.Length>16384)return new[]{new CardRuleSection(null,text)};
            string heading=null;var lines=new List<string>();
            void Flush(){if(heading!=null || lines.Count>0)result.Add(new CardRuleSection(heading,string.Join("\n",lines)));lines.Clear();}
            foreach(var line in text.Replace("\r\n","\n").Split('\n')) {
                var loyalty=kind=="Planeswalker"?Regex.Match(line,@"^([+−-]?(?:[0-9]+|X)):\s*(.*)$"):Match.Empty;
                bool level=kind=="Level up" && Regex.IsMatch(line,@"^LEVEL [0-9]+(?:[-−–][0-9]+|\+)?$");
                bool classLevel=kind=="Class" && Regex.IsMatch(line,@"^(?:\{[A-Z0-9/]+\})+: Level [0-9]+$");
                if(loyalty.Success){Flush();heading=loyalty.Groups[1].Value;lines.Add(loyalty.Groups[2].Value);}
                else if(level || classLevel){Flush();heading=line;}
                else lines.Add(line);
            }
            Flush();return result.AsReadOnly();
        }
    }
    public sealed class CardRuleSections : VisualElement
    {
        private readonly List<Label> labels=new List<Label>();
        private readonly List<RulesTextView> symbols=new List<RulesTextView>();
        public CardRuleSections(){name="structured-rules";style.flexShrink=0;}
        public void SetText(string kind,string text)
        {
            Conceal();
            foreach(var section in CardRuleSection.FromPrintedText(kind,text)) {
                var row=new VisualElement{name="ability-row"};row.style.flexShrink=0;
                row.style.paddingTop=5;row.style.paddingBottom=5;
                bool loyalty=kind=="Planeswalker" && section.Heading!=null;
                if(loyalty)row.style.flexDirection=FlexDirection.Row;
                row.style.borderBottomWidth=1;row.style.borderBottomColor=new Color(.35f,.35f,.30f,.45f);
                if(!string.IsNullOrEmpty(section.Heading)) {
                    var header=new Label(section.Heading){name="ability-heading",enableRichText=false};
                    header.style.backgroundColor=new Color(.20f,.23f,.20f);header.style.color=Color.white;
                    header.style.paddingLeft=5;header.style.paddingRight=5;header.style.marginBottom=4;
                    if(loyalty){header.style.width=32;header.style.flexShrink=0;header.style.marginRight=5;header.style.alignSelf=Align.FlexStart;header.style.unityTextAlign=TextAnchor.MiddleCenter;}
                    header.style.whiteSpace=WhiteSpace.Normal;labels.Add(header);row.Add(header);
                    if(section.Heading.Contains("{")) {
                        var cost=new RulesTextView();cost.SetText(section.Heading);
                        cost.style.position=Position.Relative;cost.style.height=StyleKeyword.Auto;
                        if(cost.SymbolCount>0){header.style.display=DisplayStyle.None;row.Add(cost);symbols.Add(cost);}
                    }
                }
                var body=new Label(section.Text){name="ability-text",enableRichText=false};
                body.style.whiteSpace=WhiteSpace.Normal;body.style.color=new Color(.06f,.065f,.055f);
                body.style.marginLeft=body.style.marginRight=body.style.marginTop=body.style.marginBottom=0;
                if(loyalty){body.style.flexGrow=1;body.style.flexBasis=0;}
                body.style.paddingLeft=body.style.paddingRight=2;labels.Add(body);row.Add(body);
                var inline=new RulesTextView();inline.SetText(section.Text);inline.style.position=Position.Relative;inline.style.height=StyleKeyword.Auto;
                if(inline.SymbolCount>0){if(loyalty){inline.style.flexGrow=1;inline.style.flexBasis=0;}body.style.display=DisplayStyle.None;row.Add(inline);symbols.Add(inline);}
                Add(row);
            }
        }
        public void Resize(float size)
        {
            foreach(var label in labels){label.style.fontSize=size;CardTypography.Apply(label,label.name=="ability-heading"?CardTextRole.Type:CardTextRole.Rules);}
            foreach(var inline in symbols)inline.Resize(size);
        }
        public void Conceal(){Clear();labels.Clear();symbols.Clear();}
    }
    public sealed class RoomDoorDisplay
    {
        public string Name {get;} public string ManaCost {get;} public string RulesText {get;}
        public RoomDoorDisplay(string name,string manaCost,string rulesText){Name=name;ManaCost=manaCost;RulesText=rulesText;}
    }
}

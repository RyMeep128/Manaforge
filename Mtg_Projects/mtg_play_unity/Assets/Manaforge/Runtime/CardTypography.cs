using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;
using UnityEngine.TextCore.Text;

namespace Manaforge.Play
{
    public enum CardTextRole { Title,Type,Rules,PowerToughness,Collector }
    public static class CardTypography
    {
        private static readonly Dictionary<string,FontAsset> distanceFields=new Dictionary<string,FontAsset>();
        private static readonly Dictionary<string,Font> fonts=new Dictionary<string,Font>();
        public static string ResourceName(CardTextRole role,FontStyle emphasis=FontStyle.Normal)
        {
            string name=role==CardTextRole.Collector?"BelerenSmallCaps":role==CardTextRole.Rules?
                emphasis==FontStyle.BoldAndItalic?"PlantinBoldItalic":emphasis==FontStyle.Bold?"PlantinBold":
                emphasis==FontStyle.Italic?"PlantinItalic":"PlantinRegular":"BelerenBold";
            return "LocalCardVisuals/Fonts/"+name;
        }
        public static bool Apply(Label label,CardTextRole role,FontStyle emphasis=FontStyle.Normal)
        {
            label.AddToClassList(role==CardTextRole.Title?"CardTitleText":role==CardTextRole.Type?"CardTypeText":
                role==CardTextRole.Rules?"CardRulesText":role==CardTextRole.PowerToughness?"CardPowerToughness":"CardCollectorText");
            string key=ResourceName(role,emphasis);
            if(!fonts.TryGetValue(key,out var font)) {font=Resources.Load<Font>(key);if(font!=null)fonts.Add(key,font);}
            if(font==null)return false; // CI/source-only checkout can render with the default font.
            if(!distanceFields.TryGetValue(key,out var asset)) {
                asset=FontAsset.CreateFontAsset(font);
                asset.name=font.name+" Card SDF";
                distanceFields.Add(key,asset);
            }
            label.style.unityFontDefinition=new FontDefinition{fontAsset=asset};
            label.style.unityFontStyleAndWeight=FontStyle.Normal; // The supplied file already has its requested weight/style.
            return true;
        }
    }
}

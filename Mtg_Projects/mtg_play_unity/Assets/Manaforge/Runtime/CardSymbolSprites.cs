using System.Collections.Generic;
using System.Text.RegularExpressions;
using UnityEngine;

namespace Manaforge.Play
{
    public static class CardSymbolSprites
    {
        private static readonly Regex tokenShape=new Regex("^[A-Z0-9/]{1,24}$",RegexOptions.CultureInvariant);
        private static readonly Dictionary<string,Texture2D> loaded=new Dictionary<string,Texture2D>();
        public static bool TryLoad(string token,out Texture2D texture)
        {
            texture=null;if(token==null || !tokenShape.IsMatch(token))return false;
            if(loaded.TryGetValue(token,out texture))return true;
            texture=Resources.Load<Texture2D>("LocalCardVisuals/Symbols/"+token.Replace('/','_'));
            if(texture==null)return false;loaded.Add(token,texture);return true;
        }
    }
}

using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // Glyph ink is centered from its actual bounds, independently of a text line's baseline.
    public sealed class ManaSymbolView : VisualElement
    {
        private static Font font;
        private readonly string token;
        public ManaSymbolView(string value)
        {
            token=value;name="mana-symbol";pickingMode=PickingMode.Ignore;
            AddToClassList("CardManaSymbol");
            if(CardSymbolSprites.TryLoad(value,out var sprite)) {
                var image=new Image{image=sprite,scaleMode=ScaleMode.ScaleToFit,pickingMode=PickingMode.Ignore};
                image.StretchToParentSize();Add(image);return;
            }
            if(font==null)font=Resources.Load<Font>("Mana");
            // One fixed raster size keeps the shared font atlas bounded across zoom levels.
            var characters="";
            foreach(var part in value.Split('/'))if(ManaCostView.TryGlyph(part,out char glyph))characters+=glyph;
            font?.RequestCharactersInTexture(characters,64,FontStyle.Normal);
            generateVisualContent+=Draw;
            RegisterCallback<AttachToPanelEvent>(_=>Font.textureRebuilt+=Rebuilt);
            RegisterCallback<DetachFromPanelEvent>(_=>Font.textureRebuilt-=Rebuilt);
        }
        private void Rebuilt(Font changed){if(changed==font)MarkDirtyRepaint();}
        private void Draw(MeshGenerationContext context)
        {
            var box=contentRect;float diameter=Mathf.Min(box.width,box.height);
            if(diameter<=0 || font==null)return;
            var p=context.painter2D;p.fillColor=ManaCostView.ColorFor(token.Split('/')[0]);
            p.BeginPath();p.Arc(box.center,diameter*.5f,0,360);p.Fill();
            var parts=token.Split('/');
            if(parts.Length==1)DrawGlyph(context,parts[0],new Rect(box.center-Vector2.one*diameter*.37f,Vector2.one*diameter*.74f));
            else {
                DrawGlyph(context,parts[0],new Rect(box.x+diameter*.08f,box.y+diameter*.05f,diameter*.46f,diameter*.46f));
                DrawGlyph(context,parts[1],new Rect(box.x+diameter*.46f,box.y+diameter*.49f,diameter*.46f,diameter*.46f));
            }
        }
        private static void DrawGlyph(MeshGenerationContext context,string token,Rect area)
        {
            if(!ManaCostView.TryGlyph(token,out char glyph) || !font.GetCharacterInfo(glyph,out var info,64,FontStyle.Normal))return;
            float width=info.maxX-info.minX,height=info.maxY-info.minY;
            if(width<=0 || height<=0)return;
            float scale=Mathf.Min(area.width/width,area.height/height);
            var rect=new Rect(area.center-new Vector2(width,height)*scale*.5f,new Vector2(width,height)*scale);
            var mesh=context.Allocate(4,6,font.material.mainTexture);var uv=mesh.uvRegion;
            Vector2 Map(Vector2 value)=>uv.position+Vector2.Scale(value,uv.size);
            var ink=new Color32(20,18,15,255);
            mesh.SetNextVertex(new Vertex{position=new Vector3(rect.xMin,rect.yMin,Vertex.nearZ),tint=ink,uv=Map(info.uvTopLeft)});
            mesh.SetNextVertex(new Vertex{position=new Vector3(rect.xMax,rect.yMin,Vertex.nearZ),tint=ink,uv=Map(info.uvTopRight)});
            mesh.SetNextVertex(new Vertex{position=new Vector3(rect.xMax,rect.yMax,Vertex.nearZ),tint=ink,uv=Map(info.uvBottomRight)});
            mesh.SetNextVertex(new Vertex{position=new Vector3(rect.xMin,rect.yMax,Vertex.nearZ),tint=ink,uv=Map(info.uvBottomLeft)});
            foreach(ushort index in new ushort[]{0,1,2,2,3,0})mesh.SetNextIndex(index);
        }
    }
}

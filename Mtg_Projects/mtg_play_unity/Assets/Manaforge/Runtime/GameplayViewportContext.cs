using System;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // Coordinates are canvas UI units; pixel scale is diagnostic and detects display/DPI changes.
    public readonly struct GameplayViewportContext : IEquatable<GameplayViewportContext>
    {
        public readonly Rect Bounds;
        public readonly float PixelsPerUnit;
        public Vector2 Size=>Bounds.size;
        public bool SupportsCustomization=>Size.x+1>=1024 && Size.y+1>=768 || Size.x+1>=1280 && Size.y+1>=720;
        public GameplayViewportContext(Rect bounds,float pixelsPerUnit=1)
        {
            if(!ContainerLayoutResolver.Finite(bounds.x) || !ContainerLayoutResolver.Finite(bounds.y) ||
                !ContainerLayoutResolver.Finite(bounds.width) || !ContainerLayoutResolver.Finite(bounds.height) ||
                bounds.width<1 || bounds.height<1 || !ContainerLayoutResolver.Finite(pixelsPerUnit) || pixelsPerUnit<=0)
                throw new ArgumentException("GAMEPLAY_VIEWPORT");
            Bounds=bounds;PixelsPerUnit=pixelsPerUnit;
        }
        // Preserve 1280x720 sizing at normal desktop ratios, fit ultrawide by height,
        // and never shrink UI below one pixel per unit just to conceal a small viewport.
        public static float ScaleForPixels(Vector2 pixels)=>Mathf.Max(1,Mathf.Min(pixels.x/1280f,pixels.y/720f));
        public static bool TryRead(VisualElement canvas,out GameplayViewportContext context)
        {
            context=default;if(canvas?.panel==null)return false;
            float width=canvas.resolvedStyle.width,height=canvas.resolvedStyle.height;
            if(!ContainerLayoutResolver.Finite(width) || !ContainerLayoutResolver.Finite(height) || width<1 || height<1)return false;
            var origin=RuntimePanelUtils.ScreenToPanel(canvas.panel,Vector2.zero);
            var unit=RuntimePanelUtils.ScreenToPanel(canvas.panel,Vector2.right);
            float scale=(unit-origin).magnitude;scale=scale>0?1/scale:1;
            context=new GameplayViewportContext(new Rect(0,0,width,height),scale);return true;
        }
        public bool Equals(GameplayViewportContext other)=>Bounds==other.Bounds && Mathf.Approximately(PixelsPerUnit,other.PixelsPerUnit);
        public override bool Equals(object other)=>other is GameplayViewportContext value && Equals(value);
        public override int GetHashCode()=>Bounds.GetHashCode();
    }

    // The adapter and its handles consume this same result. No second expansion-direction policy.
    public readonly struct GameplayDrawerGeometry
    {
        public readonly Rect Header;
        public readonly float BodyHeight;
        public readonly bool BodyBelow;
        public readonly Vector2 GripPosition;
        private GameplayDrawerGeometry(Rect header,float height,bool below,Vector2 grip)
        {Header=header;BodyHeight=height;BodyBelow=below;GripPosition=grip;}
        public static GameplayDrawerGeometry Resolve(Rect header,float requestedHeight,GameplayViewportContext viewport)
        {
            if(!ContainerLayoutResolver.Finite(requestedHeight))throw new ArgumentException("DRAWER_BODY_HEIGHT");
            header=ClampHeader(header,viewport.Bounds);
            float above=Mathf.Max(0,header.y-viewport.Bounds.yMin-32),below=Mathf.Max(0,viewport.Bounds.yMax-header.y-32);
            bool down=below>=Mathf.Min(requestedHeight,above);
            float height=Mathf.Max(0,Mathf.Min(requestedHeight,down?below:above));
            // The entire 48x28 grip remains inside the usable viewport, including at edges.
            float gripY=down?32+height-28:-32-height;
            gripY=Mathf.Clamp(gripY,viewport.Bounds.yMin-header.y,Mathf.Max(viewport.Bounds.yMin-header.y,viewport.Bounds.yMax-header.y-28));
            return new GameplayDrawerGeometry(header,height,down,new Vector2(Mathf.Max(0,header.width-48),gripY));
        }
        public static Rect ClampHeader(Rect rect,Rect viewport)
        {
            rect.width=Mathf.Clamp(rect.width,1,viewport.width);rect.height=30;
            rect.x=Mathf.Clamp(rect.x,viewport.xMin,Mathf.Max(viewport.xMin,viewport.xMax-rect.width));
            rect.y=Mathf.Clamp(rect.y,viewport.yMin,Mathf.Max(viewport.yMin,viewport.yMax-30));return rect;
        }
    }
}

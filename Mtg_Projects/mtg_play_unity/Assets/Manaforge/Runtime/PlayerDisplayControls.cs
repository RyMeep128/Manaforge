using System;
using UnityEngine;
using UnityEngine.UIElements;
namespace Manaforge.Play
{
    // Reusable application chrome. No match state, priority policy or game commands.
    public sealed class PlayerDisplayControls : IDisposable
    {
        private const string ModeKey="Manaforge.Display.Fullscreen",WidthKey="Manaforge.Display.WindowWidth",HeightKey="Manaforge.Display.WindowHeight";
        private readonly VisualElement root,chrome;private readonly Button toggle;private readonly IVisualElementScheduledItem ticker;
        private readonly bool remember,wasFocusable;private bool held,disposed,lastFullscreen;private bool? requested;private float deadline;
        private int windowWidth,windowHeight;
        private static bool Fullscreen=>Screen.fullScreenMode!=FullScreenMode.Windowed;
        public PlayerDisplayControls(VisualElement root,bool rememberPreference=true)
        {
            this.root=root??throw new ArgumentNullException(nameof(root));remember=rememberPreference;wasFocusable=root.focusable;root.focusable=true;
            windowWidth=remember?PlayerPrefs.GetInt(WidthKey,Screen.width):Screen.width;windowHeight=remember?PlayerPrefs.GetInt(HeightKey,Screen.height):Screen.height;
            chrome=new VisualElement{name="player-display-controls"};chrome.AddToClassList("mf-display-controls");GameplayTheme.Attach(chrome);
            toggle=new Button(Toggle){name="player-fullscreen-toggle"};GameplayTheme.Button(toggle);chrome.Add(toggle);root.Add(chrome);
            root.RegisterCallback<KeyDownEvent>(Down,TrickleDown.TrickleDown);root.RegisterCallback<KeyUpEvent>(Up,TrickleDown.TrickleDown);
            lastFullscreen=Fullscreen;
            if(remember && PlayerPrefs.GetInt(ModeKey,0)==1 && !Fullscreen)Request(true,false);
            else if(!Fullscreen)RememberWindow();
            Refresh();ticker=root.schedule.Execute(Refresh).Every(100);root.Focus();
        }
        private void Down(KeyDownEvent ev)
        {if(ev.keyCode!=KeyCode.F11)return;if(!held){held=true;Toggle();}ev.StopImmediatePropagation();}
        private void Up(KeyUpEvent ev){if(ev.keyCode==KeyCode.F11){held=false;ev.StopImmediatePropagation();}}
        public void Toggle(){if(!disposed && !requested.HasValue)Request(!Fullscreen,true);}
        private void RememberWindow()
        {if(Screen.width>0 && Screen.height>0){windowWidth=Screen.width;windowHeight=Screen.height;}}
        private void Request(bool fullscreen,bool captureWindow)
        {
            if(captureWindow && !Fullscreen)RememberWindow();
            var display=Screen.mainWindowDisplayInfo;int width=display.width>0?display.width:Screen.currentResolution.width;int height=display.height>0?display.height:Screen.currentResolution.height;
            width=Math.Max(1,width);height=Math.Max(1,height);requested=fullscreen;deadline=Time.realtimeSinceStartup+3;toggle.tooltip="";
            Screen.SetResolution(fullscreen?width:Mathf.Clamp(windowWidth,1,width),fullscreen?height:Mathf.Clamp(windowHeight,1,height),fullscreen?FullScreenMode.FullScreenWindow:FullScreenMode.Windowed);
            Refresh();
        }
        private void Save()
        {if(!remember)return;PlayerPrefs.SetInt(ModeKey,Fullscreen?1:0);PlayerPrefs.SetInt(WidthKey,windowWidth);PlayerPrefs.SetInt(HeightKey,windowHeight);PlayerPrefs.Save();}
        private void Refresh()
        {
            if(disposed)return;
            if(requested.HasValue && Fullscreen==requested.Value){requested=null;lastFullscreen=Fullscreen;Save();}
            if(requested.HasValue && Time.realtimeSinceStartup>deadline){requested=null;toggle.tooltip="The display mode could not be applied. Try again with F11.";}
            if(!requested.HasValue){
                if(!Fullscreen)RememberWindow();
                if(lastFullscreen!=Fullscreen){lastFullscreen=Fullscreen;Save();}
            }
            toggle.text=requested.HasValue?"Switching display...":Fullscreen?"Windowed (F11)":"Fullscreen (F11)";
            toggle.SetEnabled(!requested.HasValue);
            if(!requested.HasValue && !(toggle.tooltip??"").Contains("could not"))toggle.tooltip="Toggle borderless fullscreen. F11 also works while inspecting cards or making choices.";
        }
        public void Dispose()
        {
            if(disposed)return;if(!Fullscreen && !requested.HasValue)RememberWindow();if(!requested.HasValue)Save();disposed=true;ticker.Pause();
            root.UnregisterCallback<KeyDownEvent>(Down,TrickleDown.TrickleDown);root.UnregisterCallback<KeyUpEvent>(Up,TrickleDown.TrickleDown);root.focusable=wasFocusable;chrome.RemoveFromHierarchy();
        }
    }
}

using System;
using System.Linq;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // Uses only the normal UI in the existing opt-in, isolated normal-game acceptance path.
    internal sealed class LiveHudLayoutAcceptance
    {
        private readonly VisualElement root;
        private readonly ArenaGameplayPresentation arena;
        private readonly GameplayMenuOverlay menu;
        private readonly JObject evidence=new JObject();
        private int phase;
        private Rect baseline,applied;
        private float started;
        public bool Failed {get;private set;}
        public bool Complete=>phase==5 && !Failed;
        public LiveHudLayoutAcceptance(VisualElement root,ArenaGameplayPresentation arena,GameplayMenuOverlay menu)
        {this.root=root;this.arena=arena;this.menu=menu;}
        private void Submit(string name)
        {
            var button=root.Q<Button>(name);if(button==null || !button.enabledInHierarchy)throw new InvalidOperationException("Control unavailable: "+name);
            for(var parent=button.parent;parent!=null;parent=parent.parent)if(parent is Foldout foldout)foldout.value=true;
            using(var submit=NavigationSubmitEvent.GetPooled()){submit.target=button;button.SendEvent(submit);}
        }
        private static void Require(bool condition,string message){if(!condition)throw new InvalidOperationException(message);}
        // true holds the gameplay acceptance driver for this frame; the authenticated host still ticks.
        public bool Tick()
        {
            if(Failed || Complete)return false;var editor=arena.LayoutEditor;if(editor==null)return false;
            try{
                if(phase==0){
                    if(!editor.CanOpen)return false;
                    started=Time.realtimeSinceStartup;baseline=editor.Controller.State(GameplayHudIds.Actions).FloatingRect;
                    menu.Open();Submit("game-menu-customize-layout");Require(editor.IsEditing && !menu.IsOpen,"Customize did not open from menu");evidence["opened"]=true;
                    editor.Adjust(GameplayHudIds.Actions,-48,-24,false);editor.Adjust(GameplayHudIds.Actions,32,24,true);phase=1;return true;
                }
                if(!editor.IsEditing && editor.HasRetainedDraft){
                    evidence["interrupted"]=true;
                    if(!editor.CanOpen){started=Time.realtimeSinceStartup;return false;}
                    menu.Open();Submit("game-menu-customize-layout");
                }
                if((phase==3 || phase==4) && !editor.CanOpen && !editor.IsEditing){started=Time.realtimeSinceStartup;return false;}
                Require(Time.realtimeSinceStartup-started<20,"Layout UI timed out");
                switch(phase){
                    case 1:
                        Require(editor.IsEditing && arena.Decisions.LayoutEditing && arena.Decisions.SuppressSpatialInput,"Editor input gate missing");evidence["input_gate"]=true;
                        var offeredButton=arena.Decisions.Root.Query<Button>().ToList().FirstOrDefault(b=>b.enabledInHierarchy);
                        if(offeredButton!=null){using(var submit=NavigationSubmitEvent.GetPooled()){submit.target=offeredButton;offeredButton.SendEvent(submit);}Require(offeredButton.enabledInHierarchy,"Underlying command was dispatched while editing");}
                        var edited=editor.Controller.State(GameplayHudIds.Actions).FloatingRect;
                        Require(edited.position!=baseline.position && edited.size!=baseline.size,"Move or resize was not applied to draft");evidence["moved"]=evidence["resized"]=true;
                        Submit("layout-editor-apply");applied=edited;editor.Adjust(GameplayHudIds.Actions,-24,0,false);Submit("layout-editor-cancel");phase=2;return true;
                    case 2:
                        Require(!editor.IsEditing && !arena.Decisions.LayoutEditing && editor.Controller.State(GameplayHudIds.Actions).FloatingRect==applied,"Cancel did not preserve applied layout");evidence["cancel"]=true;
                        menu.Open();Submit("game-menu-reset-layout");Submit("game-menu-confirm-reset-layout");phase=3;return true;
                    case 3:
                        Require(!editor.OwnsGeometry(GameplayHudIds.Actions) && !editor.HasRetainedDraft && !arena.Decisions.LayoutEditing,"Session recovery failed");evidence["reset"]=true;
                        if(!editor.CanOpen)return false;
                        menu.Open();Submit("game-menu-customize-layout");editor.Adjust(GameplayHudIds.Actions,-48,-24,false);Submit("layout-editor-apply");Submit("layout-editor-cancel");phase=4;return true;
                    case 4:
                        Require(!editor.IsEditing && editor.OwnsGeometry(GameplayHudIds.Actions),"Custom layout missing for full-game acceptance");
                        evidence["custom_gameplay"]=true;phase=5;return false;
                }
            }catch(Exception error){Failed=true;evidence["failure"]=error.Message;Debug.LogError("HUD_LAYOUT_ACCEPTANCE_FAILED: "+error.Message);}
            return true;
        }
        public JObject Certificate(){var result=(JObject)evidence.DeepClone();result["complete"]=Complete;return result;}
    }
}

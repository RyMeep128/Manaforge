using System;
using System.Collections;
using System.Threading.Tasks;
using Manaforge.Play.Protocol;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using UnityEngine.UIElements;
namespace Manaforge.Play.Tests
{
    public sealed class GameplayMenuOverlayTests
    {
        private static void Press(VisualElement target,KeyCode code,bool down=true)
        {var keyboard=new Event{type=down?EventType.KeyDown:EventType.KeyUp,keyCode=code};if(down){using(var ev=KeyDownEvent.GetPooled(keyboard)){ev.target=target;target.SendEvent(ev);}}else{using(var ev=KeyUpEvent.GetPooled(keyboard)){ev.target=target;target.SendEvent(ev);}}}
        private static void Click(VisualElement root,string name){using(var ev=NavigationSubmitEvent.GetPooled()){ev.target=root.Q<Button>(name);root.Q<Button>(name).SendEvent(ev);}}
        [UnityTest] public IEnumerator EscapeWinsOverGameplayAndNavigatesWithoutCommands()
        {
            var node=new UnityEngine.GameObject("Menu test");var settings=ScriptableObject.CreateInstance<PanelSettings>();settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");var doc=node.AddComponent<UIDocument>();doc.panelSettings=settings;
            var root=doc.rootVisualElement;var board=new VisualElement();var origin=new Button{text="Card"};board.Add(origin);root.Add(board);int escapes=0,sends=0,interrupts=0;board.RegisterCallback<KeyDownEvent>(e=>{if(e.keyCode==KeyCode.Escape)escapes++;},TrickleDown.TrickleDown);
            var menu=new GameplayMenuOverlay(root,()=>true,()=>{sends++;return Task.FromException<TrackedCommand>(new Exception("fixture rejection"));},id=>null,()=>interrupts++);
            try{
                yield return null;origin.Focus();Press(origin,KeyCode.Escape);Assert.That(menu.IsOpen,Is.True);Assert.That(escapes,Is.Zero);Assert.That(interrupts,Is.EqualTo(1));
                using(var navigation=NavigationCancelEvent.GetPooled()){navigation.target=root.Q<Button>("game-menu-resume");root.SendEvent(navigation);}Assert.That(menu.IsOpen,Is.True,"Keyboard Escape and navigation cancel in one frame must act once");
                Press(root,KeyCode.Escape);Assert.That(menu.IsOpen,Is.True,"Held Escape must not close the menu");Press(root,KeyCode.Escape,false);yield return null;
                Assert.That(root.focusController.focusedElement,Is.SameAs(root.Q<Button>("game-menu-resume")));
                Click(root,"game-menu-options");Press(root.Q<Button>("game-menu-back"),KeyCode.Escape);Press(root,KeyCode.Escape,false);Assert.That(menu.IsOpen,Is.True);
                Click(root,"game-menu-concede");Assert.That(root.focusController.focusedElement,Is.SameAs(root.Q<Button>("game-menu-cancel-concede")));Click(root,"game-menu-cancel-concede");Assert.That(sends,Is.Zero);
                origin.Focus();Assert.That(root.focusController.focusedElement,Is.SameAs(root.Q<Button>("game-menu-resume")),"Focus cannot escape the modal");
                Click(root,"game-menu-resume");Assert.That(menu.IsOpen,Is.False);Assert.That(root.focusController.focusedElement,Is.SameAs(origin));Assert.That(Time.timeScale,Is.EqualTo(1));
                menu.Open();Click(root,"game-menu-concede");Click(root,"game-menu-confirm-concede");yield return new WaitForSecondsRealtime(.15f);Assert.That(sends,Is.EqualTo(1));Assert.That(root.Q<Label>("game-menu-status").text,Does.Contain("fixture rejection"));menu.EndMatch();Assert.That(menu.IsOpen,Is.False);
            }finally{menu.Dispose();UnityEngine.Object.Destroy(node);UnityEngine.Object.Destroy(settings);}yield return null;
        }
        [UnityTest] public IEnumerator DisplayButtonLivesOnlyInOptionsAndF11DoesNotNavigateMenu()
        {
            var node=new UnityEngine.GameObject("Display menu test");var settings=ScriptableObject.CreateInstance<PanelSettings>();var doc=node.AddComponent<UIDocument>();doc.panelSettings=settings;var root=doc.rootVisualElement;
            var menu=new GameplayMenuOverlay(root,()=>false,()=>Task.FromResult<TrackedCommand>(null),id=>null);var display=new PlayerDisplayControls(root,false,menu.OptionsContent);
            try{
                yield return null;Assert.That(menu.OptionsContent.Q<Button>("player-fullscreen-toggle"),Is.Not.Null);Assert.That(root.Query<Button>("player-fullscreen-toggle").ToList().Count,Is.EqualTo(1));
                menu.Open();Click(root,"game-menu-options");var button=root.Q<Button>("player-fullscreen-toggle");Assert.That(button.resolvedStyle.display,Is.EqualTo(DisplayStyle.Flex));Assert.That(root.Q<Button>("game-menu-concede").enabledSelf,Is.False);
                // A synthetic F11 must reach the root display listener even from a modal button.
                var old=Screen.fullScreenMode;Press(button,KeyCode.F11);Press(button,KeyCode.F11,false);Assert.That(menu.IsOpen,Is.True);
                yield return new WaitForSecondsRealtime(.3f);Screen.fullScreenMode=old;
            }finally{display.Dispose();menu.Dispose();UnityEngine.Object.Destroy(node);UnityEngine.Object.Destroy(settings);}yield return null;
        }
    }
}

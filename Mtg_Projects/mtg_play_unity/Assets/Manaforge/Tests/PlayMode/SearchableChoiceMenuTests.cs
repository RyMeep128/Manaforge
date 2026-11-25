using System.Collections;
using System.Linq;
using Manaforge.Play.Protocol;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using UnityEngine.UIElements;
using GameObject=UnityEngine.GameObject;

namespace Manaforge.Play.Tests
{
    public sealed class SearchableChoiceMenuTests
    {
        private GameObject node;private PanelSettings settings;private VisualElement root;
        private static ProjectedDecision Decision(bool emptyDeck=false)
        {
            var options=new JArray();
            foreach(string type in new[]{"Human","Elf","Time Lord"})options.Add(new JObject{["option_id"]="opaque-"+type,["label"]=type,["object_id"]=null,["player_id"]=null,["selected"]=false,["suggested"]=!emptyDeck && type!="Time Lord"});
            // Real creature-type lists exceed the former 256-entry bridge limit.
            for(int i=0;i<300;i++)options.Add(new JObject{["option_id"]="opaque-extra-"+i,["label"]="Type "+i,["object_id"]=null,["player_id"]=null,["selected"]=false,["suggested"]=false});
            return new ProjectedDecision(new CardProjectionContext("session","viewer",1),new JObject{["decision_id"]="decision",["player_id"]="viewer",["family"]="selection",["prompt"]="Choose a creature type",["menu"]="creature_type",["options"]=options,["amounts"]=new JArray(),["cancellable"]=false,["can_finish"]=false,["is_priority"]=false});
        }
        [UnitySetUp] public IEnumerator Setup(){node=new GameObject("Choice menu tests");settings=ScriptableObject.CreateInstance<PanelSettings>();settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");var document=node.AddComponent<UIDocument>();document.panelSettings=settings;root=document.rootVisualElement;root.style.width=600;yield return null;}
        [UnityTearDown] public IEnumerator Cleanup(){Object.Destroy(node);Object.Destroy(settings);yield return null;}
        [UnityTest] public IEnumerator DefaultsToDeckAndSearchFindsAnOffDeckTypeWithoutSubmittingTypedText()
        {
            ProjectedChoiceOption submitted=null;var decision=Decision();var menu=new SearchableChoiceMenu(decision,option=>submitted=option);root.Add(menu.Root);yield return null;
            var list=menu.Root.Q<ListView>();Assert.That(list.itemsSource.Cast<ProjectedChoiceOption>().Select(option=>option.Label),Is.EqualTo(new[]{"Elf","Human"}));
            var confirm=menu.Root.Q<Button>("choice-menu-confirm");Assert.That(confirm.enabledSelf,Is.False);
            menu.Root.Q<TextField>().value=" tImE LoRd ";yield return null;
            Assert.That(list.itemsSource.Count,Is.EqualTo(1));Assert.That(submitted,Is.Null);Assert.That(confirm.enabledSelf,Is.False);
            list.SetSelection(0);yield return null;Assert.That(confirm.enabledSelf,Is.True);
            using(var click=NavigationSubmitEvent.GetPooled()){click.target=confirm;confirm.SendEvent(click);}yield return null;
            Assert.That(submitted,Is.SameAs(decision.Options[2]));Assert.That(submitted.OptionId,Is.EqualTo("opaque-Time Lord"));
            menu.Root.Q<TextField>().value="no such creature type";yield return null;
            Assert.That(list.itemsSource.Count,Is.Zero);Assert.That(confirm.enabledSelf,Is.False);
        }
        [UnityTest] public IEnumerator AllTypesAreReachableAndEmptyDeckNeverAutomaticallySelectsAType()
        {
            var menu=new SearchableChoiceMenu(Decision(true),_=>Assert.Fail("No automatic submissions"));root.Add(menu.Root);yield return null;
            var list=menu.Root.Q<ListView>();Assert.That(list.itemsSource.Count,Is.Zero);Assert.That(menu.Root.Q<Button>("choice-menu-confirm").enabledSelf,Is.False);
            var all=menu.Root.Q<Button>("choice-menu-all");using(var click=NavigationSubmitEvent.GetPooled()){click.target=all;all.SendEvent(click);}yield return null;
            Assert.That(list.itemsSource.Count,Is.EqualTo(303));Assert.That(menu.Root.Q<Button>("choice-menu-confirm").enabledSelf,Is.False);
            // Virtualization must avoid mounting hundreds of row elements.
            Assert.That(list.Query<Label>().ToList().Count,Is.LessThan(40));
            menu.Root.SetEnabled(false);Assert.That(all.enabledInHierarchy,Is.False);
        }
    }
}

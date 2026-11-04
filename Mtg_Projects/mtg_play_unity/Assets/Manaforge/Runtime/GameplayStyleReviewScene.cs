using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEngine.UIElements;
namespace Manaforge.Play
{
    // Explicit synthetic component sheet, never a live multiplayer session.
    public sealed class GameplayStyleReviewScene : MonoBehaviour
    {
        private readonly List<IDisposable> owned=new List<IDisposable>();
        private ArenaGameplayPresentation table;private string tableJson,tableSession,tableViewer;private ViewerSurfaceTicket tableTicket;
        private PanelSettings settings;private UIDocument document;private VisualElement content;
        public static void Populate(VisualElement root,ICollection<IDisposable> owned,int seats=3,bool vertical=false)
        {
            GameplayTheme.Attach(root);
            var title=new Label("MANAFORGE / THE FORGE");title.AddToClassList("mf-review-title");root.Add(title);
            var note=new Label("Synthetic component review | Original slate, metal and ember theme | No game engine or private cards");note.AddToClassList("mf-review-note");root.Add(note);
            var row=new VisualElement();row.AddToClassList("mf-review-row");if(vertical)row.style.flexDirection=FlexDirection.Column;root.Add(row);
            for(int i=0;i<seats;i++){
                string id="review-seat-"+i;var tile=new VisualElement();tile.AddToClassList("mf-review-tile");tile.style.flexGrow=1;row.Add(tile);
                tile.Add(new Label(i==0?"YOU / NORMAL":i==1?"SEAT B / TARGET":"SEAT C / PRIORITY"));
                var seatRow=new VisualElement();seatRow.AddToClassList("mf-review-seat");tile.Add(seatRow);
                var panel=new PlayerPanel();panel.Bind(id,i==0?"You":"Player "+(i+1));panel.Present(i==0?20:i==1?34:17,i==2,i==1,true);seatRow.Add(panel);owned.Add(panel);
                var library=new ZonePile("library");library.Bind(id);library.Present(i==0?53:(long?)null,null,null,false);seatRow.Add(library);owned.Add(library);
                var graveyard=new ZonePile("graveyard");graveyard.Bind(id);graveyard.Present(i+1,null,"Known card",false);seatRow.Add(graveyard);owned.Add(graveyard);
                var message=new Label("Select a highlighted player or browse a pile.");message.style.whiteSpace=WhiteSpace.Normal;tile.Add(message);
                panel.Activated+=player=>message.text="Target request: "+player;
                library.BrowseRequested+=(zone,owner)=>message.text="Browse request: "+owner+" / "+zone;
                graveyard.BrowseRequested+=(zone,owner)=>message.text="Browse request: "+owner+" / "+zone;
                var buttons=new VisualElement();buttons.style.flexDirection=FlexDirection.Row;tile.Add(buttons);
                var primary=new Button(()=>message.text="Fixture confirmation only"){text="Confirm"};GameplayTheme.Button(primary,true);buttons.Add(primary);
                var secondary=new Button(()=>message.text="Fixture cancelled"){text="Cancel"};GameplayTheme.Button(secondary);buttons.Add(secondary);
                var unavailable=new Button(){text="Unavailable"};unavailable.SetEnabled(false);GameplayTheme.Button(unavailable);tile.Add(unavailable);
                var state=new Label(i==0?"Pending | Waiting for confirmation":i==1?"Uncertain | Check session status":"Confirmed | Ready");state.style.whiteSpace=WhiteSpace.Normal;tile.Add(state);
                tile.AddToClassList(i==0?"command-pending":i==1?"command-uncertain":"command-confirmed");tile.AddToClassList("mf-decision");
            }
            string browserOwner="review-seat-"+(seats-1),browserName="Player "+seats;
            var browser=new ZoneBrowser();browser.style.position=Position.Relative;browser.style.height=300;browser.Present(browserOwner,"library",browserName,0,42);root.Add(browser);owned.Add(browser);
            browser.Closed+=()=>browser.ClearBinding();browser.BrowseRequested+=(zone,owner)=>browser.Present(owner,zone,browserName,0,zone=="library"?42:(long?)null);
        }
        private void Awake()
        {
            settings=ScriptableObject.CreateInstance<PanelSettings>();settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");settings.scaleMode=PanelScaleMode.ConstantPixelSize;
            document=gameObject.AddComponent<UIDocument>();document.panelSettings=settings;var root=document.rootVisualElement;GameplayTheme.Attach(root);
            var scroll=new ScrollView();scroll.style.flexGrow=1;root.Add(scroll);
            var navigation=new VisualElement();navigation.style.flexDirection=FlexDirection.Row;scroll.Add(navigation);
            foreach(var mode in new[]{"Component sheet","Side by side","Multi-seat"}){string selected=mode;var button=new Button(()=>Show(selected)){text=mode};GameplayTheme.Button(button);navigation.Add(button);}
            var reduced=new Toggle("Reduced motion");reduced.RegisterValueChangedCallback(e=>root.EnableInClassList("reduced-motion",e.newValue));scroll.Add(reduced);
            content=new VisualElement();content.style.paddingLeft=24;content.style.paddingRight=24;content.style.paddingTop=20;scroll.Add(content);Show("Multi-seat");
        }
        private void Show(string mode)
        {
            table?.Dispose();table=null;settings.scaleMode=PanelScaleMode.ConstantPixelSize;
            if(content.panel==null){var root=document.rootVisualElement;root.Clear();var scroll=new ScrollView();scroll.style.flexGrow=1;root.Add(scroll);content=new VisualElement();content.style.paddingLeft=24;content.style.paddingRight=24;content.style.paddingTop=20;scroll.Add(content);}
            foreach(var item in owned)item.Dispose();owned.Clear();content.Clear();
            Populate(content,owned,mode=="Multi-seat"?3:2,mode=="Component sheet");
        }
        private IEnumerator Start()
        {
            string output=ArtworkFixtureScene.Argument("-manaforgeStyleCapture");if(output==null)yield break;
            Directory.CreateDirectory(output);
            // Force an initial swapchain resize; a hidden Windows launch may not paint its initial size.
            Screen.SetResolution(1366,768,FullScreenMode.Windowed);for(int i=0;i<60;i++)yield return null;
            var resolutions=new JArray();
            foreach(var size in new[]{new Vector2Int(1280,720),new Vector2Int(1366,768),new Vector2Int(1920,1080),new Vector2Int(2560,1440)}){
                Screen.SetResolution(size.x,size.y,FullScreenMode.Windowed);
                for(int i=0;i<30;i++)yield return null;
                Show("Side by side");for(int i=0;i<10;i++)yield return null;
                yield return new WaitForEndOfFrame();ScreenCapture.CaptureScreenshot(Path.Combine(output,"side-by-side-"+size.x+"x"+size.y+".png"));
                for(int i=0;i<5;i++)yield return null;
                Show("Multi-seat");for(int i=0;i<10;i++)yield return null;
                yield return new WaitForEndOfFrame();ScreenCapture.CaptureScreenshot(Path.Combine(output,"multi-seat-"+size.x+"x"+size.y+".png"));
                for(int i=0;i<5;i++)yield return null;
                string fixture=ArtworkFixtureScene.Argument("-manaforgeStyleTableFixture");
                if(fixture!=null){
                    ShowTable(fixture);for(int i=0;i<20;i++)yield return null;
                    table.Surface.TryPresent(tableTicket,ViewerCardProjection.ParseSnapshot(tableJson,tableSession,tableViewer,0,true));
                    table.Present(ViewerDecisionProjection.ParseSnapshot(tableJson,tableSession,tableViewer,0,true));for(int i=0;i<5;i++)yield return null;
                    yield return new WaitForEndOfFrame();ScreenCapture.CaptureScreenshot(Path.Combine(output,"default-1v1-"+size.x+"x"+size.y+".png"));
                    for(int i=0;i<5;i++)yield return null;
                }
                resolutions.Add(new JObject{["requested_width"]=size.x,["requested_height"]=size.y,["observed_width"]=Screen.width,["observed_height"]=Screen.height});
            }
            File.WriteAllText(Path.Combine(output,"resolution-proof.json"),new JObject{["fixture_only"]=true,["sizes"]=resolutions}.ToString());
            File.WriteAllText(Path.Combine(output,"revision.txt"),ArtworkFixtureScene.Argument("-manaforgeRevision")??"uncommitted working tree");
            Application.Quit(0);
        }
        private void ShowTable(string fixture)
        {
            foreach(var item in owned)item.Dispose();owned.Clear();table?.Dispose();content.Clear();
            settings.scaleMode=PanelScaleMode.ScaleWithScreenSize;settings.referenceResolution=new Vector2Int(1280,720);
            var root=document.rootVisualElement;root.Clear();
            var note=new Label("SYNTHETIC 1v1 VISUAL FIXTURE / Missing artwork intentional / No live decisions");note.style.position=Position.Absolute;note.style.left=20;note.style.bottom=0;note.style.fontSize=12;root.Add(note);
            table=new ArenaGameplayPresentation(root);
            var prompt=new VisualElement();prompt.AddToClassList("mf-decision");prompt.Add(new Label("Fixture prompt / Main phase"));
            var pass=new Button(){text="Pass priority"};GameplayTheme.Button(pass,true);prompt.Add(pass);prompt.Add(new Label("Synthetic controls: no command is sent."));root.Q("table-choices").Add(prompt);
            var envelope=(JObject)JObject.Parse(File.ReadAllText(fixture))["positive"][0]["envelope"].DeepClone();var snapshot=envelope["body"]["snapshot"];
            tableSession=(string)snapshot["session_id"];tableViewer=(string)snapshot["viewer_id"];string other=(string)snapshot["players"][1]["player_id"];
            foreach(var player in snapshot["players"]){player["life"]=(string)player["player_id"]==tableViewer?20:16;player["library_count"]=47;player["hand_count"]=4;}
            snapshot["decision"]=null;snapshot["actions"]=new JArray();snapshot["turn"]=3;snapshot["phase"]="PRECOMBAT_MAIN";
            var original=snapshot["objects"][0].DeepClone();var cards=new JArray();
            for(int i=0;i<13;i++){
                var card=original.DeepClone();bool enemy=i>=8;card["object_id"]="review-card-"+i;card["owner_id"]=enemy?other:tableViewer;card["controller_id"]=enemy?other:tableViewer;
                card["zone"]=i<4?"hand":i==12?"graveyard":"battlefield";card["characteristics"]["name"]=i<4?"Forge Study "+(i+1):i%2==0?"Ember Sentinel":"Ashen Workshop";
                card["characteristics"]["type_line"]=i>=4 && i%2==1?"Basic Land":"Artifact Creature";card["tapped"]=i==5;cards.Add(card);
            }
            snapshot["objects"]=cards;tableJson=envelope.ToString();tableTicket=table.Surface.BeginViewer(tableSession,tableViewer);
            table.Surface.TryPresent(tableTicket,ViewerCardProjection.ParseSnapshot(tableJson,tableSession,tableViewer,0,true));note.BringToFront();
        }
        private void OnDestroy(){table?.Dispose();foreach(var item in owned)item.Dispose();owned.Clear();if(settings!=null)Destroy(settings);}
    }
}

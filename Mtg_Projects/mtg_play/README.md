# Unity Play

Unity is the gameplay UI and Java/XMage owns rules and game decisions. The retired
Python game adapter and Qt game table have been removed.

The Manaforge Play workspace selects Freeform or Commander, a saved deck for you,
a saved deck for the AI opponent, and a mana payment preference. **Start Game**
launches the Unity player. There are no Python gameplay or preview launch buttons.
Close the Unity window to end a session; application shutdown also cleans up its
owned game processes. Returning to Play reloads saved decks.

Python modules here remain for saved-deck preparation, artwork export, protocol
contracts, pinned engine provisioning, and Unity process startup and cleanup.
The Java sources, shared protocol fixtures, and Unity project remain in use.
Historical Python protocol fixtures are retained as a cross-language validation
corpus; they no longer require the retired adapter to generate them.

Build the Windows Unity player before starting a game. See
[Unity tooling](../../tools/unity-play.ps1), the
[Unity + Java roadmap](../../docs/play-unity-java-roadmap.md), and
[development workflow](../../docs/development-workflow.md). Test suites run in
GitHub Actions; a successful launch alone does not prove playable acceptance.

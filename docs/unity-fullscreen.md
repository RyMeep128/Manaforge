# Unity fullscreen

Use **Fullscreen (F11)** in the top application chrome, or press **F11**, to switch to borderless fullscreen on the window's current monitor. Use the same control to return to the previous window size. The selected mode and window size are stored in Unity PlayerPrefs; a new interactive game restores fullscreen when selected. First launch remains windowed. Automated game acceptance does not restore or save the interactive display preference.

`PlayerDisplayControls` owns window-mode requests, asynchronous transition feedback and preference storage. It is composed by `LiveGameScene`, so all gameplay layouts share it without embedding window logic in a table view. Geometry/styles belong to the shared theme. It submits no gameplay commands, and F11 is handled before descendant gameplay controls. Existing inspection, targeting, reveals and required choices remain intact through a resize.

The operating system controls window position; the component restores size and clamps it to the current monitor. Borderless mode uses the current monitor's desktop dimensions, without changing its display resolution. This adds no exclusive-fullscreen or resolution selector.

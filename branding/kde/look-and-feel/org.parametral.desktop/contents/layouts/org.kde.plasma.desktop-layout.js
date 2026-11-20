// Parametral dock layout.
//
// Shipped inside the look-and-feel package, so a fresh account (or "Apply" in System
// Settings → Global Theme) gets this instead of Plasma's default bar: a tall bottom dock
// with the gauge launcher, icon-only tasks, tray and clock.
//
// What this build actually honours, measured on Plasma 6.5 (Arch, 2026-11):
//   panel.height            yes (40 px)
//   panel.hiding            yes ("none": always visible)
//   panel.floating          accepted by the API and written to the config, but NOT rendered —
//                           the panel stays edge-to-edge. Do not rely on it for an island look.
//   panel.minimum/maxLength accepted, also not rendered while the panel fills the screen
//   panel.alignment         accepted, no visible effect on a full-width panel
// The two "island" lines are kept because they are harmless here and correct on builds that
// do render floating panels.

var panel = new Panel
var panelScreen = panel.screen

// One plate at the top, 40 px, always visible. This is not a dock: no autohide, no
// ultrawide cap, no second surface. The wallpaper draws the plate; the panel sits on it.
panel.location = "top"
panel.hiding = "none"
panel.height = 40
panel.floating = false
panel.alignment = "center"

// The workspace ruler (5 ticks, 6×2 / active 14×2) is our own applet, not the stock
// workspaces widget: stock dots and pills break the one signature. See T14.

panel.addWidget("org.kde.plasma.kickoff")
panel.addWidget("org.kde.plasma.icontasks")
panel.addWidget("org.kde.plasma.marginsseparator")
panel.addWidget("org.kde.plasma.systemtray")
panel.addWidget("org.kde.plasma.digitalclock")

// Wallpaper: ours, through the image plugin.
var desktopsArray = desktopsForActivity(currentActivity());
for (var j = 0; j < desktopsArray.length; j++) {
    desktopsArray[j].wallpaperPlugin = 'org.kde.image';
    desktopsArray[j].currentConfigGroup = ["Wallpaper", "org.kde.image", "General"];
    desktopsArray[j].writeConfig("Image", "/usr/share/wallpapers/Parametral/contents/images/2560x1440.png");
}

// Parametral dock layout.
//
// Shipped inside the look-and-feel package, so a fresh account (or "Apply" in System
// Settings → Global Theme) gets this instead of Plasma's default bar: a floating, centred
// panel with the gauge launcher, icon-only tasks and the tray. Written against the API the
// stock template uses (Panel, panel.height, panel.addWidget), because guessing newer keys
// silently produces no panel at all.

var panel = new Panel
var panelScreen = panel.screen

panel.location = "bottom"

// 3 gridUnits ≈ 56 px at 96 dpi: tall enough for 32 px icons, still a bar and not a slab.
panel.height = 2 * Math.ceil(gridUnit * 3 / 2)

// floating + centred is what makes it read as a dock rather than a window frame edge
panel.floating = true
panel.alignment = "center"

// On ultrawide screens an unconstrained dock runs the whole width and looks like a taskbar
// again, so cap it at 16:9 like the stock template does with 21:9.
var geo = screenGeometry(panelScreen)
var maximumWidth = Math.ceil(geo.height * (16 / 9))
if (geo.formFactor === "horizontal" && geo.width > maximumWidth) {
    panel.minimumLength = maximumWidth
    panel.maximumLength = maximumWidth
}

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

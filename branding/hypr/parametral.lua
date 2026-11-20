-- Parametral OS — Hyprland session.
--
-- Hyprland 0.57 takes a Lua config (the old hyprland.conf syntax no longer parses), so this
-- file is Lua. Everything here is a plain file on purpose: the AI layer reads and writes it,
-- and a btrfs snapshot of /etc/parametral/hypr is a complete undo.
-- Colours: graphite #12171E, amber #E0A93B — same language as the rest of the system.

hl.monitor({ output = "", mode = "preferred", position = "auto", scale = "auto" })

hl.env("XCURSOR_THEME", "Parametral")
hl.env("XCURSOR_SIZE", "24")
hl.env("HYPRCURSOR_THEME", "Parametral")
hl.env("HYPRCURSOR_SIZE", "24")

hl.config({
    general = {
        gaps_in     = 6,
        gaps_out    = 16,
        border_size = 2,

        col = {
            active_border   = "rgba(e0a93bff)",
            inactive_border = "rgba(2a323cff)",
        },

        layout        = "dwindle",
        allow_tearing = false,
    },

    decoration = {
        rounding       = 14,
        rounding_power = 2,
        active_opacity   = 1.0,
        inactive_opacity = 0.97,

        shadow = {
            enabled      = true,
            range        = 20,
            render_power = 3,
            color        = 0x66000000,
        },

        blur = {
            enabled  = true,
            size     = 6,
            passes   = 2,
            vibrancy = 0.08,
        },
    },

    animations = { enabled = true },

    input = {
        kb_layout    = "tr",
        follow_mouse = 1,
        sensitivity  = 0,
    },

    dwindle = {
        -- 0.57 dropped `pseudotile`; only the keys the stub lists are accepted
        preserve_split = true,
        smart_split    = true,
    },

    misc = {
        force_default_wallpaper   = 0,
        disable_hyprland_logo     = true,
        disable_splash_rendering  = true,
        focus_on_activate         = true,
    },
})

-- curves: the same soft ease used by the KDE dock
hl.curve("param", { type = "bezier", points = { {0.2, 0.9}, {0.2, 1} } })
hl.curve("soft",  { type = "bezier", points = { {0.35, 1.2}, {0.3, 1} } })

hl.animation({ leaf = "global",     enabled = true, speed = 8,  bezier = "param" })
hl.animation({ leaf = "windows",    enabled = true, speed = 5,  bezier = "param" })
hl.animation({ leaf = "windowsOut", enabled = true, speed = 4,  bezier = "param", style = "popin 92%" })
hl.animation({ leaf = "border",     enabled = true, speed = 8,  bezier = "param" })
hl.animation({ leaf = "fade",       enabled = true, speed = 6,  bezier = "param" })
hl.animation({ leaf = "workspaces", enabled = true, speed = 5,  bezier = "soft"  })

-- --- keys --------------------------------------------------------------------
local mod = "SUPER"

hl.bind(mod .. " + Return", hl.dsp.exec_cmd("konsole"))
hl.bind(mod .. " + E",      hl.dsp.exec_cmd("dolphin"))
hl.bind(mod .. " + Space",  hl.dsp.exec_cmd("/usr/local/bin/parametral-launcher"))
hl.bind(mod .. " + Q",      hl.dsp.window.close())
hl.bind(mod .. " + L",      hl.dsp.exec_cmd("hyprlock --config /etc/parametral/hypr/hyprlock.conf"))
hl.bind(mod .. " + Escape", hl.dsp.exec_cmd("qs -p /usr/share/parametral/shell/shell.qml ipc call powermenu toggle"))
hl.bind(mod .. " + M",      hl.dsp.exit())

hl.bind(mod .. " + left",  hl.dsp.focus({ direction = "left" }))
hl.bind(mod .. " + right", hl.dsp.focus({ direction = "right" }))
hl.bind(mod .. " + up",    hl.dsp.focus({ direction = "up" }))
hl.bind(mod .. " + down",  hl.dsp.focus({ direction = "down" }))

for i = 1, 5 do
    hl.bind(mod .. " + " .. i,         hl.dsp.focus({ workspace = i }))
    hl.bind(mod .. " + SHIFT + " .. i, hl.dsp.window.move({ workspace = i }))
end

-- --- session startup ---------------------------------------------------------
hl.on("hyprland.start", function()
    -- hyprpaper 0.57 rejects its own IPC requests and leaves the screen flat;
    -- swaybg is the boring, working path for a static wallpaper
    hl.exec_cmd("swaybg -i /usr/share/wallpapers/Parametral/contents/images/2560x1440.png -m fill")
    -- our own shell (Quickshell/QML). waybar stays in the tree as a fallback.
    hl.exec_cmd("qs -p /usr/share/parametral/shell/shell.qml")
    hl.exec_cmd("/usr/local/bin/parametral-approvals")
end)

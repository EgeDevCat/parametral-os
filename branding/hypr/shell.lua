-- What starts with the session.
--
-- The shell is Noctalia (MIT, noctalia.dev). Our own Quickshell surfaces in shell/ are kept in
-- the tree as experiments and are deliberately NOT started: two bars would fight for the same
-- exclusive zone, and Noctalia's polkit agent is the one that answers pkexec.

hl.on("hyprland.start", function()
    -- Noctalia draws the wallpaper itself ([wallpaper] in its config); no swaybg, no hyprpaper.
    hl.exec_cmd("noctalia")

    -- first-party app: the approval window the AI layer talks to
    hl.exec_cmd("/usr/local/bin/parametral-approvals")
end)

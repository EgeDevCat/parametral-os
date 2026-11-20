-- Values shared by every other module.

mod = "SUPER"

local palette = {
    graphite = "0b0f14ff",
    surface  = "12171eff",
    card     = "1a2029ff",
    amber    = "e0a93bff",
    edge     = "2a323cff",
    text     = "e9e4d8ff",
}

function colour(name)
    return "rgba(" .. (palette[name] or palette.text) .. ")"
end

wallpaper = "/usr/share/wallpapers/Parametral/contents/images/2560x1440.png"

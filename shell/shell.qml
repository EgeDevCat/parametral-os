// Parametral Shell — the bar.
//
// Quickshell (QML) on Hyprland. Everything is a file the AI can rewrite, and the whole surface
// is one design language: islands floating over the wallpaper, graphite body, amber edge.
//
// Geometry note: the panel uses PanelWindow.margins (not manual anchors) — anchoring the
// content to the window edge pushed the islands below the screen edge on a 1280x800 panel.
//
// Left to right: launcher · workspaces · [space] · status (volume, battery, network) · clock ·
// power. Islands only exist when they have something to say: an empty island reads as a
// rendering bug, so the tray and the battery hide themselves when absent.

import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Wayland
import Quickshell.Hyprland
import Quickshell.Io
import Quickshell.Services.SystemTray
import Quickshell.Services.UPower
import Quickshell.Networking

ShellRoot {
    id: root

    readonly property color bg:     "#12171E"
    readonly property color bgSoft: "#171D25"
    readonly property color text:   "#E9E4D8"
    readonly property color muted:  "#9AA4B2"
    readonly property color faint:  "#6B7280"
    readonly property color amber:  "#E0A93B"
    readonly property color inkOnAmber: "#1A150A"
    readonly property color edge:   Qt.rgba(0.878, 0.663, 0.231, 0.22)
    readonly property color edgeSoft: Qt.rgba(0.60, 0.64, 0.70, 0.18)

    readonly property int wsCount: 5
    property string volumeText: "—"

    Process {
        id: volumeProc
        command: ["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"]
        running: false
        stdout: StdioCollector {
            onStreamFinished: {
                const match = this.text.match(/Volume:\s*([0-9.]+)/)
                if (this.text.includes("MUTED")) root.volumeText = "sessiz"
                else if (match) root.volumeText = Math.round(parseFloat(match[1]) * 100) + "%"
                else root.volumeText = "—"
            }
        }
    }

    Timer {
        interval: 3000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: volumeProc.running = true
    }

    component Island: Rectangle {
        radius: 14
        color: root.bg
        border.color: root.edge
        border.width: 1
        Behavior on color { ColorAnimation { duration: 120 } }
    }

    // a clickable island slot: hover lifts the edge, press dims it
    component Chip: Rectangle {
        id: chip
        property string label: ""
        property bool active: false
        signal tapped()

        radius: 10
        color: active ? root.amber
             : area.containsMouse ? root.bgSoft
             : "transparent"
        Behavior on color { ColorAnimation { duration: 110 } }

        Text {
            anchors.centerIn: parent
            text: chip.label
            color: chip.active ? root.inkOnAmber : root.muted
            font.pixelSize: 12
            font.bold: chip.active
        }

        MouseArea {
            id: area
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: chip.tapped()
        }
    }

    PanelWindow {
        id: bar
        anchors.bottom: true
        anchors.left: true
        anchors.right: true

        implicitHeight: 56
        color: "transparent"
        exclusiveZone: 0

        margins {
            left: 14
            right: 14
            bottom: 8
        }

        RowLayout {
            anchors.fill: parent
            spacing: 10

            // ---- launcher -------------------------------------------------
            Island {
                Layout.preferredWidth: 46
                Layout.fillHeight: true
                color: launcherArea.containsMouse ? root.bgSoft : root.bg

                // the gauge, drawn: same mark as the apps, no icon file to go missing
                Canvas {
                    anchors.centerIn: parent
                    width: 26
                    height: 26
                    onPaint: {
                        const ctx = getContext("2d")
                        ctx.reset()
                        const c = width / 2, r = width * 0.42
                        ctx.strokeStyle = root.amber
                        ctx.lineWidth = 1.6
                        ctx.beginPath()
                        for (let i = 0; i < 12; i++) {
                            const a = (Math.PI * 2 * i) / 12 - Math.PI / 2
                            ctx.moveTo(c + Math.cos(a) * r * 0.78, c + Math.sin(a) * r * 0.78)
                            ctx.lineTo(c + Math.cos(a) * r, c + Math.sin(a) * r)
                        }
                        ctx.stroke()
                        ctx.beginPath()
                        ctx.arc(c, c, r * 0.62, 0, Math.PI * 2)
                        ctx.stroke()
                        ctx.fillStyle = root.amber
                        ctx.beginPath()
                        ctx.arc(c, c, 2.2, 0, Math.PI * 2)
                        ctx.fill()
                    }
                }

                MouseArea {
                    id: launcherArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: Quickshell.execDetached(["/usr/local/bin/parametral-launcher"])
                }
            }

            // ---- workspaces -----------------------------------------------
            Island {
                Layout.preferredWidth: wsRow.implicitWidth + 20
                Layout.fillHeight: true

                Row {
                    id: wsRow
                    anchors.centerIn: parent
                    spacing: 4

                    // fixed 1..5: a workspace you cannot see is a workspace you forget
                    Repeater {
                        model: root.wsCount

                        Chip {
                            required property int index
                            readonly property int id: index + 1
                            readonly property var ws: Hyprland.workspaces.values.find(w => w.id === id)
                            label: id
                            active: Hyprland.focusedWorkspace?.id === id
                            width: 30
                            height: 30
                            opacity: (active || ws) ? 1.0 : 0.55
                            onTapped: Hyprland.dispatch("workspace " + id)
                        }
                    }
                }
            }

            Item { Layout.fillWidth: true }

            // ---- tray ------------------------------------------------------
            Island {
                visible: SystemTray.items.values.length > 0
                Layout.preferredWidth: Math.max(52, trayRow.implicitWidth + 22)
                Layout.fillHeight: true

                Row {
                    id: trayRow
                    anchors.centerIn: parent
                    spacing: 10

                    Repeater {
                        model: SystemTray.items

                        Image {
                            required property var modelData
                            width: 17
                            height: 17
                            source: modelData.icon
                            fillMode: Image.PreserveAspectFit
                            opacity: modelData.status === 1 ? 1.0 : 0.45
                        }
                    }
                }
            }

            // ---- status: volume, battery, network --------------------------
            Island {
                Layout.preferredWidth: statusRow.implicitWidth + 24
                Layout.fillHeight: true

                Row {
                    id: statusRow
                    anchors.centerIn: parent
                    spacing: 12

                    // volume: polled from wpctl — Pipewire's node api reports 0 for a
                    // suspended sink, and a wrong number is worse than a stale one
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: root.volumeText
                        color: root.volumeText === "sessiz" ? root.faint : root.muted
                        font.pixelSize: 11
                        font.family: "monospace"
                    }

                    // battery: only when there is one to report
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        visible: UPower.displayDevice?.ready ?? false
                        text: {
                            const d = UPower.displayDevice
                            if (!d || !d.ready) return ""
                            return Math.round((d.percentage ?? 0) * 100) + "%" + (d.state === 1 ? " ⚡" : "")
                        }
                        color: (UPower.displayDevice?.percentage ?? 1) < 0.15 ? "#D66056" : root.muted
                        font.pixelSize: 11
                        font.family: "monospace"
                    }

                    // network: one dot, colour tells the story
                    Row {
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 5
                        Rectangle {
                            width: 6
                            height: 6
                            radius: 3
                            anchors.verticalCenter: parent.verticalCenter
                            color: Networking.connectivity === NetworkConnectivity.Full ? "#7EAE68"
                                 : (Networking.connectivity === NetworkConnectivity.Limited
                                    || Networking.connectivity === NetworkConnectivity.Portal) ? root.amber
                                 : Networking.connectivity === NetworkConnectivity.None ? "#D66056"
                                 : root.faint
                        }
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: "net"
                            color: root.muted
                            font.pixelSize: 11
                        }
                    }
                }
            }

            // ---- clock -----------------------------------------------------
            Island {
                Layout.preferredWidth: clockColumn.implicitWidth + 30
                Layout.fillHeight: true

                Column {
                    id: clockColumn
                    anchors.centerIn: parent
                    spacing: 0

                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: Qt.formatDateTime(clock.date, "HH:mm")
                        color: root.text
                        font.pixelSize: 15
                        font.bold: true
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: clock.date.toLocaleString(Qt.locale("tr_TR"), "ddd d MMM").toLowerCase()
                        color: root.faint
                        font.pixelSize: 10
                    }

                    SystemClock {
                        id: clock
                        precision: SystemClock.Minutes
                    }
                }
            }

            // ---- power -----------------------------------------------------
            Island {
                Layout.preferredWidth: 46
                Layout.fillHeight: true
                color: powerArea.containsMouse ? root.bgSoft : root.bg

                Text {
                    anchors.centerIn: parent
                    text: "⏻"
                    color: powerArea.containsMouse ? root.amber : root.muted
                    font.pixelSize: 15
                }

                MouseArea {
                    id: powerArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: powerMenu.visible = !powerMenu.visible
                }
            }
        }
    }

    // IPC so a Hyprland keybind can open this without a second implementation of the menu
    IpcHandler {
        target: "powermenu"
        function toggle(): void { powerMenu.visible = !powerMenu.visible }
        function close(): void { powerMenu.visible = false }
    }

    // ---- power menu -------------------------------------------------------
    // A small window of our own instead of a wofi/rofi script: same corners, same edge.
    PanelWindow {
        id: powerMenu
        visible: false
        anchors.bottom: true
        anchors.right: true
        margins { right: 14; bottom: 74 }
        implicitWidth: 190
        implicitHeight: 196
        color: "transparent"
        exclusiveZone: -1
        exclusionMode: ExclusionMode.Ignore

        Rectangle {
            anchors.fill: parent
            radius: 14
            color: root.bg
            border.color: root.edge
            border.width: 1

            Column {
                anchors.fill: parent
                anchors.margins: 10
                spacing: 4

                Repeater {
                    model: [
                        { label: "Kilitle",    cmd: ["hyprlock"] },
                        { label: "Oturumu kapat", cmd: ["hyprctl", "dispatch", "exit"] },
                        { label: "Yeniden başlat", cmd: ["systemctl", "reboot"] },
                        { label: "Kapat",      cmd: ["systemctl", "poweroff"] }
                    ]

                    Rectangle {
                        required property var modelData
                        width: parent.width
                        height: 42
                        radius: 9
                        color: itemArea.containsMouse ? root.bgSoft : "transparent"

                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.left: parent.left
                            anchors.leftMargin: 12
                            text: modelData.label
                            color: modelData.label === "Kapat" && itemArea.containsMouse ? "#D66056" : root.text
                            font.pixelSize: 13
                        }

                        MouseArea {
                            id: itemArea
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                powerMenu.visible = false
                                if (modelData.cmd[0] === "systemctl") {
                                    Quickshell.execDetached(["systemctl", modelData.cmd[1]])
                                } else {
                                    Quickshell.execDetached(modelData.cmd)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

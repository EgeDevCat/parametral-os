// Parametral Shell — panel increment.
//
// Quickshell (QML) on Hyprland. Everything is a file the AI can rewrite, and the whole surface
// is one design language: three islands, graphite body, amber edge.
//
// Geometry note: the panel uses PanelWindow.margins (not manual anchors) — anchoring the
// content to the window edge pushed the islands below the screen edge on a 1280x800 panel.

import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Wayland
import Quickshell.Hyprland
import Quickshell.Services.SystemTray

ShellRoot {
    id: root

    readonly property color bg:     "#12171E"
    readonly property color text:   "#E9E4D8"
    readonly property color muted:  "#9AA4B2"
    readonly property color amber:  "#E0A93B"
    readonly property color edge:   Qt.rgba(0.878, 0.663, 0.231, 0.22)

    component Island: Rectangle {
        radius: 14
        color: root.bg
        border.color: root.edge
        border.width: 1
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

                Text {
                    anchors.centerIn: parent
                    text: "◉"
                    color: root.amber
                    font.pixelSize: 21
                }

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: Quickshell.execDetached(["/usr/local/bin/parametral-launcher"])
                }
            }

            // ---- workspaces -----------------------------------------------
            Island {
                Layout.preferredWidth: workspaceRow.implicitWidth + 22
                Layout.fillHeight: true

                Row {
                    id: workspaceRow
                    anchors.centerIn: parent
                    spacing: 5

                    Repeater {
                        model: Hyprland.workspaces

                        Rectangle {
                            required property var modelData
                            width: 28
                            height: 28
                            radius: 9
                            color: modelData.id === Hyprland.focusedWorkspace?.id
                                   ? root.amber : "transparent"

                            Text {
                                anchors.centerIn: parent
                                text: modelData.id
                                color: modelData.id === Hyprland.focusedWorkspace?.id
                                       ? "#1A150A" : root.muted
                                font.pixelSize: 12
                                font.bold: true
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: Hyprland.dispatch("workspace " + modelData.id)
                            }
                        }
                    }
                }
            }

            Item { Layout.fillWidth: true }

            // ---- clock ----------------------------------------------------
            Island {
                Layout.preferredWidth: clockText.implicitWidth + 40
                Layout.fillHeight: true

                Text {
                    id: clockText
                    anchors.centerIn: parent
                    color: root.text
                    font.pixelSize: 15
                    font.bold: true
                    text: Qt.formatDateTime(clock.date, "HH:mm")
                }

                SystemClock {
                    id: clock
                    precision: SystemClock.Minutes
                }
            }

            Item { Layout.fillWidth: true }

            // ---- tray -----------------------------------------------------
            Island {
                Layout.preferredWidth: Math.max(56, trayRow.implicitWidth + 24)
                Layout.fillHeight: true

                Row {
                    id: trayRow
                    anchors.centerIn: parent
                    spacing: 10

                    Repeater {
                        model: SystemTray.items

                        Image {
                            required property var modelData
                            width: 18
                            height: 18
                            source: modelData.icon
                            fillMode: Image.PreserveAspectFit
                        }
                    }
                }
            }
        }
    }
}

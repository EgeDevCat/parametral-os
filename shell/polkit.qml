// Parametral polkit agent — the dialog that asks a human for permission.
//
// Without this, `pkexec` in the Hyprland session has nobody to ask: the snapshot app's rollback
// and anything else that needs root fails with "no authentication agent found". KDE ships its
// own agent; our session needs ours.
//
// STATUS: experimental. The window and the agent registration exist — `agent.isRegistered`
// returns true — but a pkexec request in this VM still reports "No authentication agent
// found", so the end-to-end path is NOT verified. Do not autostart this until that is fixed;
// the honest fix is a wrapper that registers the agent for the caller's session properly.
//
// The flow object owns the protocol. We only show it: message, one password field, two answers.
// Nothing here decides anything — the password goes to polkit, and polkit's PAM stack judges it.

import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Wayland
import Quickshell.Io
import Quickshell.Services.Polkit

ShellRoot {
    id: root

    readonly property color bg:     "#12171E"
    readonly property color card:   "#1A2029"
    readonly property color text:   "#E9E4D8"
    readonly property color muted:  "#9AA4B2"
    readonly property color faint:  "#6B7280"
    readonly property color amber:  "#E0A93B"
    readonly property color danger: "#D66056"
    readonly property color edge:   Qt.rgba(0.878, 0.663, 0.231, 0.30)

    PolkitAgent {
        id: agent
        path: "/org/parametral/PolkitAgent"
    }

    readonly property var flow: agent.flow

    // diagnostics: "is the agent even registered, and does it have a request?" — the two
    // questions that decide whether pkexec can reach this window
    IpcHandler {
        target: "polkitstatus"
        function report(): string {
            return "registered=" + agent.isRegistered
                 + " active=" + agent.isActive
                 + " flow=" + (agent.flow ? "yes" : "no")
        }
    }
    property string password: ""

    Connections {
        target: agent
        function onFlowChanged() {
            if (agent.flow) {
                root.password = ""
                input.text = ""
                input.forceActiveFocus()
            }
        }
    }

    PanelWindow {
        id: window
        visible: root.flow !== null && root.flow !== undefined
        anchors {
            top: true
            bottom: true
            left: true
            right: true
        }
        color: "transparent"
        exclusiveZone: 0
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive

        Rectangle {
            anchors.fill: parent
            color: Qt.rgba(0.02, 0.03, 0.04, 0.62)
        }

        Rectangle {
            id: card
            anchors.centerIn: parent
            width: 420
            height: column.implicitHeight + 30
            radius: 16
            color: root.bg
            border.color: root.edge
            border.width: 1

            Column {
                id: column
                x: 15
                y: 15
                width: card.width - 30
                spacing: 10

                Row {
                    spacing: 10

                    Item {
                        width: 30
                        height: 30
                        anchors.verticalCenter: parent.verticalCenter

                        Canvas {
                            anchors.fill: parent
                            onPaint: {
                                const ctx = getContext("2d")
                                ctx.reset()
                                const c = width / 2, r = width * 0.42
                                ctx.strokeStyle = root.amber
                                ctx.lineWidth = 1.5
                                ctx.beginPath()
                                for (let i = 0; i < 12; i++) {
                                    const a = (Math.PI * 2 * i) / 12 - Math.PI / 2
                                    ctx.moveTo(c + Math.cos(a) * r * 0.78, c + Math.sin(a) * r * 0.78)
                                    ctx.lineTo(c + Math.cos(a) * r, c + Math.sin(a) * r)
                                }
                                ctx.stroke()
                                ctx.beginPath()
                                ctx.arc(c, c, r * 0.6, 0, Math.PI * 2)
                                ctx.stroke()
                            }
                        }
                    }

                    Column {
                        anchors.verticalCenter: parent.verticalCenter

                        Text {
                            text: "Yetki isteği"
                            color: root.text
                            font.pixelSize: 15
                            font.bold: true
                        }
                        Text {
                            text: "Parametral OS · polkit"
                            color: root.faint
                            font.pixelSize: 10
                        }
                    }
                }

                Text {
                    width: parent.width
                    text: root.flow ? root.flow.message : ""
                    color: root.muted
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                }

                Text {
                    width: parent.width
                    visible: root.flow !== null && root.flow.supplementaryMessage !== ""
                    text: root.flow ? root.flow.supplementaryMessage : ""
                    color: root.flow && root.flow.supplementaryIsError ? root.danger : root.muted
                    font.pixelSize: 11
                    wrapMode: Text.WordWrap
                }

                Rectangle {
                    width: parent.width
                    height: 42
                    radius: 11
                    color: root.card
                    border.color: input.activeFocus ? root.edge : "transparent"
                    border.width: 1

                    TextInput {
                        id: input
                        anchors.fill: parent
                        anchors.leftMargin: 12
                        anchors.rightMargin: 12
                        verticalAlignment: TextInput.AlignVCenter
                        color: root.text
                        font.pixelSize: 14
                        echoMode: TextInput.Password
                        focus: true
                        onTextChanged: root.password = text
                        // Enter must submit even when the toolkit eats `accepted`
                        Keys.onPressed: event => {
                            if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                                if (root.password !== "" && root.flow) root.flow.submit(root.password)
                                event.accepted = true
                            } else if (event.key === Qt.Key_Escape) {
                                if (root.flow) root.flow.cancelAuthenticationRequest()
                                event.accepted = true
                            }
                        }

                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            visible: input.text === ""
                            text: "şifre"
                            color: root.faint
                            font.pixelSize: 14
                        }
                    }
                }

                Row {
                    width: parent.width
                    spacing: 8
                    layoutDirection: Qt.RightToLeft

                    Rectangle {
                        width: 96
                        height: 34
                        radius: 9
                        color: okArea.containsMouse ? "#2A2010" : root.amber

                        Text {
                            anchors.centerIn: parent
                            text: "Onayla"
                            color: "#1A150A"
                            font.pixelSize: 13
                            font.bold: true
                        }

                        MouseArea {
                            id: okArea
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: if (root.password !== "" && root.flow) root.flow.submit(root.password)
                        }
                    }

                    Rectangle {
                        width: 96
                        height: 34
                        radius: 9
                        color: cancelArea.containsMouse ? root.card : "transparent"
                        border.color: Qt.rgba(0.60, 0.64, 0.70, 0.25)
                        border.width: 1

                        Text {
                            anchors.centerIn: parent
                            text: "İptal"
                            color: root.muted
                            font.pixelSize: 13
                        }

                        MouseArea {
                            id: cancelArea
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: if (root.flow) root.flow.cancelAuthenticationRequest()
                        }
                    }
                }
            }
        }
    }
}

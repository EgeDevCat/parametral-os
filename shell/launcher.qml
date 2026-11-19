// Parametral launcher — search + keyboard, our own surface.
//
// Opens on the launcher button or SUPER+Space. Lists desktop entries, filters as you type,
// Enter launches the selected one, Escape closes. Written for Quickshell 0.3.x.

import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import Quickshell.Wayland

ShellRoot {
    id: root

    readonly property color bg:    "#12171E"
    readonly property color card:  "#1A2029"
    readonly property color text:  "#E9E4D8"
    readonly property color muted: "#9AA4B2"
    readonly property color amber: "#E0A93B"

    property string query: ""
    property int selected: 0

    // all applications, read once per open
    property var entries: []

    Process {
        id: lister
        command: ["sh", "-c",
            "for f in /usr/share/applications/*.desktop /home/*/.local/share/applications/*.desktop; do " +
            "[ -f \"$f\" ] || continue; " +
            "n=$(sed -n 's/^Name=//p' \"$f\" | head -1); " +
            "e=$(sed -n 's/^Exec=//p' \"$f\" | head -1); " +
            "h=$(sed -n 's/^NoDisplay=true//p' \"$f\" | head -1); " +
            "[ -z \"$n\" ] && continue; [ -n \"$h\" ] && continue; " +
            "printf '%s\\t%s\\n' \"$n\" \"$e\"; done | sort -u"]
        running: true
        stdout: SplitParser {
            onRead: line => {
                const tab = line.indexOf("\t");
                if (tab <= 0) return;
                // `entries.push()` mutates in place and QML never re-evaluates `filtered`;
                // reassigning the array is what actually notifies the bindings.
                const next = root.entries.slice();
                next.push({ name: line.slice(0, tab), exec: line.slice(tab + 1) });
                root.entries = next;
            }
        }
    }

    readonly property var filtered: {
        const q = query.toLowerCase().trim();
        const seen = new Set();
        const out = [];
        for (const e of entries) {
            const key = e.name.toLowerCase();
            if (seen.has(key)) continue;          // same app in /usr/share and ~/.local/share
            if (q !== "" && !key.includes(q)) continue;
            seen.add(key);
            out.push(e);
            if (out.length === 8) break;
        }
        return out;
    }

    function launch(entry) {
        if (!entry) return;
        // strip field codes (%U %f ...) the way desktop files expect
        const cmd = entry.exec.replace(/%[a-zA-Z]/g, "").trim();
        Quickshell.execDetached(["sh", "-c", cmd]);
        Qt.quit();
    }

    // A full-screen layer with a scrim, and the card placed by arithmetic. Anchoring the
    // PanelWindow to the top edge alone kept the surface on the bottom edge in this build.
    PanelWindow {
        id: window
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
            color: Qt.rgba(0, 0, 0, 0.35)

            MouseArea {
                anchors.fill: parent
                onClicked: Qt.quit()
            }
        }

        Rectangle {
            id: card
            anchors.horizontalCenter: parent.horizontalCenter
            y: Math.round(parent.height * 0.16)
            width: Math.min(620, parent.width - 80)
            height: column.implicitHeight + 28
            radius: 18
            color: root.bg
            border.color: Qt.rgba(0.878, 0.663, 0.231, 0.35)
            border.width: 1

            ColumnLayout {
                id: column
                anchors {
                    left: parent.left
                    right: parent.right
                    top: parent.top
                    margins: 14
                }
                spacing: 10

                Rectangle {
                    Layout.fillWidth: true
                    height: 46
                    radius: 12
                    color: root.card

                    TextInput {
                        id: input
                        anchors.fill: parent
                        anchors.leftMargin: 14
                        anchors.rightMargin: 14
                        verticalAlignment: TextInput.AlignVCenter
                        color: root.text
                        font.pixelSize: 17
                        focus: true
                        selectByMouse: true
                        onTextChanged: {
                            root.query = text;
                            root.selected = 0;
                        }
                        Keys.onDownPressed: root.selected = Math.min(root.selected + 1, root.filtered.length - 1)
                        Keys.onUpPressed: root.selected = Math.max(root.selected - 1, 0)
                        Keys.onReturnPressed: root.launch(root.filtered[root.selected])
                        Keys.onEscapePressed: Qt.quit()

                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            visible: input.text === ""
                            text: "Uygulama ara…"
                            color: root.muted
                            font.pixelSize: 17
                        }
                    }
                }

                Text {
                    visible: root.filtered.length === 0
                    Layout.fillWidth: true
                    Layout.topMargin: 6
                    text: root.entries.length === 0 ? "Uygulama listesi yüklenemedi" : "Eşleşme yok"
                    color: root.muted
                    font.pixelSize: 14
                }

                Repeater {
                    model: root.filtered

                    Rectangle {
                        required property var modelData
                        required property int index
                        Layout.fillWidth: true
                        Layout.preferredHeight: 42
                        height: 42            // the layout prop alone was ignored for delegates
                        radius: 10
                        color: index === root.selected ? Qt.rgba(0.878, 0.663, 0.231, 0.16) : "transparent"

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 12
                            anchors.rightMargin: 12
                            spacing: 10

                            Rectangle {
                                width: 6
                                height: 6
                                radius: 3
                                color: index === root.selected ? root.amber : root.muted
                            }

                            Text {
                                Layout.fillWidth: true
                                text: modelData.name
                                color: index === root.selected ? root.text : root.muted
                                font.pixelSize: 15
                                elide: Text.ElideRight
                            }
                        }

                        MouseArea {
                            anchors.fill: parent
                            hoverEnabled: true
                            onEntered: root.selected = index
                            onClicked: root.launch(modelData)
                        }
                    }
                }
            }
        }
    }
}

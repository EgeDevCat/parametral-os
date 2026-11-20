// Parametral launcher — search + keyboard, our own surface.
//
// Opens on the launcher button or SUPER+Space. Lists desktop entries, filters as you type,
// Enter launches the selected one, Escape closes. Written for Quickshell 0.3.x.
//
// Layout note: the list is a fixed-height Flickable with an explicit row height. Letting a
// ColumnLayout size itself from delegates made the card grow past the bottom of the screen
// and spaced rows ~100px apart.

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
    readonly property color faint: "#6B7280"
    readonly property color amber: "#E0A93B"
    readonly property color edge:  Qt.rgba(0.878, 0.663, 0.231, 0.28)

    readonly property int rowHeight: 44
    readonly property int maxRows: 8

    property string query: ""
    property int selected: 0
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
            if (out.length === maxRows) break;
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
            color: Qt.rgba(0.02, 0.03, 0.04, 0.55)

            MouseArea {
                anchors.fill: parent
                onClicked: Qt.quit()
            }
        }

        Rectangle {
            id: card
            anchors.horizontalCenter: parent.horizontalCenter
            y: Math.round(parent.height * 0.18)
            width: Math.min(640, parent.width - 80)
            height: column.implicitHeight + 24
            radius: 18
            color: root.bg
            border.color: root.edge
            border.width: 1

            Column {
                id: column
                width: card.width - 24
                x: 12
                y: 12
                spacing: 8

                // ---- search field -------------------------------------
                Rectangle {
                    width: parent.width
                    height: 48
                    radius: 12
                    color: root.card

                    Item {
                        id: mark
                        width: 26
                        height: 26
                        anchors.left: parent.left
                        anchors.leftMargin: 14
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

                    TextInput {
                        id: input
                        anchors.left: mark.right
                        anchors.leftMargin: 12
                        anchors.right: parent.right
                        anchors.rightMargin: 14
                        anchors.verticalCenter: parent.verticalCenter
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
                            color: root.faint
                            font.pixelSize: 17
                        }
                    }
                }

                // ---- results ------------------------------------------
                Text {
                    visible: root.filtered.length === 0
                    width: parent.width
                    topPadding: 8
                    bottomPadding: 8
                    text: root.entries.length === 0 ? "Uygulama listesi yüklenemedi" : "Eşleşme yok"
                    color: root.muted
                    font.pixelSize: 13
                    horizontalAlignment: Text.AlignHCenter
                }

                Item {
                    visible: root.filtered.length > 0
                    width: parent.width
                    height: Math.min(root.filtered.length * root.rowHeight,
                                     root.maxRows * root.rowHeight)

                    ListView {
                        id: list
                        anchors.fill: parent
                        clip: true
                        model: root.filtered
                        currentIndex: root.selected
                        interactive: false

                        delegate: Rectangle {
                            required property var modelData
                            required property int index
                            width: list.width
                            height: root.rowHeight
                            radius: 10
                            color: index === root.selected ? Qt.rgba(0.878, 0.663, 0.231, 0.14)
                                 : rowArea.containsMouse ? root.card : "transparent"

                            Rectangle {
                                width: 5
                                height: 5
                                radius: 3
                                anchors.left: parent.left
                                anchors.leftMargin: 13
                                anchors.verticalCenter: parent.verticalCenter
                                color: index === root.selected ? root.amber : root.faint
                            }

                            Text {
                                anchors.left: parent.left
                                anchors.leftMargin: 28
                                anchors.right: parent.right
                                anchors.rightMargin: 12
                                anchors.verticalCenter: parent.verticalCenter
                                text: modelData.name
                                color: index === root.selected ? root.text : root.muted
                                font.pixelSize: 14
                                elide: Text.ElideRight
                            }

                            MouseArea {
                                id: rowArea
                                anchors.fill: parent
                                hoverEnabled: true
                                onEntered: root.selected = index
                                onClicked: root.launch(modelData)
                            }
                        }
                    }
                }

                // ---- footer hint --------------------------------------
                Text {
                    width: parent.width
                    topPadding: 2
                    text: "↵ aç    ↑↓ seç    esc kapat"
                    color: root.faint
                    font.pixelSize: 10
                    horizontalAlignment: Text.AlignHCenter
                }
            }
        }
    }
}

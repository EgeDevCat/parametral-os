// Parametral Cetvel — the one signature, as a Plasma applet.
//
// 5 workspaces, each a tick on the panel's ruler: passive 6×2, active 14×2 amber.
// Colours come from the active KDE colour scheme (Parametral / ParametralLight), so dark and
// light both stay on the same tokens. No stock workspaces widget: its dots/pills break the
// signature.

import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.private.pager 2.0

PlasmoidItem {
    id: root

    readonly property int tickGap: 8
    readonly property int activeWidth: 14
    readonly property int idleWidth: 6
    readonly property int tickHeight: 2

    Layout.minimumWidth: row.implicitWidth + 20
    Layout.minimumHeight: 40
    Layout.preferredWidth: row.implicitWidth + 20
    implicitWidth: row.implicitWidth + 20
    implicitHeight: 40

    Plasmoid.preferredRepresentation: Plasmoid.fullRepresentation
    Plasmoid.status: PlasmaCore.Types.ActiveStatus
    Plasmoid.backgroundHints: PlasmaCore.Types.NoBackground

    PagerModel {
        id: pagerModel
        enabled: root.visible
        pagerType: PagerModel.VirtualDesktops
    }

    fullRepresentation: Item {
        implicitWidth: root.implicitWidth
        implicitHeight: root.implicitHeight

        Row {
            id: row
            anchors.horizontalCenter: parent.horizontalCenter
            // sit on the ruler line at the bottom edge of the 40 px plate
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 10
            spacing: root.tickGap

            Repeater {
                model: Math.max(1, pagerModel.count)

                Rectangle {
                    required property int index
                    readonly property bool active: index === pagerModel.currentPage

                    width: active ? root.activeWidth : root.idleWidth
                    height: root.tickHeight
                    radius: 1
                    color: active ? PlasmaCore.Theme.highlightColor
                                  : PlasmaCore.Theme.disabledTextColor

                    MouseArea {
                        anchors.fill: parent
                        anchors.margins: -4
                        cursorShape: Qt.PointingHandCursor
                        onClicked: pagerModel.changePage(index)
                    }
                }
            }
        }
    }
}

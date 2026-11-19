// Parametral SDDM theme — soft cream, the mark, one card, nothing else.
// Resolution-independent: every size derives from `u`, a scale unit computed from the
// actual screen, so the layout is identical on a 1280x800 VM and a 4K panel.
// Dependency-light on purpose: QtQuick Controls 2 only, no third-party imports, so a
// theme failure can never be the reason a machine has no login screen.
import QtQuick 2.15
import QtQuick.Controls 2.15
import SddmComponents 2.0

Rectangle {
    id: root
    // SDDM sizes the root item to the screen. Derive one scale unit from the design size.
    property real u: Math.min(width / 1920, height / 1080)
    color: "#f7f2e8"

    Image {
        anchors.fill: parent
        source: "background.png"
        fillMode: Image.PreserveAspectCrop
    }

    Column {
        anchors.centerIn: parent
        spacing: 18 * root.u

        Image {
            id: mark
            source: "logo-large.png"
            width: 150 * root.u
            height: 150 * root.u
            anchors.horizontalCenter: parent.horizontalCenter
            fillMode: Image.PreserveAspectFit
            smooth: true
        }

        Text {
            id: wordmark
            text: "Parametral"
            anchors.horizontalCenter: parent.horizontalCenter
            color: "#1a1a1e"
            font.family: "DejaVu Sans"
            font.weight: Font.Light
            font.pixelSize: 54 * root.u
            font.letterSpacing: 1.2
        }

        Rectangle {
            id: card
            width: 620 * root.u
            height: 348 * root.u
            radius: 26 * root.u
            color: "#fffefb"
            border.color: "#e4dbca"
            border.width: 1
            anchors.horizontalCenter: parent.horizontalCenter

            Column {
                anchors.centerIn: parent
                spacing: 14 * root.u

                Text {
                    text: "Hoş geldiniz"
                    anchors.horizontalCenter: parent.horizontalCenter
                    color: "#5c5852"
                    font.family: "DejaVu Sans"
                    font.weight: Font.Light
                    font.pixelSize: 25 * root.u
                }

                TextField {
                    id: userEntry
                    width: 520 * root.u
                    height: 54 * root.u
                    placeholderText: "kullanıcı"
                    text: userModel.lastUser
                    font.pixelSize: 19 * root.u
                    color: "#1a1a1e"
                    selectByMouse: true
                    background: Rectangle {
                        radius: 13 * root.u
                        color: "#ffffff"
                        border.color: userEntry.activeFocus ? "#e0a93b" : "#e6ddcc"
                        border.width: userEntry.activeFocus ? 2 : 1
                    }
                }

                TextField {
                    id: passwordEntry
                    width: 520 * root.u
                    height: 54 * root.u
                    placeholderText: "parola"
                    echoMode: TextInput.Password
                    font.pixelSize: 19 * root.u
                    color: "#1a1a1e"
                    selectByMouse: true
                    onAccepted: sddm.login(userEntry.text, passwordEntry.text, sessionModel.lastIndex)
                    background: Rectangle {
                        radius: 13 * root.u
                        color: "#ffffff"
                        border.color: passwordEntry.activeFocus ? "#e0a93b" : "#e6ddcc"
                        border.width: passwordEntry.activeFocus ? 2 : 1
                    }
                }

                Rectangle {
                    id: loginButton
                    width: 520 * root.u
                    height: 56 * root.u
                    radius: 13 * root.u
                    color: buttonArea.pressed ? "#c9942f" : "#e0a93b"

                    Text {
                        anchors.centerIn: parent
                        text: "Giriş yap"
                        color: "#231c10"
                        font.pixelSize: 19 * root.u
                    }

                    MouseArea {
                        id: buttonArea
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: sddm.login(userEntry.text, passwordEntry.text, sessionModel.lastIndex)
                    }
                }
            }
        }
    }

    Text {
        id: message
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 64 * root.u
        color: "#a2564a"
        font.pixelSize: 17 * root.u
        text: ""
        visible: text.length > 0
    }

    Text {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 28 * root.u
        text: "Parametral OS"
        color: "#8a8378"
        font.family: "DejaVu Sans"
        font.weight: Font.Light
        font.pixelSize: 18 * root.u
    }

    Connections {
        target: sddm
        function onLoginFailed() {
            passwordEntry.text = ""
            message.text = "Parola hatalı"
            passwordEntry.forceActiveFocus()
        }
        function onLoginSucceeded() {
            message.text = ""
        }
    }

    Component.onCompleted: {
        if (userEntry.text.length > 0) {
            passwordEntry.forceActiveFocus()
        } else {
            userEntry.forceActiveFocus()
        }
    }
}

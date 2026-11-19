// Parametral SDDM theme — soft cream, the mark, one card, nothing else.
// Kept dependency-light on purpose: QtQuick Controls 2 only, no third-party imports,
// so a theme failure can never be the reason a machine has no login screen.
import QtQuick 2.15
import QtQuick.Controls 2.15
import SddmComponents 2.0

Rectangle {
    id: root
    width: 1920
    height: 1080
    color: "#f7f2e8"

    Image {
        anchors.fill: parent
        source: "background.png"
        fillMode: Image.PreserveAspectCrop
    }

    Image {
        id: mark
        source: "logo-large.png"
        width: 168
        height: 168
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: parent.top
        anchors.topMargin: 148
        fillMode: Image.PreserveAspectFit
        smooth: true
    }

    Text {
        id: wordmark
        text: "Parametral"
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: mark.bottom
        anchors.topMargin: 20
        color: "#1a1a1e"
        font.family: "DejaVu Sans"
        font.weight: Font.Light
        font.pixelSize: 58
        font.letterSpacing: 1.2
    }

    Rectangle {
        id: card
        width: 640
        height: 352
        radius: 28
        color: "#fffefb"
        border.color: "#e4dbca"
        border.width: 1
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: wordmark.bottom
        anchors.topMargin: 44

        Column {
            anchors.centerIn: parent
            spacing: 16

            Text {
                text: "Hoş geldiniz"
                anchors.horizontalCenter: parent.horizontalCenter
                color: "#5c5852"
                font.family: "DejaVu Sans"
                font.weight: Font.Light
                font.pixelSize: 26
            }

            TextField {
                id: userEntry
                width: 520
                height: 56
                placeholderText: "kullanıcı"
                text: userModel.lastUser
                font.pixelSize: 20
                color: "#1a1a1e"
                selectByMouse: true
                background: Rectangle {
                    radius: 14
                    color: "#ffffff"
                    border.color: userEntry.activeFocus ? "#e0a93b" : "#e6ddcc"
                    border.width: userEntry.activeFocus ? 2 : 1
                }
            }

            TextField {
                id: passwordEntry
                width: 520
                height: 56
                placeholderText: "parola"
                echoMode: TextInput.Password
                font.pixelSize: 20
                color: "#1a1a1e"
                selectByMouse: true
                onAccepted: sddm.login(userEntry.text, passwordEntry.text, sessionModel.lastIndex)
                background: Rectangle {
                    radius: 14
                    color: "#ffffff"
                    border.color: passwordEntry.activeFocus ? "#e0a93b" : "#e6ddcc"
                    border.width: passwordEntry.activeFocus ? 2 : 1
                }
            }

            Button {
                id: loginButton
                width: 520
                height: 58
                text: qsTr("Giriş yap")
                font.pixelSize: 20
                onClicked: sddm.login(userEntry.text, passwordEntry.text, sessionModel.lastIndex)
                background: Rectangle {
                    radius: 14
                    color: loginButton.down ? "#c9942f" : "#e0a93b"
                }
                contentItem: Text {
                    text: loginButton.text
                    color: "#231c10"
                    font.pixelSize: 20
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }
        }
    }

    Text {
        id: message
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: card.bottom
        anchors.topMargin: 18
        color: "#a2564a"
        font.pixelSize: 18
        text: ""
        visible: text.length > 0
    }

    Text {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 54
        text: "Parametral OS"
        color: "#8a8378"
        font.family: "DejaVu Sans"
        font.weight: Font.Light
        font.pixelSize: 20
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

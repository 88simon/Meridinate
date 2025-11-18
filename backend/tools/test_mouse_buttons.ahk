#Requires AutoHotkey v2.0
#SingleInstance Force

; Test script to identify which mouse buttons are being pressed
; This will show a tooltip with the button name when you press any mouse button

A_IconTip := "Mouse Button Tester - Press your side buttons!"

; Test all possible side buttons
XButton1:: {
    ToolTip "XButton1 (Back) was pressed!"
    SetTimer () => ToolTip(), -2000
}

XButton2:: {
    ToolTip "XButton2 (Forward) was pressed!"
    SetTimer () => ToolTip(), -2000
}

; Some mice report side buttons differently
MButton:: {
    ToolTip "Middle Button was pressed!"
    SetTimer () => ToolTip(), -2000
}

; Test if it's being reported as a regular button
~LButton:: {
    ToolTip "Left Button was pressed!"
    SetTimer () => ToolTip(), -1000
}

~RButton:: {
    ToolTip "Right Button was pressed!"
    SetTimer () => ToolTip(), -1000
}

; Exit with Escape
Esc::ExitApp
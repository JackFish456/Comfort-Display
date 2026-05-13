Option Explicit

Dim shell
Dim fso
Dim appDir
Dim launcher
Dim logPath
Dim pythonw
Dim pyw
Dim command

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

appDir = fso.GetParentFolderName(WScript.ScriptFullName)
launcher = fso.BuildPath(appDir, "run_jack_display.pyw")
logPath = fso.BuildPath(appDir, "jack_display_launch.log")
pythonw = fso.BuildPath(shell.ExpandEnvironmentStrings("%LOCALAPPDATA%"), "Programs\Python\Python312\pythonw.exe")
pyw = fso.BuildPath(shell.ExpandEnvironmentStrings("%SystemRoot%"), "pyw.exe")

Sub Log(message)
    Dim file
    Set file = fso.OpenTextFile(logPath, 8, True)
    file.WriteLine Now & " " & message
    file.Close
End Sub

If Not fso.FileExists(launcher) Then
    Log "Missing launcher: " & launcher
    WScript.Quit 1
End If

If fso.FileExists(pythonw) Then
    command = """" & pythonw & """ """ & launcher & """"
ElseIf fso.FileExists(pyw) Then
    command = """" & pyw & """ -3.12 """ & launcher & """"
Else
    command = "pyw.exe -3.12 """ & launcher & """"
End If

shell.CurrentDirectory = appDir
Log "Launching: " & command
shell.Run command, 1, False

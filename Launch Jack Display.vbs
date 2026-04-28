Option Explicit

Dim shell
Dim fso
Dim appDir
Dim launcher
Dim pythonw
Dim command

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

appDir = fso.GetParentFolderName(WScript.ScriptFullName)
launcher = fso.BuildPath(appDir, "run_jack_display.pyw")
pythonw = fso.BuildPath(shell.ExpandEnvironmentStrings("%LOCALAPPDATA%"), "Programs\Python\Python312\pythonw.exe")

If fso.FileExists(pythonw) Then
    command = """" & pythonw & """ """ & launcher & """"
Else
    command = "pyw.exe -3 """ & launcher & """"
End If

shell.CurrentDirectory = appDir
shell.Run command, 0, False

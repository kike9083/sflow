Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "G:\Documents\app\sflow"
WshShell.Run "G:\Documents\app\sflow\.venv\Scripts\pythonw.exe main.py", 0, False

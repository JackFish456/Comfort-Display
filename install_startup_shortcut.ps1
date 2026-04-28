param(
    [string]$ShortcutName = "Jack Display Comfort Workspace",
    [switch]$NoDesktopShortcut
)

$ErrorActionPreference = "Stop"

$appDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$launcher = Join-Path $appDir "Launch Jack Display.vbs"
$iconPath = Join-Path $appDir "jack_display_pixel_j.ico"

if (-not (Test-Path -LiteralPath $launcher)) {
    throw "Launcher not found: $launcher"
}

function New-PixelJIcon {
    param([string]$Path)

    Add-Type -AssemblyName System.Drawing

    $size = 64
    $bitmap = New-Object System.Drawing.Bitmap $size, $size
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::NearestNeighbor
    $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::None

    $bg = [System.Drawing.Brushes]::Purple
    $border = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(247, 201, 72))
    $mark = [System.Drawing.Brushes]::White

    function Fill-CellRect {
        param(
            [System.Drawing.Brush]$Brush,
            [int]$X,
            [int]$Y,
            [int]$Width,
            [int]$Height
        )

        $scale = $size / 16
        $graphics.FillRectangle(
            $Brush,
            [int]($X * $scale),
            [int]($Y * $scale),
            [int]($Width * $scale),
            [int]($Height * $scale)
        )
    }

    Fill-CellRect $bg 0 0 16 16
    Fill-CellRect $border 0 0 16 2
    Fill-CellRect $border 0 14 16 2
    Fill-CellRect $border 0 0 2 16
    Fill-CellRect $border 14 0 2 16
    Fill-CellRect $mark 5 4 7 2
    Fill-CellRect $mark 8 4 2 7
    Fill-CellRect $mark 4 9 2 3
    Fill-CellRect $mark 5 11 5 2

    $iconHandle = $bitmap.GetHicon()
    try {
        $icon = [System.Drawing.Icon]::FromHandle($iconHandle)
        $stream = [System.IO.File]::Create($Path)
        try {
            $icon.Save($stream)
        } finally {
            $stream.Dispose()
            $icon.Dispose()
        }
    } finally {
        $graphics.Dispose()
        $bitmap.Dispose()
    }
}

function New-JackDisplayShortcut {
    param(
        [string]$Path,
        [string]$Description
    )

    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($Path)
    $shortcut.TargetPath = "wscript.exe"
    $shortcut.Arguments = "`"$launcher`""
    $shortcut.WorkingDirectory = $appDir
    $shortcut.Description = $Description
    $shortcut.IconLocation = $iconPath
    $shortcut.Save()
}

New-PixelJIcon -Path $iconPath

$startupDir = [Environment]::GetFolderPath("Startup")
$startupShortcutPath = Join-Path $startupDir "$ShortcutName.lnk"
New-JackDisplayShortcut -Path $startupShortcutPath -Description "Launch Jack Display Comfort Workspace at sign-in"

Write-Host "Installed startup shortcut:"
Write-Host $startupShortcutPath

if (-not $NoDesktopShortcut) {
    $desktopDir = [Environment]::GetFolderPath("Desktop")
    $desktopShortcutPath = Join-Path $desktopDir "$ShortcutName.lnk"
    New-JackDisplayShortcut -Path $desktopShortcutPath -Description "Launch Jack Display Comfort Workspace"

    Write-Host "Installed desktop shortcut:"
    Write-Host $desktopShortcutPath
}

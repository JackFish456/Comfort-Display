param(
    [string]$ShortcutName = "Jack Display Comfort Workspace"
)

$ErrorActionPreference = "Stop"

$shortcutPaths = @(
    (Join-Path ([Environment]::GetFolderPath("Startup")) "$ShortcutName.lnk"),
    (Join-Path ([Environment]::GetFolderPath("Desktop")) "$ShortcutName.lnk")
)

foreach ($shortcutPath in $shortcutPaths) {
    if (Test-Path -LiteralPath $shortcutPath) {
        Remove-Item -LiteralPath $shortcutPath -Force
        Write-Host "Removed shortcut:"
        Write-Host $shortcutPath
    } else {
        Write-Host "No shortcut found:"
        Write-Host $shortcutPath
    }
}

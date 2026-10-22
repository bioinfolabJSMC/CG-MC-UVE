param([string[]]$Names)
$ErrorActionPreference = 'Stop'
$packageTask = Split-Path -Parent $PSScriptRoot
$documentsTask = if ($Names) { $Names | ForEach-Object { Get-Item -LiteralPath (Join-Path $packageTask $_) } } else { Get-ChildItem -LiteralPath $packageTask -Filter '*.docx' }
$wordTask = New-Object -ComObject Word.Application
$wordTask.Visible = $false
$wordTask.DisplayAlerts = 0
try {
  foreach ($sourceTask in $documentsTask) {
    $documentTask = $null
    try {
      $documentTask = $wordTask.Documents.Open($sourceTask.FullName, $false, $true)
      $documentTask.Repaginate()
      $destinationTask = [System.IO.Path]::ChangeExtension($sourceTask.FullName, '.pdf')
      $documentTask.ExportAsFixedFormat($destinationTask, 17)
      Write-Output $destinationTask
    } finally {
      if ($null -ne $documentTask) { $documentTask.Close(0); [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($documentTask) }
    }
  }
} finally {
  $wordTask.Quit()
  [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($wordTask)
}

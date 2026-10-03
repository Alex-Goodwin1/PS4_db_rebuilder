# builds dist\fix_db.zip and the SHA256SUMS files of this repository
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem

$root = $PSScriptRoot
$dist = Join-Path $root 'dist'
if (-not (Test-Path $dist)) { New-Item -ItemType Directory $dist | Out-Null }

$archives = [ordered]@{
	'fix_db.zip' = @(
		'fix_db.exe',
		'run_check.bat',
		'run_apply.bat',
		'README.md',
		'LICENSE'
	)
}

foreach ($name in $archives.Keys) {
	$zip = Join-Path $dist $name
	$missing = @()
	foreach ($item in $archives[$name]) {
		if (-not (Test-Path (Join-Path $root $item))) { $missing += $item }
	}
	if ($missing.Count -gt 0) {
		throw "cannot build $name, these files are missing: $($missing -join ', ')"
	}
	if (Test-Path $zip) { Remove-Item $zip -Force }
	$archive = [System.IO.Compression.ZipFile]::Open($zip, 'Create')
	try {
		foreach ($item in $archives[$name]) {
			$full = Join-Path $root $item
			[void][System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
				$archive, $full, (Split-Path $full -Leaf))
		}
	} finally {
		$archive.Dispose()
	}
	Write-Host ('{0}  {1:N0} B' -f $name, (Get-Item $zip).Length)
}

$sums = @()
foreach ($file in (Get-ChildItem $dist -File -Filter *.zip | Sort-Object Name)) {
	$sums += '{0}  {1}' -f (Get-FileHash $file.FullName -Algorithm SHA256).Hash.ToLower(), $file.Name
}
$sums | Set-Content (Join-Path $dist 'SHA256SUMS.txt') -Encoding ASCII
Write-Host 'dist\SHA256SUMS.txt written'

$sums = @()
foreach ($item in @('fix_db.exe')) {
	$full = Join-Path $root $item
	if (-not (Test-Path $full)) { continue }
	$sums += '{0}  {1}' -f (Get-FileHash $full -Algorithm SHA256).Hash.ToLower(), $item
}
$sums | Set-Content (Join-Path $root 'SHA256SUMS.txt') -Encoding ASCII
Write-Host 'SHA256SUMS.txt written'
Get-Content (Join-Path $root 'SHA256SUMS.txt')

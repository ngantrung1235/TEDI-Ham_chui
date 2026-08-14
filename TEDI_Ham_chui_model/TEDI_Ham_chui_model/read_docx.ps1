Add-Type -AssemblyName System.IO.Compression.FileSystem
$docXPath = "C:\git\TEDI-Ham_chui\TEDI_Ham_chui_model\TEDI_Ham_chui_model\New Microsoft Word Document (3).docx"
$tempPath = "C:\git\TEDI-Ham_chui\TEDI_Ham_chui_model\TEDI_Ham_chui_model\temp_docx"
if (Test-Path $tempPath) { Remove-Item -Recurse -Force $tempPath }
[System.IO.Compression.ZipFile]::ExtractToDirectory($docXPath, $tempPath)
[xml]$doc = Get-Content "$tempPath\word\document.xml" -Raw
$ns = new-object System.Xml.XmlNamespaceManager $doc.NameTable
$ns.AddNamespace("w", "http://schemas.openxmlformats.org/wordprocessingml/2006/main")
$nodes = $doc.SelectNodes("//w:t", $ns)
$text = $nodes | ForEach-Object { $_.InnerText }
$text -join ""
Remove-Item -Recurse -Force $tempPath

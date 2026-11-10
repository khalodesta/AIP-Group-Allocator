# Exercises the built, frozen backend through the standalone frontend proxy.
# All identities are fictional; this script is only used for release validation.
param([string]$BaseUri = "http://127.0.0.1:3000")
$ErrorActionPreference = "Stop"
$People = @(0..5 | ForEach-Object {
  @{ id="P$_"; name="Fictional Hire $_"; attributes=@{
    Gender=$(if ($_ -lt 4) { "Male" } else { "Female" })
    University=$(if ($_ % 2) { "GUC" } else { "Cairo University" })
    "University Category"=$(if ($_ % 2) { "private" } else { "public" })
    "L3 Offering"=@("Cyber", "Customer", "Engineering")[$_ % 3]
  }}
})
$Faculty = @(0..2 | ForEach-Object {
  @{ id="F$_"; name="Fictional Faculty $_"; offering=@("Cyber", "Customer", "Engineering")[$_] }
})
$Support = @(0..3 | ForEach-Object {
  @{ id="S$_"; name="Fictional Support $_"; gender=$(if ($_ % 2) { "Female" } else { "Male" })
    category=$(if ($_ -lt 2) { "Support Lead" } else { "Analyst Support" }) }
})
$Payload = @{
  participants=$People; faculty_members=$Faculty; support_members=$Support
  configuration=@{
    activities=@(
      @{id="main";name="Main Groups";mode="max_size";value=3},
      @{id="quiz";name="Quiz Night";mode="max_size";value=3},
      @{id="team";name="Team Building";mode="max_size";value=3}
    )
    time_limit_seconds=2
    reflection_settings=@{enabled=$true;start_time="11:15";prayer_deadline="11:40";resume_time="13:00";
      session_duration_minutes=20;selected_participant_ids=@($People | Where-Object { $_.attributes.Gender -eq "Male" } | ForEach-Object { $_.id })}
  }
}
$Result = Invoke-RestMethod -Method Post -Uri "$BaseUri/api/optimize" -ContentType "application/json" -Body ($Payload | ConvertTo-Json -Depth 16) -TimeoutSec 90
if ($Result.allocation.activities.Count -ne 6) { throw "Expected all six Week 2 allocations" }
$Payload.allocation = $Result.allocation
$Body = $Payload | ConvertTo-Json -Depth 16
$Validation = Invoke-RestMethod -Method Post -Uri "$BaseUri/api/allocations/validate" -ContentType "application/json" -Body $Body -TimeoutSec 15
if (-not $Validation.valid) { throw "Bundled allocation validation failed: $($Validation.errors)" }
$Bus = $Result.allocation.activities | Where-Object { $_.activity_id -eq "bus" }
foreach ($Group in $Bus.groups) {
  if (-not (@($Group.participant_ids | Where-Object { $_ -in @("S0","S1") }).Count)) {
    throw "A bundled BUS Team is missing its Support Lead"
  }
}
$Hotel = $Result.allocation.activities | Where-Object { $_.activity_id -eq "hotel" }
$Occupants = @($Hotel.groups | ForEach-Object { $_.participant_ids })
if ($Occupants.Count -ne 13 -or @($Occupants | Sort-Object -Unique).Count -ne 13) { throw "Bundled hotel manifest must include every person exactly once" }
if ($Hotel.room_summary.total_rooms -ne $Hotel.groups.Count) { throw "Bundled hotel room totals disagree" }
$Sessions = @($Result.allocation.activities | Where-Object { $_.activity_id -eq "reflection" } | ForEach-Object { $_.sessions })
if ($Sessions.Count -ne 6 -or -not @($Sessions | Where-Object { -not $_.before_prayer }).Count) { throw "Bundled appointments did not continue after prayer" }
foreach ($Endpoint in @("pdf", "hotel-pdf", "editable")) {
  $Artifact = Join-Path $env:RUNNER_TEMP "AIP-fictional-smoke-$Endpoint.bin"
  Invoke-WebRequest -UseBasicParsing -Method Post -Uri "$BaseUri/api/export/$Endpoint" -ContentType "application/json" -Body $Body -OutFile $Artifact -TimeoutSec 30
  if ((Get-Item $Artifact).Length -lt 1000) { throw "Bundled $Endpoint export is empty" }
}
$Workbook = Join-Path $env:RUNNER_TEMP "AIP-fictional-smoke-editable.bin"
$Boundary = "AIP-" + [guid]::NewGuid().ToString("N")
$Header = [Text.Encoding]::UTF8.GetBytes("--$Boundary`r`nContent-Disposition: form-data; name=`"file`"; filename=`"fictional-master.xlsx`"`r`nContent-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`r`n`r`n")
$Footer = [Text.Encoding]::UTF8.GetBytes("`r`n--$Boundary--`r`n")
$Stream = New-Object IO.MemoryStream
$Stream.Write($Header, 0, $Header.Length)
$Bytes = [IO.File]::ReadAllBytes($Workbook)
$Stream.Write($Bytes, 0, $Bytes.Length)
$Stream.Write($Footer, 0, $Footer.Length)
$Multipart = $Stream.ToArray()
$Stream.Dispose()
$Imported = Invoke-RestMethod -Method Post -Uri "$BaseUri/api/upload" -ContentType "multipart/form-data; boundary=$Boundary" -Body $Multipart -TimeoutSec 30
if ($Imported.participants.Count -ne 6) { throw "Bundled Excel participant upload failed" }
$ImportedSupport = Invoke-RestMethod -Method Post -Uri "$BaseUri/api/upload/support" -ContentType "multipart/form-data; boundary=$Boundary" -Body $Multipart -TimeoutSec 30
if ($ImportedSupport.support_members.Count -ne 4) { throw "Bundled Excel support upload failed" }
if (@($Imported.participants | Where-Object { $_.attributes.'University Category' -notin @('public', 'private') }).Count) { throw "Imported university categories were not Public/Private" }
$Payload.participants = $Imported.participants
$Payload.Remove('allocation')
$Regenerated = Invoke-RestMethod -Method Post -Uri "$BaseUri/api/optimize" -ContentType "application/json" -Body ($Payload | ConvertTo-Json -Depth 16) -TimeoutSec 90
if ($Regenerated.allocation.activities.Count -ne 6) { throw "Generating six allocations from the uploaded workbook failed" }
Write-Host "Fictional Excel uploads, six allocations, prayer continuation, hotel manifest and PDF/Excel exports passed."

# Real optimizer request through the packaged Next.js proxy, exceeding the old 30s limit.
param([string]$BaseUri = "http://127.0.0.1:3000", [string]$DiagnosticDirectory = $env:RUNNER_TEMP)
$ErrorActionPreference = "Stop"
$Payload = Get-Content (Join-Path $PSScriptRoot 'fixtures\allocation27.json') -Raw | ConvertFrom-Json

function Assert-SixActivities($Result, $Request) {
  $Expected = @($Request.participants | ForEach-Object { $_.id })
  if ($Result.allocation.status -notin @('OPTIMAL','FEASIBLE')) { throw "27-person run must return a real CP-SAT solution, not fallback" }
  $Activities = @($Result.allocation.activities)
  if ($Activities.Count -ne 6 -or (@($Activities.activity_id | Sort-Object) -join ',') -ne 'bus,hotel,main,quiz,reflection,team') { throw "27-person run did not return all six activities" }
  foreach ($Activity in $Activities) {
    $Assigned = @($Activity.groups | ForEach-Object { $_.participant_ids })
    if (@($Assigned | Sort-Object -Unique).Count -ne $Assigned.Count) { throw "$($Activity.activity_id): duplicate assignments" }
    if (@($Expected | Where-Object { $_ -notin $Assigned }).Count) { throw "$($Activity.activity_id): missing new hires" }
  }
  $Validation = @{participants=$Request.participants;configuration=$Request.configuration;faculty_members=$Request.faculty_members;support_members=$Request.support_members;allocation=$Result.allocation} | ConvertTo-Json -Depth 24
  $Checked = Invoke-RestMethod -Method Post -Uri "$BaseUri/api/allocations/validate" -ContentType 'application/json' -Body $Validation -TimeoutSec 20
  if (-not $Checked.valid) { throw "27-person allocation validation failed: $($Checked.errors -join '; ')" }
  $Bus = $Activities | Where-Object { $_.activity_id -eq 'bus' }
  $Leads = @($Request.support_members | Where-Object { $_.category -eq 'Support Lead' } | ForEach-Object { $_.id })
  foreach ($Group in $Bus.groups) {
    if (-not @($Group.participant_ids | Where-Object { $_ -in $Leads }).Count) { throw "BUS missing Support Lead" }
  }
  $Hotel = $Activities | Where-Object { $_.activity_id -eq 'hotel' }
  $AllPeople = @($Request.participants) + @($Request.support_members) + @($Request.faculty_members)
  $HotelIds = @($Hotel.groups | ForEach-Object { $_.participant_ids })
  if ($HotelIds.Count -ne $AllPeople.Count -or $Hotel.room_summary.total_rooms -ne $Hotel.groups.Count) { throw "27-person hotel manifest or room count failed" }
  $PeopleById = @{}
  foreach ($Person in $Request.participants) { $PeopleById[$Person.id] = $Person.attributes.Gender }
  foreach ($Person in $Request.support_members) { $PeopleById[$Person.id] = $Person.gender }
  foreach ($Room in $Hotel.groups) {
    if ($Room.participant_ids.Count -eq 2) {
      $Left, $Right = $Room.participant_ids
      if (-not $PeopleById[$Left] -or $PeopleById[$Left] -ne $PeopleById[$Right]) { throw 'Automatic hotel room is not same-gender compatible' }
    }
  }
  $Reflection = $Activities | Where-Object { $_.activity_id -eq 'reflection' }
  if ($Reflection.sessions.Count -ne 27 -or @($Reflection.sessions.participant_id | Sort-Object -Unique).Count -ne 27) { throw "27-person reflection appointments missing/duplicated" }
}

$Reports = @()
foreach ($Case in @(@{chemistry=$true;seconds=20}, @{chemistry=$true;seconds=30}, @{chemistry=$false;seconds=30})) {
  $Chemistry = $Case.chemistry
  $Payload.configuration.include_business_chemistry = $Chemistry
  $Payload.configuration.time_limit_seconds = $Case.seconds
  $Timer = [Diagnostics.Stopwatch]::StartNew()
  try {
    $Result = Invoke-RestMethod -Method Post -Uri "$BaseUri/api/optimize" -ContentType 'application/json' -Body ($Payload | ConvertTo-Json -Depth 24) -TimeoutSec 180
  } catch {
    # CI preserves the frozen backend/frontend stderr logs in the finally block.
    throw "Real 27-person /api/optimize failed after $([math]::Round($Timer.Elapsed.TotalSeconds,2)) seconds: $($_.Exception.Message)"
  }
  $Timer.Stop()
  Assert-SixActivities $Result $Payload
  if ($Case.seconds -eq 30 -and $Timer.Elapsed.TotalSeconds -le 30) { throw "Regression did not cross the old 30-second proxy timeout" }
  $Reports += @{chemistry=$Chemistry;core_budget_seconds=$Case.seconds;http_status=200;seconds=$Timer.Elapsed.TotalSeconds;solver_status=$Result.allocation.status;activity_count=$Result.allocation.activities.Count}
  Write-Host "Real packaged 27-person request: Chemistry=$Chemistry HTTP 200, $([math]::Round($Timer.Elapsed.TotalSeconds,2)) seconds, all six activities validated."
}
$Reports | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $DiagnosticDirectory 'allocation27-results.json') -Encoding UTF8

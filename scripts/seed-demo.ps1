# Demo seed — pre-stages a job + three ranked candidates with mixed verification.
# Use this when the live webcam / ML scoring path is unavailable on stage.
# Re-runnable: each run adds fresh candidates (timestamped emails).

$ErrorActionPreference = "Stop"
$B = "http://localhost:3000"

function Post($path, $body) {
  Invoke-RestMethod -Method POST -Uri "$B$path" `
    -Body ($body | ConvertTo-Json -Depth 5) `
    -ContentType 'application/json' -TimeoutSec 30
}

$run = Get-Date -Format "HHmmss"

# 1. Recruiter's job
$job = Post "/api/jobs" @{
  companyName    = "Northwind Robotics"
  title          = "Senior CV Engineer"
  domain         = "engineering"
  description    = "Own the vision pipeline end to end: capture, scoring, and the recruiter UI."
  requiredSkills = "python, ffmpeg, react"
}
Write-Host "job        -> $($job.id)"

# 2. Three candidates. The mix is deliberate: it makes the ranking and the
#    green/red Verified badges mean something instead of being a single row.
$people = @(
  @{ name = "Aditi Sharma";  domain = "engineering"; pass = $true  }
  @{ name = "Rohan Verma";   domain = "engineering"; pass = $false }
  @{ name = "Meera Iyer";    domain = "sales";       pass = $true  }
)

$first = $null
foreach ($p in $people) {
  $email = "$($p.name.Split(' ')[0].ToLower()).demo.$run@example.com"
  $cand = Post "/api/candidates" @{
    name          = $p.name
    email         = $email
    domain        = $p.domain
    resumeFileUrl = "$($p.name.Split(' ')[0].ToLower())_resume.pdf"
  }

  if ($p.pass) {
    # A passing session is what flips Candidate.verified -> true, which is
    # what the green badge and the 0.4 verified weight both read from.
    $null = Post "/api/verification-sessions" @{
      candidateId   = $cand.id
      gazeScore     = 0.86
      lipSyncScore  = 0.91
      audioScore    = 0.94
      livenessScore = 0.97
      result        = "pass"
      reviewedByHR  = $false
    }
  }

  $null = Post "/api/applications" @{
    candidateId = $cand.id
    jobId      = $job.id
    status     = "applied"
  }

  if (-not $first) { $first = $cand }
  Write-Host ("candidate  -> {0,-14} domain={1,-11} verified={2}" -f $p.name, $p.domain, $p.pass)
}

# 3. Rank them so the table is already ordered when you walk in
$null = Post "/api/jobs/$($job.id)/shortlist" $null

Write-Host ""
Write-Host "READY. Open $B/jobs/$($job.id)/candidates"
Write-Host "Expected ranking: Aditi 1.00 (verified+domain) > Rohan 0.60 (domain only) > Meera 0.40 (verified only)"
Write-Host "candidateId for browser localStorage: $($first.id)"

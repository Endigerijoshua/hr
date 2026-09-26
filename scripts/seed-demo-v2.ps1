# Demo seed v2 — three jobs across three domains, 15 candidates each, with a
# realistic spread of resume quality and verification outcomes.
#
# Replace scripts/seed-demo.ps1 (kept for reference). Use this when the live
# webcam / ML scoring path is unavailable on stage.
#
# IDEMPOTENT: emails are deterministic (no timestamp suffix), and every write
# goes through Upsert-Candidate, which reuses an existing candidate when the
# email is already present. Re-running this does not create duplicates and does
# not blow up on the Candidate.email unique constraint.
#
# Synthetic verification sessions are inserted straight through the API — the
# point of seeded data is to NOT need a webcam per candidate. Real clips are
# still what you use for the live demo moment (scripts/seed-demo.ps1's note).

$ErrorActionPreference = "Stop"
$B = "http://localhost:3000"

function Post($path, $body) {
  Invoke-RestMethod -Method POST -Uri "$B$path" `
    -Body ($body | ConvertTo-Json -Depth 5) `
    -ContentType 'application/json' -TimeoutSec 30
}

# ---------------------------------------------------------------------------
# Re-runnable primitives
# ---------------------------------------------------------------------------

# One snapshot of existing candidates, keyed by email, so repeat runs reuse
# rather than duplicate. Refreshed lazily after each insert.
$script:ByEmail = @{}

function Load-Candidates {
  $script:ByEmail = @{}
  foreach ($c in (Invoke-RestMethod -Uri "$B/api/candidates" -TimeoutSec 30)) {
    $script:ByEmail[$c.email] = $c
  }
}

function Upsert-Candidate($name, $email, $domain, $skills) {
  if ($script:ByEmail.ContainsKey($email)) {
    return $script:ByEmail[$email]
  }
  $c = Post "/api/candidates" @{
    name          = $name
    email         = $email
    domain        = $domain
    skills        = $skills
    resumeFileUrl = "$($name.Split(' ')[0].ToLower())_resume.pdf"
  }
  $script:ByEmail[$email] = $c
  return $c
}

function Upsert-Job($company, $title, $domain, $description, $skills) {
  $key = "$company|$title"
  if ($script:ByJob.ContainsKey($key)) {
    return $script:ByJob[$key]
  }
  $j = Post "/api/jobs" @{
    companyName    = $company
    title          = $title
    domain         = $domain
    description    = $description
    requiredSkills = $skills
  }
  $script:ByJob[$key] = $j
  return $j
}

# Application rows can't be looked up by (candidate, job) through any existing
# endpoint, so we read the job's existing applications once and preload the
# guard map. Without this, every re-run inserts a second row per candidate and
# the ranking table silently doubles.
function Load-Applications($jobId) {
  try {
    foreach ($a in (Invoke-RestMethod -Uri "$B/api/jobs/$jobId/applications" -TimeoutSec 30)) {
      $script:ByApp["$($a.candidateId)|$($a.jobId)"] = $true
    }
  } catch {
    Write-Warning "Could not preload applications for $jobId : $($_.Exception.Message)"
  }
}

function Ensure-Application($candidateId, $jobId) {
  $key = "$candidateId|$jobId"
  if ($script:ByApp.ContainsKey($key)) { return }
  $null = Post "/api/applications" @{ candidateId = $candidateId; jobId = $jobId; status = "applied" }
  $script:ByApp[$key] = $true
}

# Only create a verification session if this candidate has none. Preloaded from
# the API at startup — without that, every re-run stacks another session per
# candidate and the "latest verdict" lookup becomes meaningless.
function Ensure-Verification($candidateId, $gaze, $lip, $aud, $live, $result, $reviewed) {
  if ($script:ByVerified.ContainsKey($candidateId)) { return }
  $null = Post "/api/verification-sessions" @{
    candidateId   = $candidateId
    gazeScore     = $gaze
    lipSyncScore  = $lip
    audioScore    = $aud
    livenessScore = $live
    result        = $result
    reviewedByHR  = $reviewed
  }
  $script:ByVerified[$candidateId] = $true
}

# ---------------------------------------------------------------------------
# Load existing state once
# ---------------------------------------------------------------------------
Load-Candidates
$script:ByJob = @{}
foreach ($j in (Invoke-RestMethod -Uri "$B/api/jobs" -TimeoutSec 30)) {
  $script:ByJob["$($j.companyName)|$($j.title)"] = $j
}
$script:ByApp = @{}
$script:ByVerified = @{}
foreach ($s in (Invoke-RestMethod -Uri "$B/api/verification-sessions" -TimeoutSec 30)) {
  $script:ByVerified[$s.candidateId] = $true
}

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
# Each candidate carries: name, email, domain, skills, and a verification
# profile (@{ g,l,a,v,result,hr }) or $null for unverified.
#
# Quality is encoded in the SKILL LIST, not the name: "strong" candidates hit
# most of the job's requiredSkills, "partial" hit a couple, "irrelevant" hit
# none and usually sit in a different domain. That is what the shortlist
# scorer measures, so the 0.6 cutoff lands mid-table instead of admitting
# everyone in a domain.

$JOBS = @(
  @{
    key    = "sales"
    company = "Northwind Robotics"
    title   = "Sales Executive"
    domain  = "sales"
    description = "Own the full outbound and inbound pipeline for industrial robotics across South Asia. Own pipeline targets, run demos, and close."
    requiredSkills = "salesforce, crm, pipeline management, b2b saas, negotiation, hubspot, forecasting"
    candidates = @(
      @{ n = "Aditi Sharma";      d = "sales";       s = "salesforce, crm, pipeline management, b2b saas, negotiation, forecasting"; v = $null }
      @{ n = "Rohan Verma";       d = "sales";       s = "salesforce, crm, b2b saas, negotiation, hubspot"; v = $null }
      @{ n = "Priya Nair";        d = "sales";       s = "hubspot, negotiation, forecasting, b2b saas"; v = $null }
      @{ n = "Karan Malhotra";    d = "sales";       s = "crm, pipeline management, negotiation"; v = $null }
      @{ n = "Sneha Rao";         d = "sales";       s = "salesforce, forecasting"; v = $null }
      @{ n = "Imran Qureshi";     d = "sales";       s = "b2b saas, crm, pipeline management, hubspot, negotiation, forecasting"; v = $null }
      @{ n = "Divya Menon";       d = "sales";       s = "negotiation, crm"; v = $null }
      @{ n = "Arjun Bhat";        d = "engineering"; s = "python, ffmpeg, react, node"; v = $null }
      @{ n = "Nikhil Joshi";      d = "engineering"; s = "python, react, kubernetes, docker"; v = $null }
      @{ n = "Tanvi Desai";       d = "engineering"; s = "typescript, node, postgres, aws"; v = $null }
      @{ n = "Farhan Ali";        d = "design";      s = "figma, illustrator, brand systems, prototyping"; v = $null }
      @{ n = "Meera Iyer";        d = "design";      s = "sketch, figma, wireframing, ux research"; v = $null }
      @{ n = "Vikram Sethi";      d = "finance";     s = "financial modeling, excel, valuation, fp&a"; v = $null }
      @{ n = "Aisha Khan";        d = "data";        s = "sql, tableau, etl, statistics"; v = $null }
      @{ n = "Rohit Chandra";     d = "sales";       s = "customer support, ticketing"; v = $null }
    )
  }
  @{
    key    = "engineering"
    company = "Lumen Health"
    title   = "Software Engineer"
    domain  = "engineering"
    description = "Build and ship the patient-facing scheduling service. TypeScript, Postgres, and a real-time event pipeline."
    requiredSkills = "typescript, react, node, postgres, docker, kubernetes, aws, ci/cd"
    candidates = @(
      @{ n = "Rohan Verma";    d = "engineering"; s = "typescript, react, node, postgres, docker, kubernetes, aws, ci/cd"; v = $null }
      @{ n = "Nikhil Joshi";   d = "engineering"; s = "typescript, react, node, postgres, docker, aws"; v = $null }
      @{ n = "Tanvi Desai";    d = "engineering"; s = "node, postgres, docker, ci/cd, typescript"; v = $null }
      @{ n = "Kabir Anand";    d = "engineering"; s = "react, typescript, aws, kubernetes"; v = $null }
      @{ n = "Sneha Rao";      d = "engineering"; s = "typescript, node, postgres, ci/cd"; v = $null }
      @{ n = "Arjun Bhat";     d = "engineering"; s = "python, ffmpeg, react, opencv, numpy"; v = $null }
      @{ n = "Ishaan Kapoor";  d = "engineering"; s = "docker, kubernetes, aws, terraform"; v = $null }
      @{ n = "Zoya Khan";      d = "engineering"; s = "typescript, react"; v = $null }
      @{ n = "Dev Patel";      d = "engineering"; s = "node, ci/cd, git, linux"; v = $null }
      @{ n = "Ananya Gupta";   d = "engineering"; s = "golang, grpc, kafka, postgres"; v = $null }
      @{ n = "Aditi Sharma";   d = "sales";       s = "salesforce, crm, pipeline management, negotiation"; v = $null }
      @{ n = "Priya Nair";     d = "sales";       s = "hubspot, negotiation, forecasting"; v = $null }
      @{ n = "Vikram Sethi";   d = "finance";     s = "financial modeling, excel, valuation"; v = $null }
      @{ n = "Meera Iyer";     d = "design";      s = "figma, illustrator, brand systems"; v = $null }
      @{ n = "Rohit Chandra";  d = "support";     s = "customer support, ticketing, zendesk"; v = $null }
    )
  }
  @{
    key    = "finance"
    company = "Corvus Capital"
    title   = "Financial Analyst"
    domain  = "finance"
    description = "Build the quarterly forecast and variance pack for a 40-person portfolio fund. Hands-on with the model, not just the deck."
    requiredSkills = "financial modeling, excel, valuation, fp&a, sql, forecasting, power bi, variance analysis"
    candidates = @(
      @{ n = "Vikram Sethi";   d = "finance"; s = "financial modeling, excel, valuation, fp&a, forecasting, variance analysis"; v = $null }
      @{ n = "Aisha Khan";     d = "finance"; s = "financial modeling, excel, valuation, power bi, fp&a"; v = $null }
      @{ n = "Neha Bhatt";     d = "finance"; s = "financial modeling, excel, forecasting, variance analysis"; v = $null }
      @{ n = "Sameer Kaur";    d = "finance"; s = "valuation, excel, fp&a"; v = $null }
      @{ n = "Pooja Menon";    d = "finance"; s = "financial modeling, excel, sql, power bi"; v = $null }
      @{ n = "Rehan Ali";      d = "finance"; s = "excel, fp&a, forecasting"; v = $null }
      @{ n = "Kavya Reddy";    d = "data";    s = "sql, tableau, statistics, python"; v = $null }
      @{ n = "Nikhil Joshi";   d = "engineering"; s = "typescript, react, node, postgres"; v = $null }
      @{ n = "Rohan Verma";    d = "engineering"; s = "python, docker, kubernetes, aws"; v = $null }
      @{ n = "Aditi Sharma";   d = "sales";   s = "salesforce, crm, pipeline management"; v = $null }
      @{ n = "Meera Iyer";     d = "design";  s = "figma, sketch, ux research"; v = $null }
      @{ n = "Tanvi Desai";    d = "engineering"; s = "typescript, node, postgres, docker, ci/cd"; v = $null }
      @{ n = "Rohit Chandra";  d = "support"; s = "customer support, ticketing, zendesk"; v = $null }
      @{ n = "Farhan Ali";     d = "data";    s = "sql, etl, tableau, dbt, airflow"; v = $null }
      @{ n = "Ishita Sen";     d = "finance"; s = "accounting, audit, quickbooks, tally"; v = $null }
    )
  }
)

# Verification profiles, applied by candidate name. Deliberately a MIX —
# a demo where 100% of candidates are "pass" reads as fake and gives the
# reviewer nothing to click on. Two outright fails are included so the
# red badge is visible on stage.
#
#   result  gaze lip  aud  live  reviewedByHR
$VERIF = @{
  "Aditi Sharma"  = @{ g = 0.86; l = 0.91; a = 0.94; v = 0.97; result = "pass";    hr = $false }
  "Rohan Verma"   = @{ g = 0.55; l = 0.82; a = 0.88; v = 0.94; result = "pass";    hr = $false }
  "Priya Nair"    = @{ g = 0.61; l = 0.44; a = 0.79; v = 0.92; result = "flagged"; hr = $true  }
  "Karan Malhotra"= @{ g = 0.38; l = 0.71; a = 0.66; v = 0.90; result = "flagged"; hr = $true  }
  "Sneha Rao"     = @{ g = 0.72; l = 0.63; a = 0.81; v = 0.95; result = "pass";    hr = $false }
  "Imran Qureshi" = @{ g = 0.79; l = 0.88; a = 0.90; v = 0.96; result = "pass";    hr = $false }
  "Divya Menon"   = @{ g = 0.44; l = 0.58; a = 0.72; v = 0.88; result = "flagged"; hr = $true  }
  "Tanvi Desai"   = @{ g = 0.31; l = 0.22; a = 0.48; v = 0.19; result = "fail";    hr = $true  }
  "Arjun Bhat"    = @{ g = 0.68; l = 0.77; a = 0.85; v = 0.93; result = "pass";    hr = $false }
  "Rohit Chandra" = @{ g = 0.29; l = 0.18; a = 0.41; v = 0.14; result = "fail";    hr = $true  }
  "Vikram Sethi"  = @{ g = 0.81; l = 0.84; a = 0.89; v = 0.95; result = "pass";    hr = $false }
  "Aisha Khan"    = @{ g = 0.64; l = 0.73; a = 0.80; v = 0.91; result = "pass";    hr = $false }
  "Nikhil Joshi"  = @{ g = 0.58; l = 0.49; a = 0.74; v = 0.89; result = "flagged"; hr = $true  }
  "Neha Bhatt"    = @{ g = 0.76; l = 0.80; a = 0.87; v = 0.94; result = "pass";    hr = $false }
  "Kabir Anand"   = @{ g = 0.66; l = 0.69; a = 0.78; v = 0.92; result = "pass";    hr = $false }
  "Ishaan Kapoor" = @{ g = 0.52; l = 0.61; a = 0.70; v = 0.87; result = "flagged"; hr = $true  }
  "Zoya Khan"     = @{ g = 0.74; l = 0.79; a = 0.83; v = 0.93; result = "pass";    hr = $false }
  "Pooja Menon"   = @{ g = 0.60; l = 0.67; a = 0.76; v = 0.90; result = "pass";    hr = $false }
  "Meera Iyer"    = @{ g = 0.47; l = 0.55; a = 0.68; v = 0.85; result = "flagged"; hr = $true  }
  "Sameer Kaur"   = @{ g = 0.70; l = 0.72; a = 0.81; v = 0.92; result = "pass";    hr = $false }
  "Rehan Ali"     = @{ g = 0.53; l = 0.47; a = 0.64; v = 0.88; result = "flagged"; hr = $true  }
  "Kavya Reddy"   = @{ g = 0.77; l = 0.83; a = 0.86; v = 0.94; result = "pass";    hr = $false }
  "Dev Patel"     = @{ g = 0.41; l = 0.52; a = 0.63; v = 0.84; result = "flagged"; hr = $true  }
  "Ananya Gupta"  = @{ g = 0.69; l = 0.75; a = 0.82; v = 0.91; result = "pass";    hr = $false }
  "Farhan Ali"    = @{ g = 0.56; l = 0.62; a = 0.71; v = 0.89; result = "flagged"; hr = $true  }
  "Kavya S Nair"  = @{ g = 0.71; l = 0.76; a = 0.84; v = 0.92; result = "pass";    hr = $false }
  "Ishita Sen"    = @{ g = 0.63; l = 0.68; a = 0.75; v = 0.90; result = "pass";    hr = $false }
}

# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------
$summary = @()

foreach ($j in $JOBS) {
  $job = Upsert-Job $j.company $j.title $j.domain $j.description $j.requiredSkills
  Load-Applications $job.id
  Write-Host ""
  Write-Host "JOB $($j.title) @ $($j.company)  -> $($job.id)"

  foreach ($c in $j.candidates) {
    $email = ("{0}.{1}@example.com" -f ($c.n -replace "[^A-Za-z]", "").ToLower(), $j.key)
    $cand = Upsert-Candidate $c.n $email $c.d $c.s

    if ($VERIF.ContainsKey($c.n)) {
      $p = $VERIF[$c.n]
      Ensure-Verification $cand.id $p.g $p.l $p.a $p.v $p.result $p.hr
    }

    Ensure-Application $cand.id $job.id
  }

  # Rank so the table is already ordered when you walk in.
  $ranked = Post "/api/jobs/$($job.id)/shortlist" $null
  $shortlisted = @($ranked.updated | Where-Object { $_.shortlisted }).Count
  $total = @($ranked.updated).Count
  $pct = [math]::Round(100.0 * $shortlisted / $total, 1)
  Write-Host ("  shortlisted {0}/{1} ({2}%)" -f $shortlisted, $total, $pct)

  $summary += [pscustomobject]@{
    job = $j.title
    company = $j.company
    jobId = $job.id
    applicants = $total
    shortlisted = $shortlisted
    pct = $pct
  }
}

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "=============================================="
$summary | Format-Table -AutoSize | Out-String | Write-Host

foreach ($row in $summary) {
  $ranked = Invoke-RestMethod -Method POST -Uri "$B/api/jobs/$($row.jobId)/shortlist" -Body "{}" `
    -ContentType 'application/json' -TimeoutSec 30
  Write-Host "--- $($row.job) (top 3 + bottom 2) ---"
  foreach ($a in @($ranked.updated)[0..2] + @($ranked.updated)[-2..-1]) {
    $verdict = if ($a.shortlisted) { "SHORTLISTED" } else { "rejected  " }
    Write-Host ("  {0}  score={1:N2}  {2,-16}  {3}" -f $verdict, $a.shortlistScore, $a.candidate.domain, $a.candidate.name)
  }
  Write-Host ""
}

Write-Host "READY. Open $B/jobs"

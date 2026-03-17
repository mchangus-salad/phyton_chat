param(
    [string]$Username = "devuser",
    [string]$Password = "devpassword123!",
    [string]$Email = "devuser@example.com",
    [switch]$Superuser
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
Set-Location $repoRoot

$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "Python virtual environment not found. Run .\scripts\dev-up.ps1 first."
}

$isSuperuser = if ($Superuser) { "True" } else { "False" }

$pythonCode = @"
from django.contrib.auth import get_user_model

User = get_user_model()
username = "$Username"
email = "$Email"
password = "$Password"
is_superuser = $isSuperuser

user, created = User.objects.get_or_create(
    username=username,
    defaults={"email": email},
)

if user.email != email:
    user.email = email

user.is_superuser = is_superuser
user.is_staff = is_superuser
user.set_password(password)
user.save()

if created:
    print(f"Created user: {username} (superuser={is_superuser})")
else:
    print(f"Updated user: {username} (superuser={is_superuser})")
"@

& $venvPython manage.py shell -c $pythonCode
if ($LASTEXITCODE -ne 0) {
    throw "Failed to create/update user."
}

Write-Host "User is ready. You can now request a JWT token at /api/v1/auth/token/."

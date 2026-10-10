# End of a work session: stop services that bills by the hour (not ALB, which is billed by the hour even when idle).
# For breaks longer than a day or two, also run alb-down.ps1.

. "$PSScriptRoot\_common.ps1"
Assert-AwsLogin

# Stop services first. Order matters
Write-Host "Scaling ECS services to 0..."
Set-ServiceCount 0

# Stop RDS
Write-Host "Stopping RDS..."
$status = Get-DbStatus
if ($status -eq "available") {
    Invoke-Aws rds stop-db-instance --db-instance-identifier $DbId --query "DBInstance.DBInstanceStatus" --output text | Out-Null
    Write-Host "  $DbId is stopping (AWS restarts it automatically after 7 days)"
} else {
    Write-Host "  $DbId is '$status', nothing to do"
}

# Verify ALB status and print a reminder about the ALB billing
if (Get-AlbArn) {
    Write-Host "`nThe ALB still exists and bills ~`$0.03/hr. For a longer break run: .\infra\aws\scripts\alb-down.ps1"
}
Write-Host "Session stopped."

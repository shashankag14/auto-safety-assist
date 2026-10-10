# Delete the ALB for longer breaks (it bills ~$0.03/hr even with no traffic).
# Its listener and rules are deleted with it; target groups, services and everything else stay,
# so alb-up.ps1 can recreate it in a minute.
#
# Usage: .\infra\aws\scripts\alb-down.ps1

. "$PSScriptRoot\_common.ps1"
Assert-AwsLogin

$albArn = Get-AlbArn
if (-not $albArn) {
    Write-Host "No ALB named $AlbName, nothing to delete."
    exit 0
}

# services first: running tasks behind a deleted ALB still cost money and can't be reached
Write-Host "Scaling ECS services to 0..."
Set-ServiceCount 0

Write-Host "Deleting ALB $AlbName..."
Invoke-Aws elbv2 delete-load-balancer --load-balancer-arn $albArn
Invoke-Aws elbv2 wait load-balancers-deleted --load-balancer-arns $albArn
Write-Host "ALB deleted. Recreate it with: .\infra\aws\scripts\alb-up.ps1 (session-start.ps1 does this automatically)"

# Start of a work session: database first, then the ALB (if it was deleted), then the services.
# The retriever fails its health checks if the database isn't up, hence the order.

. "$PSScriptRoot\_common.ps1"
Assert-AwsLogin

# STart RDS
Write-Host "Starting RDS..."
$status = Get-DbStatus
if ($status -eq "stopped") {
    Invoke-Aws rds start-db-instance --db-instance-identifier $DbId --query "DBInstance.DBInstanceStatus" --output text | Out-Null
} elseif ($status -ne "available") {
    Write-Host "  $DbId is '$status', waiting for it"
}
Invoke-Aws rds wait db-instance-available --db-instance-identifier $DbId
Write-Host "  $DbId is available"

# Create ALB if not exists
if (-not (Get-AlbArn)) {
    Write-Host "ALB missing, creating it..."
    & "$PSScriptRoot\alb-up.ps1"
} else {
    Write-Host "Checking the ALB allows your current IP..."
    Update-AlbIpRule
}

# Start ECS services with single service count each
Write-Host "Scaling ECS services to 1..."
Set-ServiceCount 1
Write-Host "Waiting for services to become stable (a few minutes)..."
Invoke-Aws ecs wait services-stable --cluster $Cluster --services @Services

# Verify if the health is fine
Write-Host "Target health:"
foreach ($route in $Routes) {
    $tg = Invoke-Aws elbv2 describe-target-groups --names $route.TargetGroup --query "TargetGroups[0].TargetGroupArn" --output text
    $states = Invoke-Aws elbv2 describe-target-health --target-group-arn $tg --query "TargetHealthDescriptions[].TargetHealth.State" --output text
    Write-Host "  $($route.Service): $states"
}

# Show ALB DNS name for convenience
$dns = Invoke-Aws elbv2 describe-load-balancers --names $AlbName --query "LoadBalancers[0].DNSName" --output text
Write-Host "`nReady: http://$dns  (try http://$dns/database_details)"

# Create the ALB, its HTTP listener and the path rules that forward to the existing target groups.
# Safe to re-run: does nothing if the ALB already exists.

. "$PSScriptRoot\_common.ps1"
Assert-AwsLogin

# Check if the ALB already exists - noop
if (Get-AlbArn) {
    $dns = Invoke-Aws elbv2 describe-load-balancers --names $AlbName --query "LoadBalancers[0].DNSName" --output text
    Write-Host "ALB already exists: http://$dns"
    exit 0
}

$vpc = Invoke-Aws ec2 describe-vpcs --filters "Name=isDefault,Values=true" --query "Vpcs[0].VpcId" --output text
# an ALB needs subnets in at least 2 AZs; the default VPC has one default subnet per AZ
$subnets = (Invoke-Aws ec2 describe-subnets --filters "Name=vpc-id,Values=$vpc" "Name=default-for-az,Values=true" `
    --query "Subnets[].SubnetId" --output text) -split "\s+" | Where-Object { $_ }
$albSg = Invoke-Aws ec2 describe-security-groups --filters "Name=group-name,Values=$AlbSgName" `
    --query "SecurityGroups[0].GroupId" --output text

Write-Host "Checking the ALB security group allows your current IP..."
Update-AlbIpRule

Write-Host "Creating ALB $AlbName..."
$albArn = Invoke-Aws elbv2 create-load-balancer --name $AlbName --type application --scheme internet-facing `
    --subnets @subnets --security-groups $albSg --tags "Key=Project,Value=auto-safety-assist" `
    --query "LoadBalancers[0].LoadBalancerArn" --output text
Invoke-Aws elbv2 wait load-balancer-available --load-balancer-arns $albArn

# unknown paths get a plain 404 instead of being forwarded anywhere
$listener = Invoke-Aws elbv2 create-listener --load-balancer-arn $albArn --protocol HTTP --port 80 `
    --default-actions "Type=fixed-response,FixedResponseConfig={StatusCode=404,ContentType=text/plain,MessageBody=no-route}" `
    --query "Listeners[0].ListenerArn" --output text

foreach ($route in $Routes) {
    $tg = Invoke-Aws elbv2 describe-target-groups --names $route.TargetGroup --query "TargetGroups[0].TargetGroupArn" --output text
    Invoke-Aws elbv2 create-rule --listener-arn $listener --priority $route.Priority `
        --conditions "Field=path-pattern,Values=$($route.Paths)" `
        --actions "Type=forward,TargetGroupArn=$tg" | Out-Null
    Write-Host "  $($route.Paths) -> $($route.TargetGroup)"
}

$dns = Invoke-Aws elbv2 describe-load-balancers --load-balancer-arns $albArn --query "LoadBalancers[0].DNSName" --output text
Write-Host "ALB ready: http://$dns  (returns 503 until the services are scaled up)"

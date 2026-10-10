# Shared settings and helpers, dot-sourced by the session/ALB scripts.
# Everything is looked up by name, so the scripts work from a fresh terminal.

$ErrorActionPreference = "Stop"
$env:AWS_PROFILE = "auto-safety"

$Cluster  = "auto-safety-assist"
$Services = @("intent-classifier", "retriever", "response-generator")
$DbId     = "auto-safety-assist-db"
$AlbName  = "asa-alb"
$AlbSgName = "auto-safety-assist-alb-sg"

# service name -> target group name, port and listener rule (priority + paths)
$Routes = @(
    @{ Service = "intent-classifier";  TargetGroup = "asa-classifier-tg"; Priority = 10; Paths = "/classify" }
    @{ Service = "retriever";          TargetGroup = "asa-retriever-tg";  Priority = 20; Paths = "/retrieve,/database_details" }
    @{ Service = "response-generator"; TargetGroup = "asa-generator-tg";  Priority = 30; Paths = "/generate,/answer" }
)

# $ErrorActionPreference doesn't catch failing native commands in Windows PowerShell 5.1,
# so every aws call goes through this and throws on a non-zero exit code
function Invoke-Aws {
    $out = & aws @args
    if ($LASTEXITCODE -ne 0) { throw "aws $($args -join ' ') failed (exit code $LASTEXITCODE)" }
    return $out
}

function Assert-AwsLogin {
    # in Windows PowerShell 5.1, redirecting a native command's stderr under "Stop" throws on the
    # first stderr line, so relax it just for this check
    $ErrorActionPreference = "Continue"
    & aws sts get-caller-identity --query Arn --output text 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Not logged in. Run: aws login --profile auto-safety" }
}

function Get-AlbArn {
    # empty string (not an error) when the ALB doesn't exist
    return Invoke-Aws elbv2 describe-load-balancers `
        --query "LoadBalancers[?LoadBalancerName=='$AlbName'].LoadBalancerArn" --output text
}

function Get-DbStatus {
    return Invoke-Aws rds describe-db-instances --db-instance-identifier $DbId `
        --query "DBInstances[0].DBInstanceStatus" --output text
}

function Set-ServiceCount([int]$Count) {
    foreach ($svc in $Services) {
        Invoke-Aws ecs update-service --cluster $Cluster --service $svc --desired-count $Count `
            --query "service.serviceName" --output text | Out-Null
        Write-Host "  $svc -> desired count $Count"
    }
}

# Home IPs change (router restart etc.), which silently breaks the ALB's "my-laptop-only" rule.
# Replace any old laptop IP with the current one.
function Update-AlbIpRule {
    $sg = Invoke-Aws ec2 describe-security-groups --filters "Name=group-name,Values=$AlbSgName" `
        --query "SecurityGroups[0].GroupId" --output text
    $current = "$((Invoke-RestMethod https://checkip.amazonaws.com).Trim())/32"
    $existing = (Invoke-Aws ec2 describe-security-groups --group-ids $sg `
        --query "SecurityGroups[0].IpPermissions[].IpRanges[?Description=='my-laptop-only'].CidrIp" `
        --output text) -split "\s+" | Where-Object { $_ }

    foreach ($cidr in $existing | Where-Object { $_ -ne $current }) {
        Invoke-Aws ec2 revoke-security-group-ingress --group-id $sg `
            --ip-permissions "IpProtocol=tcp,FromPort=80,ToPort=80,IpRanges=[{CidrIp=$cidr}]" | Out-Null
        Write-Host "  removed old laptop IP $cidr from $AlbSgName"
    }
    if ($existing -notcontains $current) {
        Invoke-Aws ec2 authorize-security-group-ingress --group-id $sg `
            --ip-permissions "IpProtocol=tcp,FromPort=80,ToPort=80,IpRanges=[{CidrIp=$current,Description=my-laptop-only}]" | Out-Null
        Write-Host "  allowed current laptop IP $current on $AlbSgName"
    } else {
        Write-Host "  laptop IP $current already allowed"
    }
}

<#
.SYNOPSIS
    Build, push va deploy/cap nhat mkt-insight-agent len GreenNode AgentBase
    Runtime. Theo dung tung buoc cua docs/12-build-deploy.md muc 12.7.

.DESCRIPTION
    Script nay LAP RAP lai cac lenh trong docs/12 thanh mot luong co tham so,
    KHONG tu viet lai logic lay token IAM hay goi API AgentBase - van dung
    dung script cua bo skill chinh thuc (.claude/skills/agentbase/scripts/*),
    dung nhu canh bao trong docs/12 muc 12.1: "Dung tu viet doan lay token IAM".

    Yeu cau truoc khi chay:
      1. Da `claude plugin marketplace add vngcloud/greennode-agentbase-skills`
         (docs/12 muc 12.1) - cac script .sh nam trong .claude/skills/agentbase/scripts/.
      2. Da dat GREENNODE_CLIENT_ID / GREENNODE_CLIENT_SECRET trong shell hien tai.
      3. Da co API key MaaS o trang thai ACTIVE va model da ENABLED (muc 12.6).
      4. Docker Desktop dang chay, ho tro buildx (cho --platform linux/amd64).

.PARAMETER Version
    Tag image, vi du "v1.0.0". Bat buoc.

.PARAMETER BackendName
    Ten backend cua repository tren vCR (LAY BANG `cr.sh repositories list`,
    KHONG PHAI ten hien thi tren console - loi pho bien nhat o buoc nay,
    xem docs/12 muc 12.7). Bat buoc khi -Push hoac -CreateRuntime.

.PARAMETER RuntimeId
    ID cua Agent Runtime da ton tai - truyen vao de CAP NHAT (PATCH) thay vi
    tao moi. Bo trong lan dau deploy.

.PARAMETER BuildOnly
    Chi build image cuc bo (buoc "Xong khi" cua docs/17 T14) - khong dang
    nhap/push/goi API GreenNode. Dung de kiem tra nhanh khong can credential.

.EXAMPLE
    # Chi build + chay thu cuc bo (dung nhu docs/17 T14 "Xong khi")
    .\scripts\deploy_greennode.ps1 -Version v1.0.0 -BuildOnly

.EXAMPLE
    # Deploy lan dau
    .\scripts\deploy_greennode.ps1 -Version v1.0.0 -BackendName my-backend

.EXAMPLE
    # Cap nhat runtime da co
    .\scripts\deploy_greennode.ps1 -Version v1.0.1 -BackendName my-backend -RuntimeId <id>
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Version,

    [string]$BackendName,

    [string]$RuntimeId,

    [switch]$BuildOnly
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$ImageName = "mkt-insight-agent"
$LocalTag = "${ImageName}:${Version}"

function Assert-Command($Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Thieu lenh bat buoc tren PATH: '$Name'"
    }
}

function Find-AgentbaseSkillScripts {
    <#
    Bo skill greennode-agentbase co the vao may bang HAI CACH khac nhau
    (docs/12-build-deploy.md muc 12.1), moi cach nam o mot noi khac nhau:
      1. `claude plugin marketplace add` + `claude plugin install` (khuyen
         nghi) -> cai vao thu muc NGUOI DUNG, co danh so phien ban:
         ~/.claude/plugins/cache/greennode-agentbase/greennode-agentbase/<version>/skills/agentbase/scripts
      2. Clone thu cong repo vao `.claude/skills/` CUA PROJECT (cach thay the
         trong docs) -> nam ngay trong repo: .claude/skills/agentbase/scripts

    Tra ve duong dan thu muc scripts dau tien tim thay, hoac $null.
    #>
    $projectPath = Join-Path $RepoRoot ".claude\skills\agentbase\scripts"
    if (Test-Path (Join-Path $projectPath "aip.sh")) { return $projectPath }

    $cacheRoot = Join-Path $env:USERPROFILE ".claude\plugins\cache\greennode-agentbase\greennode-agentbase"
    if (Test-Path $cacheRoot) {
        $latest = Get-ChildItem $cacheRoot -Directory -ErrorAction SilentlyContinue |
            Sort-Object { [version]($_.Name -replace '[^\d\.].*$', '') } -Descending |
            Select-Object -First 1
        if ($latest) {
            $pluginPath = Join-Path $latest.FullName "skills\agentbase\scripts"
            if (Test-Path (Join-Path $pluginPath "aip.sh")) { return $pluginPath }
        }
    }
    return $null
}

Write-Host "==> [1/5] Kiem tra dieu kien can" -ForegroundColor Cyan
Assert-Command "docker"
if (-not (Test-Path "$RepoRoot\Dockerfile")) {
    throw "Khong tim thay Dockerfile o goc du an: $RepoRoot"
}

Write-Host "==> [2/5] Build image ($LocalTag), BAT BUOC --platform linux/amd64" -ForegroundColor Cyan
docker build --platform linux/amd64 -t $LocalTag $RepoRoot
if ($LASTEXITCODE -ne 0) { throw "docker build that bai (exit $LASTEXITCODE)" }

if ($BuildOnly) {
    Write-Host "==> -BuildOnly: da build xong $LocalTag, dung tai day." -ForegroundColor Green
    Write-Host "    Kiem tra nhanh: docker run -p 8080:8080 --env-file .env $LocalTag"
    exit 0
}

Write-Host "==> [3/5] Dang nhap vCR va push image" -ForegroundColor Cyan
if (-not $BackendName) {
    throw "Thieu -BackendName. Lay bang: .claude/skills/agentbase/scripts/cr.sh repositories list"
}
$SkillScripts = Find-AgentbaseSkillScripts
if (-not $SkillScripts) {
    throw ("Khong tim thay script cua bo skill AgentBase (da kiem tra ca " +
           ".claude/skills/agentbase/scripts/ trong project lan " +
           "~/.claude/plugins/cache/greennode-agentbase/.../skills/agentbase/scripts/). " +
           "Import bo skill truoc (docs/12-build-deploy.md muc 12.1): " +
           "claude plugin marketplace add vngcloud/greennode-agentbase-skills && " +
           "claude plugin install greennode-agentbase@greennode-agentbase")
}
Write-Host "    Dung script skill tai: $SkillScripts" -ForegroundColor DarkGray
$DockerLogin = Join-Path $SkillScripts "docker_login.sh"
bash $DockerLogin
if ($LASTEXITCODE -ne 0) { throw "docker_login.sh that bai (exit $LASTEXITCODE)" }

$RemoteTag = "vcr.vngcloud.vn/$BackendName/${ImageName}:${Version}"
docker tag $LocalTag $RemoteTag
docker push $RemoteTag
if ($LASTEXITCODE -ne 0) { throw "docker push that bai (exit $LASTEXITCODE)" }
Write-Host "    Da push: $RemoteTag" -ForegroundColor Green

Write-Host "==> [4/5] Tao/cap nhat Agent Runtime" -ForegroundColor Cyan
$RuntimeScript = Join-Path $SkillScripts "runtime.sh"
if (-not (Test-Path $RuntimeScript)) {
    throw "Khong tim thay '$RuntimeScript' - xem huong dan import skill o buoc [3/5]."
}

if ($RuntimeId) {
    Write-Host "    Cap nhat runtime hien co: $RuntimeId" -ForegroundColor Yellow
    bash $RuntimeScript update --runtime-id $RuntimeId --image-url $RemoteTag
} else {
    Write-Host ("    CHUA co -RuntimeId - tao runtime MOI can bien moi truong " +
                "day du (LLM_MODEL, LLM_API_KEY, MKT_DATABASE__URL, MKT_ADMIN__TOKEN...). " +
                "Doc `.env` va dung dung cau lenh curl trong docs/12-build-deploy.md " +
                "muc 12.7 §7.2 (script nay KHONG tu doan cac gia tri bi mat do).") -ForegroundColor Yellow
    Write-Host "    Image da san sang de dan vao 'imageUrl': $RemoteTag"
    exit 0
}
if ($LASTEXITCODE -ne 0) { throw "runtime.sh that bai (exit $LASTEXITCODE)" }

Write-Host "==> [5/5] Lay URL that va nhac checklist nghiem thu" -ForegroundColor Cyan
bash $RuntimeScript endpoints list --runtime-id $RuntimeId
Write-Host ""
Write-Host "Kiem tra theo docs/12-build-deploy.md muc 12.7 §7.5:" -ForegroundColor Green
Write-Host "  curl <url>/health              # 200 {`"status`":`"ok`"}"
Write-Host "  curl <url>/readyz              # db=ok, dq=ok"
Write-Host "  curl <url>/api/dashboard/campaigns"
Write-Host "  curl -X POST <url>/invocations -d '{\"message\":\"Chien dich nao dang lo?\"}'"

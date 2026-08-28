#!/usr/bin/env bash
# 打包并上传 TestFlight。
#
# 前置（都要你本人办，我做不了）：
#   1. Apple Developer Program 会员（$99/年）
#   2. Xcode ▸ Settings ▸ Accounts 登录 Apple ID，让它自动签发证书和描述文件
#   3. App Store Connect 里建一个 App 记录，Bundle ID = me.timoz.sheepy
#   4. App Store Connect ▸ Users and Access ▸ Integrations 生成 API 密钥，
#      下载的 AuthKey_XXXXXX.p8 放到 ~/.appstoreconnect/private_keys/
#
# 用法：
#   export ASC_KEY_ID=XXXXXXXXXX
#   export ASC_ISSUER_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
#   export DEVELOPMENT_TEAM=XXXXXXXXXX      # 10 位 Team ID
#   ./apps/ios/upload_testflight.sh
set -euo pipefail
cd "$(dirname "$0")"

: "${ASC_KEY_ID:?需要 ASC_KEY_ID}"
: "${ASC_ISSUER_ID:?需要 ASC_ISSUER_ID}"
: "${DEVELOPMENT_TEAM:?需要 DEVELOPMENT_TEAM}"

BUILD="${BUILD:-$(date +%Y%m%d%H%M)}"   # 每次上传的 build 号必须递增
OUT="$(mktemp -d)"

echo "▸ 生成工程"
xcodegen generate

echo "▸ Archive（Release / arm64，带签名）"
xcodebuild archive \
  -project Sheepy.xcodeproj -scheme Sheepy \
  -destination 'generic/platform=iOS' \
  -archivePath "$OUT/Sheepy.xcarchive" \
  -allowProvisioningUpdates \
  DEVELOPMENT_TEAM="$DEVELOPMENT_TEAM" \
  CURRENT_PROJECT_VERSION="$BUILD"

cat > "$OUT/ExportOptions.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>method</key><string>app-store-connect</string>
  <key>teamID</key><string>$DEVELOPMENT_TEAM</string>
  <key>uploadSymbols</key><true/>
  <key>destination</key><string>upload</string>
</dict></plist>
PLIST

echo "▸ 导出并上传（build $BUILD）"
xcodebuild -exportArchive \
  -archivePath "$OUT/Sheepy.xcarchive" \
  -exportOptionsPlist "$OUT/ExportOptions.plist" \
  -exportPath "$OUT/export" \
  -allowProvisioningUpdates \
  -authenticationKeyIssuerID "$ASC_ISSUER_ID" \
  -authenticationKeyID "$ASC_KEY_ID" \
  -authenticationKeyPath "$HOME/.appstoreconnect/private_keys/AuthKey_${ASC_KEY_ID}.p8"

echo "✓ 已提交。App Store Connect ▸ TestFlight 里等构建处理完（通常 5~15 分钟）。"

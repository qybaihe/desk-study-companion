#!/usr/bin/env bash
# 一步配好 Worker 的机密。密码只在你的终端和 Cloudflare 之间走。
set -e
cd "$(dirname "$0")"

echo "① 设置数据库连接串"
echo "   粘贴（把 <密码> 换成 TiDB 控制台里的真实密码）："
echo "   mysql://<用户名>.root:<密码>@gateway01.<区域>.prod.aws.tidbcloud.com:4000/study_buddy"
echo
npx wrangler secret put DATABASE_URL

echo
echo "② 设置访问令牌（下面这串是随机生成的，直接粘贴即可）"
TOKEN=$(LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 40)
echo "   $TOKEN"
echo
npx wrangler secret put API_TOKEN

echo
echo "③ 重新部署使机密生效"
npx wrangler deploy

echo
echo "④ 自检"
curl -s https://sheepy.timoz.me/health; echo
echo
echo "记下这个 token，板子和 iOS 都要用："
echo "   $TOKEN"

#!/bin/bash
# 把 网页/ 发布到 Cloudflare Pages（bible-people-map.pages.dev）
# 第一次用要先登录：npx wrangler login
# GitHub Pages 不用跑这个：推送到 GitHub 就会自动发布
set -e
cd "$(dirname "$0")/.."
npx --yes wrangler@4 pages deploy 网页 --project-name bible-people-map --branch main --commit-dirty=true

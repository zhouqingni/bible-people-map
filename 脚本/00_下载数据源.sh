#!/bin/bash
# 重新下载全部原始数据到 数据源/（这些文件很大，不进 git）
# 用法：bash 脚本/00_下载数据源.sh
set -e
cd "$(dirname "$0")/../数据源"

[ -d theographic ] || git clone --depth 1 https://github.com/robertrouse/theographic-bible-metadata.git theographic
[ -d bibledata ]   || git clone --depth 1 https://github.com/BradyStephenson/bible-data.git bibledata

mkdir -p bible_nouns
[ -f bible_nouns/edges.csv ] || {
  curl -sL -o bible_nouns/bible_nouns.csv.zip "https://networks.skewed.de/net/bible_nouns/files/bible_nouns.csv.zip"
  (cd bible_nouns && unzip -oq bible_nouns.csv.zip)
}

mkdir -p 和合本
[ -d 和合本/usfm ] || {
  curl -sL -o 和合本/cu89s_usfm.zip https://ebible.org/Scriptures/cmn-cu89s_usfm.zip
  unzip -oq 和合本/cu89s_usfm.zip -d 和合本/usfm
}
echo "数据源已就绪"

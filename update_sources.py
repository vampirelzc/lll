#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 venera-configs 仓库重新生成 VeneraNext 漫画源列表 JSON。

流程:
  1. `git clone --depth 1` 拉取上游仓库(单次、无 API 限流)
  2. 读取根目录每个 .js 源文件,解析 class 顶层的 name / key / version
  3. 从 index.json 合并可选的 description
  4. 输出 VeneraNext 可识别的源列表(每个条目指向 jsDelivr 绝对地址)

用法:
    python update_sources.py [--output venera-source-list.json]

依赖: Python 3 标准库 + git。
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = "venera-app/venera-configs"
BRANCH = "main"
GIT_URL = f"https://github.com/{REPO}.git"
CDN_BASE = f"https://cdn.jsdelivr.net/gh/{REPO}@{BRANCH}"
SKIP_FILES = {"_template_.js", "_venera_.js"}
CLONE_RETRIES = 2

# 与 VeneraNext 的 parseCatalog 校验规则一致
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[.\-].+)?$")
KEY_RE = re.compile(r"^\w+$")
# 匹配 class 顶层字段:`    name = "..."`
FIELD_RE = re.compile(r'^\s*(\w+)\s*=\s*"([^"]*)"')


def extract_field(text, field):
    """取 class 顶层 `field = "..."` 的第一个字符串值。"""
    for line in text.splitlines():
        m = FIELD_RE.match(line)
        if m and m.group(1) == field:
            return m.group(2)
    return None


def clone_repo():
    """浅克隆上游仓库到临时目录,返回目录路径。"""
    tmp = tempfile.mkdtemp(prefix="venera-configs-")
    last_error = None
    for attempt in range(1, CLONE_RETRIES + 1):
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", GIT_URL, tmp],
                check=True,
                capture_output=True,
                text=True,
            )
            return tmp
        except subprocess.CalledProcessError as exc:
            last_error = (exc.stderr or exc.stdout or str(exc)).strip()
            print(f"git clone 第 {attempt} 次失败: {last_error}", file=sys.stderr)
        except FileNotFoundError:
            shutil.rmtree(tmp, ignore_errors=True)
            raise RuntimeError("未找到 git,请先安装 git 或把 git 加入 PATH。")
    shutil.rmtree(tmp, ignore_errors=True)
    raise RuntimeError(f"git clone 失败: {last_error}")


def parse_source(path):
    """解析单个 .js 源文件,返回条目 dict;失败抛 ValueError。"""
    with open(path, encoding="utf-8-sig") as fh:
        text = fh.read()
    name = extract_field(text, "name")
    key = extract_field(text, "key")
    version = extract_field(text, "version")
    if not name or not key or not version:
        raise ValueError("缺少 name/key/version")
    if not KEY_RE.match(key):
        raise ValueError(f"key 非法: {key!r}")
    if not VERSION_RE.match(version):
        raise ValueError(f"version 非法: {version!r}")
    return {
        "key": key,
        "name": name,
        "version": version,
        "url": f"{CDN_BASE}/{os.path.basename(path)}",
    }


def load_descriptions(repo_dir):
    """从 index.json 读取 description,按 fileName 索引。"""
    path = os.path.join(repo_dir, "index.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8-sig") as fh:
            index = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(index, list):
        return {}
    return {
        item["fileName"]: item["description"]
        for item in index
        if isinstance(item, dict) and item.get("description")
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="venera-source-list.json")
    args = parser.parse_args()

    repo_dir = clone_repo()
    try:
        files = sorted(
            name
            for name in os.listdir(repo_dir)
            if name.endswith(".js") and name not in SKIP_FILES
        )
        descriptions = load_descriptions(repo_dir)

        entries = []
        skipped = []
        for filename in files:
            try:
                entry = parse_source(os.path.join(repo_dir, filename))
                desc = descriptions.get(filename)
                if desc:
                    entry["description"] = desc
                entries.append(entry)
            except Exception as exc:
                skipped.append(f"{filename}: {exc}")
    finally:
        shutil.rmtree(repo_dir, ignore_errors=True)

    if not entries:
        sys.exit("没有解析到任何有效源,请检查网络后重试。")

    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(entries, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    print(f"已生成 {args.output}:{len(entries)} 个源")
    if skipped:
        print("跳过以下无效条目:", file=sys.stderr)
        for msg in skipped:
            print("  -", msg, file=sys.stderr)


if __name__ == "__main__":
    main()

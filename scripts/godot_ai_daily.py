#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Godot AI 每日文章自动化脚本。

子命令：
  prepare   校验 GitHub 凭证、同步仓库，输出去重所需的索引与已有文章信息
  readme    仅根据 INDEX.md 重建 README.md，提交并推送
  publish   归档文章 → 更新 INDEX.md → 重建 README.md → 提交 → 推送

凭证优先级：
  1) 环境变量 GH_TOKEN / GITHUB_TOKEN（推荐，跨容器有效）
  2) GODOT_AI_PAT_FILE 指向的文件
  3) 已登录的 gh CLI（gh auth status 成功）

用法：
  python3 scripts/godot_ai_daily.py prepare
  python3 scripts/godot_ai_daily.py publish \
      --date 2026-11-13 \
      --title "标题" \
      --keywords "boids, flocking, 群体行为" \
      --sources "https://a, https://b" \
      --slug godot-boids-flocking
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import pathlib
import shutil
import subprocess
import sys

REPO_URL = "https://github.com/whpwwy/GotdotAIStudy.git"
DEFAULT_DIR = pathlib.Path("/tmp/GotdotAIStudy")
REPO_WEB = "https://github.com/whpwwy/GotdotAIStudy"
AUTHOR_NAME = "whpwwy"
AUTHOR_EMAIL = "whpwwy@users.noreply.github.com"

README_HEADER = """# Godot AI 学习文章

每天自动生成一篇 **Godot AI 编程** 学习文章，并归档到本仓库。

- 文章目录：[`articles/`](articles/)
- 去重索引：[`INDEX.md`](INDEX.md)
- 自动化脚本：[`scripts/godot_ai_daily.py`](scripts/godot_ai_daily.py)

选题覆盖方向：行为树 / 状态机、寻路（NavigationAgent）、群体行为（Boids、Flocking）、
程序化生成（PCG）、强化学习 / 机器学习插件、LLM 与生成式 AI 集成、敌人 AI 等。
每次选题都会与历史文章做关键词、来源 URL、核心内容三重去重。

"""


def run(cmd, cwd=None, check=True, capture=True):
    """执行命令，返回 CompletedProcess。"""
    res = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=capture,
        text=True,
    )
    if check and res.returncode != 0:
        sys.stderr.write(f"[FAIL] {' '.join(cmd)}\n{res.stdout}\n{res.stderr}\n")
        raise SystemExit(res.returncode)
    return res


def repo_dir(args) -> pathlib.Path:
    return pathlib.Path(args.repo_dir).expanduser()


# ---------------------------------------------------------------- 凭证


def resolve_token() -> str | None:
    for key in ("GH_TOKEN", "GITHUB_TOKEN"):
        val = os.environ.get(key)
        if val and val.strip():
            return val.strip()
    pat_file = os.environ.get("GODOT_AI_PAT_FILE")
    if pat_file and pathlib.Path(pat_file).exists():
        val = pathlib.Path(pat_file).read_text(encoding="utf-8").strip()
        if val:
            return val
    return None


def ensure_auth() -> str:
    """配置 git 凭证，返回使用的模式名。"""
    token = resolve_token()
    if token:
        helper_key = "credential.https://github.com.helper"
        run(["git", "config", "--global", "--unset-all", helper_key], check=False)
        run(
            [
                "git",
                "config",
                "--global",
                "--add",
                helper_key,
                '!f() { echo username=x-access-token; echo "password=$GIT_CRED"; }; f',
            ]
        )
        # 用一个私有环境变量承载 token，避免 $GH_TOKEN 在非登录 shell 丢失
        os.environ["GIT_CRED"] = token
        print("[auth] 使用环境变量中的 PAT")
        return "pat-env"

    status = run(["gh", "auth", "status"], check=False)
    if status.returncode == 0:
        run(["gh", "auth", "setup-git"], check=False)
        print("[auth] 使用已登录的 gh CLI")
        return "gh"

    sys.stderr.write(
        "[FAIL] 未找到 GitHub 凭证。请在自动化任务中设置环境变量 GH_TOKEN\n"
        "       （fine-grained PAT，需对 whpwwy/GotdotAIStudy 具备 Contents: Read and write）\n"
    )
    raise SystemExit(2)


def sync_repo(path: pathlib.Path) -> None:
    if (path / ".git").exists():
        run(["git", "fetch", "origin"], cwd=path)
        run(["git", "checkout", "main"], cwd=path)
        run(["git", "reset", "--hard", "origin/main"], cwd=path)
        print(f"[sync] 已更新 {path}")
    else:
        if path.exists():
            shutil.rmtree(path)
        run(["git", "clone", REPO_URL, str(path)])
        print(f"[sync] 已克隆到 {path}")


# ---------------------------------------------------------------- INDEX


def parse_index(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 5:
            continue
        if set(cells[0]) <= set("-: "):  # 分隔行
            continue
        if cells[0] in ("日期", "date"):
            continue
        rows.append(
            {
                "date": cells[0],
                "title": cells[1],
                "keywords": cells[2],
                "sources": cells[3],
                "file": cells[4],
            }
        )
    return rows


def ensure_index(path: pathlib.Path) -> None:
    if path.exists():
        return
    path.write_text(
        "# Godot AI 学习文章索引\n\n"
        "每篇文章发布后在下方表格追加一行，用于去重选题。"
        "选题时须避开已记录的主题关键词和来源 URL。\n\n"
        "| 日期 | 标题 | 主题关键词 | 来源 | 文件 |\n"
        "|---|---|---|---|---|\n",
        encoding="utf-8",
    )


def append_index_row(path: pathlib.Path, row: dict) -> bool:
    ensure_index(path)
    rows = parse_index(path)
    slug = pathlib.PurePosixPath(row["file"]).name
    if any(pathlib.PurePosixPath(r["file"]).name == slug for r in rows):
        print(f"[index] 已存在 {slug}，跳过追加")
        return False
    line = "| {date} | {title} | {keywords} | {sources} | {file} |\n".format(**row)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)
    print(f"[index] 已追加 {slug}")
    return True


# ---------------------------------------------------------------- README


def rebuild_readme(repo: pathlib.Path) -> None:
    index = repo / "INDEX.md"
    rows = parse_index(index)
    articles = sorted(
        (p.name for p in (repo / "articles").glob("*.md")), reverse=True
    ) if (repo / "articles").exists() else []

    lines = [README_HEADER]
    lines.append("## 文章统计\n\n")
    lines.append(f"- 累计文章：**{len(rows)}** 篇\n")
    if rows:
        latest = max(r["date"] for r in rows)
        lines.append(f"- 最新更新：**{latest}**\n")
    if articles:
        lines.append(f"- 文章文件数：**{len(articles)}** 个\n")
    lines.append("\n## 最新文章\n\n")
    if rows:
        lines.append("| 日期 | 标题 | 主题关键词 | 文件 |\n")
        lines.append("|---|---|---|---|\n")
        for r in sorted(rows, key=lambda x: x["date"], reverse=True):
            lines.append(
                f"| {r['date']} | {r['title']} | {r['keywords']} | {r['file']} |\n"
            )
    else:
        lines.append("_暂无文章_\n")

    lines.append(
        "\n## 自动化说明\n\n"
        "每日定时任务执行 `scripts/godot_ai_daily.py`：\n\n"
        "1. `prepare` —— 校验凭证、同步仓库、输出去重所需的历史索引；\n"
        "2. 选题去重 —— 关键词、来源 URL、核心内容三重比对，重复则换方向重新检索；\n"
        "3. `publish` —— 归档文章到 `articles/YYYY-MM-DD-slug.md`、追加 `INDEX.md`、"
        "**重建本 README**、提交并推送到 `main`。\n\n"
        "> 本 README 由脚本根据 `INDEX.md` 自动生成，请勿手动编辑。\n"
    )
    (repo / "README.md").write_text("".join(lines), encoding="utf-8")
    print(f"[readme] 已重建，共 {len(rows)} 篇")


# ---------------------------------------------------------------- 提交


def commit_and_push(repo: pathlib.Path, message: str, dry_run: bool) -> str:
    run(["git", "add", "-A"], cwd=repo)
    diff = run(["git", "status", "--porcelain"], cwd=repo)
    if not diff.stdout.strip():
        print("[git] 无变更，跳过提交")
        return ""
    if dry_run:
        print("[git] dry-run，以下为待提交内容：")
        print(diff.stdout.rstrip())
        return ""

    run(
        [
            "git",
            "-c", f"user.name={AUTHOR_NAME}",
            "-c", f"user.email={AUTHOR_EMAIL}",
            "commit",
            "-m", message,
        ],
        cwd=repo,
    )
    run(["git", "push", "origin", "main"], cwd=repo)
    sha = run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
    print(f"[git] 已推送 {sha}")
    print(f"[git] {REPO_WEB}/commit/{sha}")
    return sha


# ---------------------------------------------------------------- 子命令


def cmd_prepare(args) -> None:
    mode = ensure_auth()
    path = repo_dir(args)
    sync_repo(path)

    index = path / "INDEX.md"
    rows = parse_index(index)
    files = sorted(p.name for p in (path / "articles").glob("*.md")) if (path / "articles").exists() else []

    print("\n=== 仓库状态 ===")
    print(f"路径: {path}")
    print(f"凭证模式: {mode}")
    print(f"INDEX 条目: {len(rows)}")

    print("\n=== 已覆盖主题关键词 ===")
    print("; ".join(r["keywords"] for r in rows) if rows else "(无)")

    print("\n=== 已使用来源 URL ===")
    for r in rows:
        print(f"- {r['date']}: {r['sources']}")

    print("\n=== articles/ 已有文件 ===")
    for f in files:
        print(f"- {f}")

    print("\n=== 索引明细 ===")
    for r in rows:
        print(f"- {r['date']} | {r['title']} | {r['file']}")


def cmd_readme(args) -> None:
    ensure_auth()
    path = repo_dir(args)
    sync_repo(path)
    rebuild_readme(path)
    commit_and_push(path, "Update README", args.dry_run)


def cmd_publish(args) -> None:
    ensure_auth()
    path = repo_dir(args)
    sync_repo(path)

    articles = path / "articles"
    articles.mkdir(exist_ok=True)
    target = articles / f"{args.date}-{args.slug}.md"

    if args.file:
        src = pathlib.Path(args.file).expanduser()
        if not src.exists():
            raise SystemExit(f"源文件不存在: {src}")
        if src.resolve() != target.resolve():
            shutil.copyfile(src, target)
            print(f"[publish] 已归档到 {target}")
    elif not target.exists():
        raise SystemExit(f"未找到文章文件，且未提供 --file: {target}")

    if not target.exists():
        raise SystemExit(f"文章文件缺失: {target}")

    row = {
        "date": args.date,
        "title": args.title.replace("|", "\\|"),
        "keywords": args.keywords.replace("|", "\\|"),
        "sources": args.sources.replace("|", "\\|"),
        "file": f"articles/{target.name}",
    }
    append_index_row(path / "INDEX.md", row)
    rebuild_readme(path)
    commit_and_push(path, f"Add daily article: {args.title}", args.dry_run)


def main() -> None:
    parser = argparse.ArgumentParser(description="Godot AI 每日文章自动化")
    parser.add_argument("--repo-dir", default=str(DEFAULT_DIR), help="本地仓库路径")
    parser.add_argument("--dry-run", action="store_true", help="不提交不推送")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("prepare", help="校验凭证并同步仓库")
    sub.add_parser("readme", help="重建 README 并推送")

    p = sub.add_parser("publish", help="归档文章并推送")
    p.add_argument("--date", required=True, help="YYYY-MM-DD")
    p.add_argument("--title", required=True)
    p.add_argument("--keywords", required=True)
    p.add_argument("--sources", required=True)
    p.add_argument("--slug", required=True, help="英文短名，如 godot-boids-flocking")
    p.add_argument("--file", help="待归档的 markdown 源文件路径")

    args = parser.parse_args()
    if args.command == "prepare":
        cmd_prepare(args)
    elif args.command == "readme":
        cmd_readme(args)
    elif args.command == "publish":
        cmd_publish(args)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
import os
import sys
import json
import re
import subprocess
import shutil
from pathlib import Path
from typing import List, Tuple, Set

APP_NAME = "Dead Switch"
REPO_NAME = "Dead-Switch"
MAX_BATCH_BYTES = 40 * 1024 * 1024
MAX_FILE_BYTES = 40 * 1024 * 1024

CONFIG_PATH = Path.home() / ".dead_switch_settings.json"

README_TEXT = """# Dead Switch (Dead Man's Switch)
(omitted here for brevity - keep your original README_TEXT)
"""

def resolve_downloads_dir() -> Path:
    # Linux default
    home = Path.home()
    candidates = [
        home / "Downloads",
        home / "downloads",
    ]
    for c in candidates:
        if c.exists():
            return c
    # fallback
    return home / "Downloads"

DOWNLOADS_DIR = resolve_downloads_dir()
LOCAL_DIR = DOWNLOADS_DIR / APP_NAME

def run_rc(cmd, cwd=None, capture=False):
    p = subprocess.run(
        cmd, cwd=cwd, text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None
    )
    out = (p.stdout or "").strip() if capture else ""
    return p.returncode, out

def run(cmd, cwd=None, check=True, capture=False):
    try:
        if capture:
            p = subprocess.run(cmd, cwd=cwd, check=check, text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            return p.stdout.strip()
        subprocess.run(cmd, cwd=cwd, check=check)
        return ""
    except subprocess.CalledProcessError as e:
        msg = ""
        if getattr(e, "stdout", None):
            msg = "\n" + e.stdout
        print(f"\n[!] Command failed: {' '.join(cmd)}{msg}")
        if check:
            raise
        return msg.strip()

def which(bin_name: str) -> bool:
    return shutil.which(bin_name) is not None

def ensure_bins():
    missing = []
    for b in ("git", "gh"):
        if not which(b):
            missing.append(b)
    if missing:
        print(f"[!] Missing binaries: {', '.join(missing)}")
        print("Install them, e.g.:")
        print("  Ubuntu/Debian: sudo apt install git gh")
        print("  Fedora:        sudo dnf install git gh")
        print("  Arch:          sudo pacman -S git github-cli")
        sys.exit(1)

def ensure_folder():
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)

def load_settings() -> dict:
    defaults = {"visibility": "public"}
    try:
        if CONFIG_PATH.exists():
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                defaults.update(data)
    except Exception:
        pass
    vis = str(defaults.get("visibility", "public")).lower().strip()
    if vis not in ("public", "private"):
        vis = "public"
    defaults["visibility"] = vis
    return defaults

def save_settings(settings: dict):
    try:
        CONFIG_PATH.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass

def get_visibility() -> str:
    return load_settings().get("visibility", "public")

def set_visibility(vis: str):
    vis = (vis or "").lower().strip()
    if vis not in ("public", "private"):
        print("[!] Invalid visibility. Use public/private.")
        return
    s = load_settings()
    s["visibility"] = vis
    save_settings(s)
    print(f"[✓] Saved repository visibility preference: {vis.upper()}")

def ensure_logged_in():
    print("[*] Checking GitHub login status...")
    ok = subprocess.run(["gh", "auth", "status"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    if ok:
        print("[*] GitHub: already logged in.")
        return
    print("\n[!] You are not logged in to GitHub CLI (gh).")
    print("    Running: gh auth login --web\n")
    run(["gh", "auth", "login", "--hostname", "github.com", "--git-protocol", "https", "--web"], check=False)

    ok = subprocess.run(["gh", "auth", "status"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    if not ok:
        print("\n[!] Login not completed. Run manually:")
        print("    gh auth login --hostname github.com --git-protocol https --web")
        sys.exit(1)

def get_token_scopes() -> set:
    out = run(["gh", "auth", "status", "-h", "github.com"], capture=True, check=False)
    scopes = set()
    if out:
        for line in out.splitlines():
            if "Token scopes:" in line:
                part = line.split("Token scopes:", 1)[1]
                found = re.findall(r"[A-Za-z0-9:_-]+", part)
                scopes.update(found)
                break
    return scopes

def ensure_scopes(required_scopes):
    scopes = get_token_scopes()
    missing = [sc for sc in required_scopes if sc not in scopes]
    if not missing:
        return
    print(f"[*] Missing GitHub token scopes: {', '.join(missing)}")
    print("[*] Requesting additional permissions...")
    args = ["gh", "auth", "refresh", "-h", "github.com"]
    for sc in missing:
        args += ["-s", sc]
    run(args, check=False)

def ensure_repo_scope():
    ensure_scopes(["repo"])

def gh_user():
    out = run(["gh", "api", "user", "--jq", ".login"], capture=True, check=False)
    return (out or "").strip()

def repo_exists(owner):
    rc = subprocess.run(["gh", "repo", "view", f"{owner}/{REPO_NAME}"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
    return rc == 0

def get_default_branch(owner):
    out = run(["gh", "api", f"repos/{owner}/{REPO_NAME}", "--jq", ".default_branch"], capture=True, check=False)
    return (out or "main").strip() or "main"

def ensure_repo_created(owner, visibility: str):
    visibility = (visibility or "public").lower().strip()
    if visibility not in ("public", "private"):
        visibility = "public"

    ensure_repo_scope()

    if not repo_exists(owner):
        print(f"[*] Creating {visibility.upper()} repo: {owner}/{REPO_NAME}")
        private_flag = "true" if visibility == "private" else "false"
        run(["gh", "api", "-X", "POST", "user/repos",
             "-f", f"name={REPO_NAME}",
             "-f", f"private={private_flag}",
             "-f", "auto_init=false"], check=True)
        print("[*] Repo created.")
    else:
        print(f"[*] Repo exists: {owner}/{REPO_NAME}")

    print(f"[*] Ensuring repository visibility is {visibility.upper()}...")
    private_flag = "true" if visibility == "private" else "false"
    run(["gh", "api", "-X", "PATCH", f"repos/{owner}/{REPO_NAME}", "-f", f"private={private_flag}"], check=False)
    run(["gh", "repo", "edit", f"{owner}/{REPO_NAME}", "--visibility", visibility, "--accept-visibility-change-consequences"], check=False)

def init_or_use_git_repo():
    if not (LOCAL_DIR / ".git").exists():
        print("[*] Initializing local git repo...")
        run(["git", "init"], cwd=str(LOCAL_DIR))
        run(["git", "config", "user.name", "dead-switch"], cwd=str(LOCAL_DIR), check=False)
        run(["git", "config", "user.email", "dead-switch@localhost"], cwd=str(LOCAL_DIR), check=False)

def set_remote(owner):
    remote_url = f"https://github.com/{owner}/{REPO_NAME}.git"
    remotes = run(["git", "remote"], cwd=str(LOCAL_DIR), capture=True, check=False)
    if "origin" in remotes.split():
        run(["git", "remote", "set-url", "origin", remote_url], cwd=str(LOCAL_DIR), check=False)
    else:
        run(["git", "remote", "add", "origin", remote_url], cwd=str(LOCAL_DIR), check=False)

def ensure_gitignore():
    gi = LOCAL_DIR / ".gitignore"
    if not gi.exists():
        gi.write_text(".DS_Store\nThumbs.db\n*.log\n__pycache__/\n*.pyc\n", encoding="utf-8")

def ensure_readme():
    rm = LOCAL_DIR / "README.md"
    rm.write_text(README_TEXT, encoding="utf-8")
    return rm

def current_branch():
    b = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(LOCAL_DIR), capture=True, check=False)
    return "main" if not b or b == "HEAD" else b

def ensure_main_branch():
    b = current_branch()
    if b == "master":
        run(["git", "branch", "-M", "main"], cwd=str(LOCAL_DIR), check=False)

def staged_has_changes() -> bool:
    out = run(["git", "diff", "--cached", "--name-only"], cwd=str(LOCAL_DIR), capture=True, check=False)
    return bool((out or "").strip())

def commit_staged(message: str) -> bool:
    if not staged_has_changes():
        print("[*] Nothing staged to commit.")
        return False
    rc, out = run_rc(["git", "commit", "-m", message], cwd=str(LOCAL_DIR), capture=True)
    if rc != 0:
        print("[!] Commit failed.")
        if out:
            print(out)
        return False
    return True

def push_current() -> bool:
    ensure_main_branch()
    head = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(LOCAL_DIR), capture=True, check=False)
    if not head or head == "HEAD":
        run(["git", "checkout", "-B", "main"], cwd=str(LOCAL_DIR), check=False)
        head = "main"
    print("[*] Pushing to GitHub...")
    rc, out = run_rc(["git", "push", "-u", "origin", head], cwd=str(LOCAL_DIR), capture=True)
    if rc != 0:
        print("[!] Push failed.")
        if out:
            print(out)
        return False
    return True

def list_local_files() -> List[Tuple[str, int]]:
    items: List[Tuple[str, int]] = []
    for p in LOCAL_DIR.rglob("*"):
        if p.is_dir():
            continue
        if ".git" in p.parts:
            continue
        try:
            size = p.stat().st_size
        except OSError:
            continue
        rel = p.relative_to(LOCAL_DIR).as_posix()
        items.append((rel, size))
    items.sort(key=lambda x: x[0])
    return items

def fetch_remote_paths(owner) -> Set[str]:
    if not repo_exists(owner):
        return set()
    default_branch = get_default_branch(owner)
    out = run(["gh", "api", f"repos/{owner}/{REPO_NAME}/git/trees/{default_branch}", "-f", "recursive=1"],
              capture=True, check=False)
    if not out:
        return set()
    try:
        data = json.loads(out)
        paths = set()
        for item in data.get("tree", []):
            if item.get("type") == "blob" and "path" in item:
                paths.add(item["path"])
        return paths
    except Exception:
        return set()

def make_batches(candidates: List[Tuple[str, int]], max_bytes: int) -> List[List[Tuple[str, int]]]:
    batches: List[List[Tuple[str, int]]] = []
    current: List[Tuple[str, int]] = []
    total = 0
    for rel, size in candidates:
        if size > MAX_FILE_BYTES:
            continue
        if not current:
            current = [(rel, size)]
            total = size
            continue
        if total + size <= max_bytes:
            current.append((rel, size))
            total += size
        else:
            batches.append(current)
            current = [(rel, size)]
            total = size
    if current:
        batches.append(current)
    return batches

def report_skips(skipped: List[Tuple[str, int]]):
    if not skipped:
        return
    print("\n[!] Skipped files (too large):")
    for rel, size in skipped:
        mb = size / (1024 * 1024)
        print(f"    - {rel} ({mb:.2f} MB)")
    print("")

def stage_paths(paths: List[str]):
    for rel in paths:
        run(["git", "add", "--", rel], cwd=str(LOCAL_DIR), check=False)

def create_switch_only_new():
    print("\n=== Create Switch (Only New Files) ===")
    ensure_folder()
    ensure_bins()
    ensure_logged_in()
    ensure_repo_scope()

    owner = gh_user()
    if not owner:
        print("[!] Could not detect GitHub username.")
        return

    ensure_repo_created(owner, get_visibility())
    init_or_use_git_repo()
    set_remote(owner)
    ensure_gitignore()
    ensure_readme()

    run(["git", "fetch", "origin"], cwd=str(LOCAL_DIR), check=False)

    remote_paths = fetch_remote_paths(owner)
    local_items = list_local_files()
    print(f"[*] Local files detected: {len(local_items)}")
    if not local_items:
        print("[!] Folder is empty. Put files in it and try again.")
        return

    skipped_large = [(rel, size) for rel, size in local_items if size > MAX_FILE_BYTES]
    report_skips(skipped_large)

    candidates = []
    for rel, size in local_items:
        if size > MAX_FILE_BYTES:
            continue
        if rel == "README.md":
            candidates.append((rel, size))
            continue
        if rel not in remote_paths:
            candidates.append((rel, size))

    if not candidates:
        print("[*] No new files to upload.")
        print(f"[✓] Repo: https://github.com/{owner}/{REPO_NAME}")
        return

    batches = make_batches(candidates, MAX_BATCH_BYTES)
    print(f"[*] Need to upload {len(candidates)} file(s) in {len(batches)} batch(es).")

    uploaded = 0
    for i, batch in enumerate(batches, start=1):
        run(["git", "reset"], cwd=str(LOCAL_DIR), check=False)
        batch_paths = [rel for rel, _ in batch]
        batch_bytes = sum(size for _, size in batch)
        print(f"\n[*] Batch {i}/{len(batches)}: {len(batch_paths)} file(s), {batch_bytes/(1024*1024):.2f} MB")
        stage_paths(batch_paths)
        if not commit_staged(f"Add new files batch {i}/{len(batches)} (<=40MB)"):
            print("[!] Stopping because commit failed.")
            return
        if not push_current():
            print("[!] Stopping because push failed.")
            return
        uploaded += len(batch_paths)
        for rel in batch_paths:
            remote_paths.add(rel)

    print(f"\n[✓] Done. Uploaded {uploaded} file(s). Repo: https://github.com/{owner}/{REPO_NAME}")

def overwrite_repository_batched():
    print("\n=== Overwrite Repository (Full Sync, Batched) ===")
    ensure_folder()
    ensure_bins()
    ensure_logged_in()
    ensure_repo_scope()

    owner = gh_user()
    if not owner:
        print("[!] Could not detect GitHub username.")
        return

    ensure_repo_created(owner, get_visibility())
    init_or_use_git_repo()
    set_remote(owner)
    ensure_gitignore()
    ensure_readme()

    run(["git", "fetch", "origin"], cwd=str(LOCAL_DIR), check=False)

    local_items = list_local_files()
    print(f"[*] Local files detected: {len(local_items)}")
    if not local_items:
        print("[!] Folder is empty.")
        return

    skipped_large = [(rel, size) for rel, size in local_items if size > MAX_FILE_BYTES]
    report_skips(skipped_large)

    candidates = [(rel, size) for rel, size in local_items if size <= MAX_FILE_BYTES]
    batches = make_batches(candidates, MAX_BATCH_BYTES)
    print(f"[*] Will sync {len(candidates)} file(s) in {len(batches)} batch(es).")

    committed_any = False
    for i, batch in enumerate(batches, start=1):
        run(["git", "reset"], cwd=str(LOCAL_DIR), check=False)
        batch_paths = [rel for rel, _ in batch]
        batch_bytes = sum(size for _, size in batch)
        print(f"\n[*] Batch {i}/{len(batches)}: {len(batch_paths)} file(s), {batch_bytes/(1024*1024):.2f} MB")
        stage_paths(batch_paths)
        if commit_staged(f"Overwrite/sync batch {i}/{len(batches)} (<=40MB)"):
            committed_any = True
            if not push_current():
                print("[!] Stopping because push failed.")
                return
        else:
            print("[*] Nothing changed in this batch.")

    if committed_any:
        print(f"\n[✓] Done. Repo: https://github.com/{owner}/{REPO_NAME}")
    else:
        print("\n[*] No changes detected to upload.")

def ensure_delete_scope():
    print("[*] Ensuring delete permissions (delete_repo)...")
    ensure_scopes(["delete_repo", "repo"])

def wipe_repo_files(owner):
    print("[*] Wiping repository files (empty commit)...")
    init_or_use_git_repo()
    set_remote(owner)
    run(["git", "fetch", "origin"], cwd=str(LOCAL_DIR), check=False)

    for branch in ("main", "master"):
        rc = subprocess.run(["git", "checkout", branch], cwd=str(LOCAL_DIR),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
        if rc == 0:
            break
    else:
        run(["git", "checkout", "-B", "main"], cwd=str(LOCAL_DIR), check=False)

    run(["git", "rm", "-r", "--ignore-unmatch", "."], cwd=str(LOCAL_DIR), check=False)
    (LOCAL_DIR / "README.md").write_text(README_TEXT, encoding="utf-8")
    (LOCAL_DIR / ".gitkeep").write_text("Repo wiped by dead_switch_linux.py\n", encoding="utf-8")

    run(["git", "add", "-A"], cwd=str(LOCAL_DIR), check=False)
    commit_staged("Wipe repository contents")
    run(["git", "push", "origin", "HEAD", "--force"], cwd=str(LOCAL_DIR), check=False)
    print("[*] Repo contents wiped (best effort).")

def delete_repo(owner):
    print(f"[*] Deleting repo: {owner}/{REPO_NAME}")
    ensure_delete_scope()
    rc = subprocess.run(["gh", "repo", "delete", f"{owner}/{REPO_NAME}", "--yes"],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True).returncode
    if rc != 0:
        run(["gh", "api", "-X", "DELETE", f"repos/{owner}/{REPO_NAME}"], check=False)

def kill_switch():
    print("\n=== Kill Switch (Wipe + Delete Repo) ===")
    ensure_folder()
    ensure_bins()
    ensure_logged_in()
    ensure_repo_scope()

    owner = gh_user()
    if not owner:
        print("[!] Could not detect GitHub username.")
        return
    if not repo_exists(owner):
        print(f"[*] Repo does not exist: {owner}/{REPO_NAME}")
        return
    try:
        wipe_repo_files(owner)
    except Exception:
        print("[!] Could not fully wipe files (continuing to delete repo anyway).")
    delete_repo(owner)

def print_header():
    os.system("clear")
    print("===================================")
    print(f" {APP_NAME} (Linux)")
    print("===================================")
    print(f"Local folder: {LOCAL_DIR}")
    print(f"GitHub repo : {REPO_NAME} (preference: {get_visibility().upper()})")
    print("Upload rules:")
    print(" - Each batch push <= 40MB total.")
    print(" - Any single file > 40MB is skipped.")
    print("")

def menu():
    while True:
        print_header()
        print("1) Create Switch (ONLY new files, batched <=40MB)")
        print("2) Overwrite Repository (sync/overwrite, batched <=40MB)")
        print("3) Kill Switch (wipe repo then delete it)")
        print("4) Set Repository Visibility (Public / Private)")
        print("0) Exit")
        choice = input("\nSelect: ").strip()

        if choice == "1":
            create_switch_only_new()
            input("\nPress Enter to continue...")
        elif choice == "2":
            print("\n[!] WARNING: This will OVERWRITE/UPDATE files in the repo (batched).")
            confirm = input("Type OVERWRITE to continue: ").strip()
            if confirm == "OVERWRITE":
                overwrite_repository_batched()
            else:
                print("[*] Cancelled.")
            input("\nPress Enter to continue...")
        elif choice == "3":
            print("\n[!] WARNING: This will WIPE and DELETE your GitHub repo.")
            confirm = input("Type KILL to continue: ").strip()
            if confirm == "KILL":
                kill_switch()
            else:
                print("[*] Cancelled.")
            input("\nPress Enter to continue...")
        elif choice == "4":
            print("\nChoose visibility:")
            print("1) Public")
            print("2) Private")
            v = input("\nSelect: ").strip()
            if v == "1":
                set_visibility("public")
            elif v == "2":
                set_visibility("private")
            else:
                print("[*] Cancelled.")
            input("\nPress Enter to continue...")
        elif choice == "0":
            print("Bye.")
            return
        else:
            print("[!] Invalid choice.")
            input("\nPress Enter to continue...")

if __name__ == "__main__":
    print("Linux Version")
    try:
        menu()
    except KeyboardInterrupt:
        print("\nBye.")
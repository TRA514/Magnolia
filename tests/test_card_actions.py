"""Task 8 — card action backend: accept->apply->receipt->undo + graduate.

The git apply/commit/revert path runs with `git -C task_server.PM_OS_DIR`, so each
test monkeypatches PM_OS_DIR to a throwaway git repo. graduate_card writes through
ladder_lib via an explicit ladder_path so it never touches the real store.
"""
import subprocess


def _git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)


def test_accept_applies_patch_and_spawns_receipt(tasks_root, tmp_path, monkeypatch):
    import task_server, task_lib
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(str(repo), "init")
    _git(str(repo), "config", "user.email", "t@e.com")
    _git(str(repo), "config", "user.name", "t")
    target = repo / "hello.txt"
    target.write_text("hello\n")
    _git(str(repo), "add", "."); _git(str(repo), "commit", "-m", "init")
    patch = repo / "p.patch"
    patch.write_text("--- a/hello.txt\n+++ b/hello.txt\n@@ -1 +1 @@\n-hello\n+hello world\n")
    monkeypatch.setattr(task_server, "PM_OS_DIR", str(repo))
    tid, _ = task_lib.create_task("rec", queue="collab", card_type="recommendation", patch_path="p.patch")
    receipt_id = task_server.apply_recommendation(tid)
    assert (repo / "hello.txt").read_text() == "hello world\n"
    rc = task_lib.read_task(receipt_id)["frontmatter"]
    assert rc["card_type"] == "receipt"
    assert rc.get("revert_commit")


def test_accept_bad_patch_raises(tasks_root, tmp_path, monkeypatch):
    import task_server, task_lib, pytest
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(str(repo), "init")
    _git(str(repo), "config", "user.email", "t@e.com"); _git(str(repo), "config", "user.name", "t")
    (repo / "hello.txt").write_text("hello\n")
    _git(str(repo), "add", "."); _git(str(repo), "commit", "-m", "init")
    (repo / "bad.patch").write_text("--- a/nonexistent.txt\n+++ b/nonexistent.txt\n@@ -1 +1 @@\n-x\n+y\n")
    monkeypatch.setattr(task_server, "PM_OS_DIR", str(repo))
    tid, _ = task_lib.create_task("rec", queue="collab", card_type="recommendation", patch_path="bad.patch")
    with pytest.raises(Exception):
        task_server.apply_recommendation(tid)


def test_undo_reverts_commit(tasks_root, tmp_path, monkeypatch):
    import task_server, task_lib
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(str(repo), "init")
    _git(str(repo), "config", "user.email", "t@e.com"); _git(str(repo), "config", "user.name", "t")
    (repo / "hello.txt").write_text("hello\n")
    _git(str(repo), "add", "."); _git(str(repo), "commit", "-m", "init")
    (repo / "p.patch").write_text("--- a/hello.txt\n+++ b/hello.txt\n@@ -1 +1 @@\n-hello\n+hello world\n")
    monkeypatch.setattr(task_server, "PM_OS_DIR", str(repo))
    tid, _ = task_lib.create_task("rec", queue="collab", card_type="recommendation", patch_path="p.patch")
    receipt_id = task_server.apply_recommendation(tid)
    task_server.undo_receipt(receipt_id)
    assert (repo / "hello.txt").read_text() == "hello\n"  # reverted


def test_graduate_advances_tier(tasks_root, tmp_path):
    import task_server, task_lib, ladder_lib
    p = str(tmp_path / "ladder.json")
    tid, _ = task_lib.create_task("grad", queue="collab", card_type="graduation")
    task_lib.update_task(tid, changes={"grad_task_type": "prd-draft", "grad_proposed_tier": "gated"})
    task_server.graduate_card(tid, ladder_path=p)
    assert ladder_lib.tier_of("prd-draft", path=p) == "gated"

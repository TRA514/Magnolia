import seed_default_crons
import cron_lib


def test_seeds_doctor_cron_once(monkeypatch, tmp_path):
    jobs = []
    monkeypatch.setattr(cron_lib, "list_jobs", lambda: list(jobs))
    monkeypatch.setattr(cron_lib, "create_job",
                        lambda **kw: jobs.append({"name": kw["name"], **kw}) or jobs[-1])
    n1 = seed_default_crons.seed()
    n2 = seed_default_crons.seed()  # idempotent: second run adds nothing
    assert n1 == 1
    assert n2 == 0
    assert any("Doctor" in j["name"] for j in jobs)


def test_doctor_cron_is_monday_9am(monkeypatch):
    captured = {}
    import cron_lib as cl
    monkeypatch.setattr(cl, "list_jobs", lambda: [])
    monkeypatch.setattr(cl, "create_job", lambda **kw: captured.update(kw) or kw)
    seed_default_crons.seed()
    assert captured["cron_expr"] == "0 9 * * 1"  # min hour dom mon dow(Mon=1)


def test_seed_cold_against_real_cron_lib(tmp_path, monkeypatch):
    # Exercises the REAL cron_lib path (no mocks) against an EMPTY tmp dir to
    # simulate a fresh Magnolia clone where _counter / jobs.json don't exist yet.
    # Would have caught the FileNotFoundError crash in _next_cron_id().
    cron_dir = tmp_path / "cron"
    cron_dir.mkdir()  # starts empty: no _counter, no jobs.json
    monkeypatch.setattr(cron_lib, "CRON_DIR", str(cron_dir), raising=True)
    monkeypatch.setattr(cron_lib, "COUNTER_FILE", str(cron_dir / "_counter"), raising=True)
    monkeypatch.setattr(cron_lib, "JOBS_FILE", str(cron_dir / "jobs.json"), raising=True)

    # Cold run must NOT raise FileNotFoundError and must seed exactly 1.
    n = seed_default_crons.seed()
    assert n == 1
    # Idempotent second run adds nothing.
    assert seed_default_crons.seed() == 0
    # The job actually persisted via the real cron_lib.
    jobs = cron_lib.list_jobs()
    assert any("Doctor" in j["name"] for j in jobs)

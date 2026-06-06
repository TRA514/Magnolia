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

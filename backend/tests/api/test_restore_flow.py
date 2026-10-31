"""API tests for the restore check: T1.12, T1.14, T1.15, T1.16 over HTTP."""

OWNER = 3


def test_t1_15_latest_is_not_tested_after_reset(app_h):
    app_h.reset()
    r = app_h.get("/restore/latest")
    assert r.status_code == 200
    assert r.json() == {"id": None, "result": "NOT_TESTED", "simulated_backup": True,
                         "started_at": None, "backup_age_hours": None, "files_total": None,
                         "files_ok": None, "exposed": None, "checks": []}


def test_t1_12_run_stores_and_returns_a_fail(app_h):
    app_h.reset()
    # Reset regenerated the demo backup (db.reset -> demo_backup.make.ensure); run the check.
    r = app_h.post("/restore/run")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["result"] == "FAIL"
    assert body["files_total"] == 50 and body["files_ok"] == 48 and body["exposed"] is True
    by = {c["check"]: c for c in body["checks"]}
    assert by["integrity"]["failed_files"] == ["invoices/invoice_017.txt", "letters/letter_032.txt"]
    # The run is stored and is what /restore/latest now reports.
    latest = app_h.get("/restore/latest").json()
    assert latest["id"] == body["id"] and latest["result"] == "FAIL"
    assert app_h.ctx.db.one("SELECT result FROM restore_runs")["result"] == "FAIL"


def test_t1_14_the_run_leaves_the_backup_folder_untouched(app_h):
    app_h.reset()
    backup_dir = app_h.ctx.config.restore_backup_dir
    before = sorted(p.name for p in backup_dir.iterdir())
    app_h.post("/restore/run")
    assert sorted(p.name for p in backup_dir.iterdir()) == before
    # The sandbox holds the copy the check hashed.
    sandbox = app_h.ctx.config.restore_sandbox_dir
    assert (sandbox / "backup_meta.json").is_file()


def test_t1_16_restore_check_button_appears_after_the_host_answer(app_h):
    app_h.reset()
    created = app_h.post("/drills", json={"scenario_id": "ransomware_clinic",
                                           "host_staff_id": OWNER, "source_alert_id": None}).json()
    code, host = created["code"], created["player_id"]
    def advance(status):
        r = app_h.post(f"/drills/{code}/advance", json={"player_id": host})
        assert r.status_code == 200 and r.json()["status"] == status, r.text
    def answer(pid, step, opt):
        r = app_h.post(f"/drills/{code}/answers", json={"player_id": pid, "step_id": step, "option_id": opt})
        assert r.status_code == 200, r.text

    advance("open")                                   # s1
    app_h.post(f"/drills/{code}/join", json={"staff_id": 1})
    advance("review"); advance("open")                 # s2
    advance("review"); advance("open")                 # s3
    answer(host, "s3", "b")                            # the trigger option
    v = app_h.get(f"/drills/{code}", params={"player_id": host}).json()
    assert v["restore_check_available"] is True
    # A wrong answer at s3 (no trigger) leaves it off.
    advance("review"); advance("open")                 # s4
    assert app_h.get(f"/drills/{code}", params={"player_id": host}).json()["restore_check_available"] is False

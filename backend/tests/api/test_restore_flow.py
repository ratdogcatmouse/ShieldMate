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


def test_a_file_missing_from_the_backup_fails_integrity_instead_of_crashing(app_h):
    app_h.reset()
    (app_h.config.restore_backup_dir / "invoices" / "invoice_001.txt").unlink()
    r = app_h.post("/restore/run")
    assert r.status_code == 200, r.text
    integrity = next(c for c in r.json()["checks"] if c["check"] == "integrity")
    assert r.json()["files_ok"] == 47
    assert "invoices/invoice_001.txt" in integrity["failed_files"]
    app_h.reset()                       # put the shared demo backup back


def test_restore_check_works_on_a_fresh_start_before_any_reset(make_app):
    """The demo backup is built at start-up, so a clone that never pressed Reset doesn't 500."""
    import shutil
    from demo_backup import make
    shutil.rmtree(make.BACKUP_DIR, ignore_errors=True)
    shutil.rmtree(make.ORIGINALS_DIR, ignore_errors=True)
    h = make_app()                       # create_app -> _ensure_demo_backup
    r = h.post("/restore/run")
    assert r.status_code == 200, r.text
    assert r.json()["result"] == "FAIL" and r.json()["files_total"] == 50


def test_verify_route_runs_the_recovery_drill(app_h):
    app_h.reset()
    r = app_h.post("/restore/verify")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "verify"
    # The demo layout plants three live vulnerabilities; the patch closes all of them, but the
    # backup (a snapshot of the compromised directory) still carries those same three - so the
    # compare fails and the story ends FAIL (restoring that backup would bring the holes back).
    assert [c["check"] for c in body["checks"]] == ["update", "compare"]
    assert body["updated_vuln_files"] == 0 and body["backup_vuln_files"] == 3
    assert body["same_vulnerabilities"] is True and body["result"] == "FAIL"
    # Stored with its own kind, not the plain check's.
    assert app_h.ctx.db.one("SELECT kind FROM restore_runs WHERE id = ?", (body["id"],))["kind"] == "verify"


def test_latest_ignores_verify_runs(app_h):
    app_h.reset()
    app_h.post("/restore/verify")
    latest = app_h.get("/restore/latest").json()
    # No check has run yet: the placeholder, even though a verify run is stored.
    assert latest == {"id": None, "result": "NOT_TESTED", "simulated_backup": True,
                      "started_at": None, "backup_age_hours": None, "files_total": None,
                      "files_ok": None, "exposed": None, "checks": []}
    app_h.post("/restore/run")
    assert app_h.get("/restore/latest").json()["result"] in ("PASS", "FAIL")

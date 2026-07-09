from app import db


def test_company_policy_snapshot_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "contractsense.db")
    db.init_db()

    policy_id = db.save_company_policy_snapshot({
        "source_url": "https://1drv.ms/w/s!policy",
        "download_url": "https://onedrive.live.com/download?resid=policy",
        "version": 3,
        "content_text": "Employees must obtain approval before disclosing personal data.",
        "checksum": "abc123",
        "etag": "v3",
        "last_modified": "Thu, 09 Jul 2026 10:00:00 GMT",
    })

    active_policy = db.get_active_company_policy()

    assert policy_id > 0
    assert active_policy is not None
    assert active_policy["version"] == 3
    assert "disclosing personal data" in active_policy["content_text"]


def test_new_company_policy_snapshot_replaces_active_policy(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "contractsense.db")
    db.init_db()

    db.save_company_policy_snapshot({
        "source_url": "https://example.com/old-policy.txt",
        "download_url": "https://example.com/old-policy.txt",
        "version": 1,
        "content_text": "Old policy text",
    })
    db.save_company_policy_snapshot({
        "source_url": "https://example.com/new-policy.txt",
        "download_url": "https://example.com/new-policy.txt",
        "version": 2,
        "content_text": "New policy text",
    })

    active_policy = db.get_active_company_policy()

    assert active_policy is not None
    assert active_policy["version"] == 2
    assert active_policy["content_text"] == "New policy text"

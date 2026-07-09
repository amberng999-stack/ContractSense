from app.services.sharepoint_policy_sync import (
    ACTIVE_POLICY_FILENAME,
    FetchedResource,
    _candidate_download_urls,
    link_company_policy_source,
    read_company_policy_source_status,
    sync_company_policy_source,
)


def test_link_company_policy_source_saves_active_policy(tmp_path):
    resource = FetchedResource(
        url="https://contoso.sharepoint.com/sites/legal/policy.txt?download=1",
        content=b"Company leave policy requires manager approval.",
        content_type="text/plain",
        etag="v1",
        last_modified="Tue, 07 Jul 2026 12:00:00 GMT",
    )

    manifest = link_company_policy_source(
        tmp_path,
        source_url="https://contoso.sharepoint.com/sites/legal/policy.txt",
        fetch_resource=lambda _url: resource,
    )

    assert manifest["sync_status"] == "up_to_date"
    assert manifest["version"] == 1
    assert (tmp_path / ACTIVE_POLICY_FILENAME).exists()
    assert "Company leave policy" in (tmp_path / ACTIVE_POLICY_FILENAME).read_text(encoding="utf-8")


def test_sync_company_policy_source_detects_unchanged_file(tmp_path, monkeypatch):
    resource = FetchedResource(
        url="https://contoso.sharepoint.com/policy.txt?download=1",
        content=b"Policy text",
        content_type="text/plain",
        etag="same",
        last_modified="Tue, 07 Jul 2026 12:00:00 GMT",
    )
    monkeypatch.setattr(
        "app.services.sharepoint_policy_sync._store_active_policy_in_database",
        lambda **_record: 1,
    )
    monkeypatch.setattr(
        "app.services.sharepoint_policy_sync._active_policy_exists_in_database",
        lambda: True,
    )

    link_company_policy_source(
        tmp_path,
        source_url="https://contoso.sharepoint.com/policy.txt",
        fetch_resource=lambda _url: resource,
    )
    manifest = sync_company_policy_source(tmp_path, fetch_resource=lambda _url: resource)

    assert manifest["sync_status"] == "up_to_date"
    assert manifest["message"] == "Company policy is already up to date."
    assert manifest["version"] == 1


def test_sync_company_policy_source_stores_extracted_text(tmp_path, monkeypatch):
    stored_records = []
    resource = FetchedResource(
        url="https://onedrive.live.com/download?resid=policy",
        content=b"Company policy requires prior approval before sharing personal data.",
        content_type="text/plain",
        etag="v1",
        last_modified="Thu, 09 Jul 2026 10:00:00 GMT",
    )

    monkeypatch.setattr(
        "app.services.sharepoint_policy_sync._store_active_policy_in_database",
        lambda **record: stored_records.append(record) or 42,
    )
    monkeypatch.setattr(
        "app.services.sharepoint_policy_sync._active_policy_exists_in_database",
        lambda: False,
    )

    manifest = link_company_policy_source(
        tmp_path,
        source_url="https://1drv.ms/w/s!policy",
        fetch_resource=lambda _url: resource,
    )

    assert manifest["policy_db_id"] == 42
    assert stored_records
    assert stored_records[0]["source_url"] == "https://1drv.ms/w/s!policy"
    assert "prior approval" in stored_records[0]["content_text"]


def test_policy_source_status_handles_not_linked(tmp_path):
    status = read_company_policy_source_status(tmp_path)
    assert status["sync_status"] == "not_linked"


def test_onedrive_live_link_generates_download_candidates():
    url = "https://onedrive.live.com/edit.aspx?resid=ABC123%21123&authkey=!secret&cid=ABC123"

    candidates = _candidate_download_urls(url)

    assert candidates[0].startswith("https://onedrive.live.com/edit.aspx?")
    assert "download=1" in candidates[0]
    assert "https://onedrive.live.com/download?resid=ABC123%21123&authkey=%21secret" in candidates
    assert "https://onedrive.live.com/download.aspx?resid=ABC123%21123&authkey=%21secret" in candidates


def test_short_onedrive_link_keeps_download_candidate():
    url = "https://1drv.ms/w/s!abcde12345"

    candidates = _candidate_download_urls(url)

    assert candidates[0] == "https://1drv.ms/w/s!abcde12345?download=1"
    assert url in candidates

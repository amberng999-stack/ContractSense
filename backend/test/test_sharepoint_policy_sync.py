from app.services.sharepoint_policy_sync import (
    ACTIVE_POLICY_FILENAME,
    FetchedResource,
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


def test_sync_company_policy_source_detects_unchanged_file(tmp_path):
    resource = FetchedResource(
        url="https://contoso.sharepoint.com/policy.txt?download=1",
        content=b"Policy text",
        content_type="text/plain",
        etag="same",
        last_modified="Tue, 07 Jul 2026 12:00:00 GMT",
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


def test_policy_source_status_handles_not_linked(tmp_path):
    status = read_company_policy_source_status(tmp_path)
    assert status["sync_status"] == "not_linked"

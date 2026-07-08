from app.services.malaysia_law_updater import (
    GENERATED_FILENAME,
    read_malaysia_law_update_status,
    update_malaysia_law_database,
)


def test_update_malaysia_law_database_writes_generated_reference(tmp_path):
    html = """
    <html>
      <body>
        <a href="/ilims/upload/portal/akta/LOM/EN/Act%20265.pdf">Act 265 - Employment Act 1955</a>
        <a href="/portal/latest">Today</a>
        <a href="/ilims/upload/portal/akta/LOM/EN/Act%20709.pdf">Act 709 - Personal Data Protection Act 2010</a>
      </body>
    </html>
    """

    manifest = update_malaysia_law_database(
        tmp_path,
        source_url="https://lom.agc.gov.my/",
        fetch_text=lambda _url: html,
    )

    generated = tmp_path / GENERATED_FILENAME
    assert manifest["status"] == "ok"
    assert manifest["link_count"] == 2
    assert generated.exists()
    content = generated.read_text(encoding="utf-8")
    assert "Employment Act 1955" in content
    assert "Personal Data Protection Act 2010" in content
    assert "https://lom.agc.gov.my/ilims/upload/portal/akta/LOM/EN/Act%20265.pdf" in content


def test_update_status_handles_never_run(tmp_path):
    status = read_malaysia_law_update_status(tmp_path)
    assert status["status"] == "never_run"
    assert status["link_count"] == 0

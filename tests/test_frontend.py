from pathlib import Path


STATIC = Path(__file__).resolve().parents[1] / "static"


def test_frontend_contains_required_surfaces():
    html = (STATIC / "index.html").read_text()
    for element_id in (
        'id="setup-view"',
        'id="main-view"',
        'id="settings-form"',
        'id="life-grid"',
        'id="projects-list"',
        'id="month-popover"',
        'id="reset-data"',
    ):
        assert element_id in html


def test_frontend_uses_server_api_not_local_storage():
    javascript = (STATIC / "app.js").read_text()
    assert "localStorage" not in javascript
    for endpoint in ("/api/settings", "/api/projects", "/api/projection", "/api/reset"):
        assert endpoint in javascript


def test_debounced_settings_save_submits_the_whole_form():
    javascript = (STATIC / "app.js").read_text()
    assert "function collectSettingsPayload()" in javascript
    assert "JSON.stringify(collectSettingsPayload())" in javascript
    assert "const previousSave = state.savePromise" in javascript
    assert "setTimeout(() => saveSetting(input)" not in javascript


def test_reset_waits_for_autosave_before_wiping_data():
    javascript = (STATIC / "app.js").read_text()
    assert "clearTimeout(state.saveTimer)" in javascript
    assert "state.savePromise" in javascript
    assert "await state.savePromise" in javascript
    assert "form.reset()" in javascript


def test_styles_are_responsive_and_expose_month_states():
    css = (STATIC / "styles.css").read_text()
    assert "@media" in css
    for class_name in (".month-cell.lived", ".month-cell.future", ".month-cell.current", ".project-marker"):
        assert class_name in css

import json
from app.services import normalization


def test_frozen_backend_reads_existing_packaged_data_layout(tmp_path, monkeypatch):
    bundled=tmp_path/"backend"/"data"
    bundled.mkdir(parents=True)
    (bundled/"university_directory.json").write_text(json.dumps({"universities":[{"id":"fictional-bundled-university"}]}))
    monkeypatch.setattr(normalization,"__file__",str(tmp_path/"app"/"services"/"normalization.py"))
    monkeypatch.setattr(normalization.sys,"_MEIPASS",str(tmp_path),raising=False)
    normalization.university_directory.cache_clear()
    try:
        assert normalization.university_directory()==[{"id":"fictional-bundled-university"}]
    finally:
        normalization.university_directory.cache_clear()

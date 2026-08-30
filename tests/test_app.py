from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_streamlit_golden_path_and_reset_have_no_exception():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(app_path), default_timeout=10).run()
    assert not app.exception
    assert app.text_area[0].value.startswith("Supportive contexts consistently")

    app.button[0].click().run()
    assert not app.exception
    assert any("Overgeneralized" in markdown.value for markdown in app.markdown)

    app.button[1].click().run()
    assert not app.exception
    assert app.text_area[0].value.startswith("Supportive contexts consistently")
    assert any("等待编译" in markdown.value for markdown in app.markdown)

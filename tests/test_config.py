"""Unit tests for the config module."""
import os
import tempfile


def test_settings_defaults(monkeypatch):
    """Test that Settings uses sensible defaults."""
    for key in ["DASHSCOPE_API_KEY", "OPENAI_API_KEY", "OPENAI_BASE_URL",
                 "OPENAI_MODEL", "DATA_DIR", "OUTPUT_DIR", "XMIND_BASE_PATH"]:
        monkeypatch.delenv(key, raising=False)

    from paper2xmind.config import Settings
    with tempfile.TemporaryDirectory() as tmp:
        s = Settings(data_dir=os.path.join(tmp, "data"), output_dir=os.path.join(tmp, "out"))
        assert s.api_key == ""
        assert s.base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"
        assert s.model == "qwen-plus"
        assert s.max_tokens_per_request == 16384
        assert s.pages_per_chunk == 3
        assert os.path.isdir(s.data_dir)
        assert os.path.isdir(s.output_dir)


def test_settings_reads_dashscope_key(monkeypatch):
    """Test that DASHSCOPE_API_KEY is preferred over OPENAI_API_KEY."""
    monkeypatch.setenv("DASHSCOPE_API_KEY", "dash-key-123")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key-456")

    from paper2xmind.config import Settings
    with tempfile.TemporaryDirectory() as tmp:
        s = Settings(data_dir=os.path.join(tmp, "d"), output_dir=os.path.join(tmp, "o"))
        assert s.api_key == "dash-key-123"


def test_settings_falls_back_to_openai_key(monkeypatch):
    """Test fallback to OPENAI_API_KEY when DASHSCOPE_API_KEY is not set."""
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key-456")

    from paper2xmind.config import Settings
    with tempfile.TemporaryDirectory() as tmp:
        s = Settings(data_dir=os.path.join(tmp, "d"), output_dir=os.path.join(tmp, "o"))
        assert s.api_key == "openai-key-456"


def test_settings_constructor_override():
    """Test that constructor args override env defaults."""
    from paper2xmind.config import Settings
    with tempfile.TemporaryDirectory() as tmp:
        s = Settings(
            api_key="custom-key",
            base_url="https://custom.example.com/v1",
            model="gpt-4o",
            data_dir=os.path.join(tmp, "d"),
            output_dir=os.path.join(tmp, "o"),
        )
        assert s.api_key == "custom-key"
        assert s.base_url == "https://custom.example.com/v1"
        assert s.model == "gpt-4o"


def test_settings_creates_directories():
    """Test that __post_init__ creates data and output dirs."""
    from paper2xmind.config import Settings
    with tempfile.TemporaryDirectory() as tmp:
        data = os.path.join(tmp, "new_data")
        output = os.path.join(tmp, "new_output")
        assert not os.path.exists(data)
        assert not os.path.exists(output)

        Settings(data_dir=data, output_dir=output)
        assert os.path.isdir(data)
        assert os.path.isdir(output)

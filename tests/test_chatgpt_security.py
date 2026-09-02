from custom_components.chatgpt_usage.security import redact_mapping


def test_redacts_all_credentials_recursively():
    result = redact_mapping(
        {
            "access_token": "a",
            "refresh_token": "b",
            "id_token": "c",
            "api_key": "d",
            "nested": {"Authorization": "Bearer secret", "safe": 123},
        }
    )
    assert result["access_token"] == "**REDACTED**"
    assert result["refresh_token"] == "**REDACTED**"
    assert result["id_token"] == "**REDACTED**"
    assert result["api_key"] == "**REDACTED**"
    assert result["nested"]["Authorization"] == "**REDACTED**"
    assert result["nested"]["safe"] == 123

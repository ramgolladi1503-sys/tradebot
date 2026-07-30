def test_dashboard_boot_import() -> None:
    import dashboard.streamlit_app_runtime as runtime

    assert runtime.__name__ == "dashboard.streamlit_app_runtime"

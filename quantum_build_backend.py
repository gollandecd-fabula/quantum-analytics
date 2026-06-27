def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    raise RuntimeError(
        "Wheel builds are intentionally disabled in Foundation. "
        "Select and pin a real build backend after repository bootstrap."
    )

def build_sdist(sdist_directory, config_settings=None):
    raise RuntimeError(
        "Source distribution builds are intentionally disabled in Foundation."
    )

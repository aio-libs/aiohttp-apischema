from aiohttp_apischema.generator import SWAGGER_PATH

async def test_files_exist() -> None:
    """Verify the swagger files have been copied in."""

    # Test every file we use in INDEX_HTML
    for f in ("swagger-ui-bundle.js", "swagger-ui-standalone-preset.js",
              "swagger-initializer.js", "swagger-ui.css", "index.css",
              "favicon-32x32.png", "favicon-16x16.png"):
        p = SWAGGER_PATH / f
        assert p.exists()

async def test_config() -> None:
    """Verify url has been substituted."""

    p = SWAGGER_PATH / "swagger-initializer.js"
    assert 'document.getElementById("swagger-ui").dataset.url' in p.read_text()

"""Shared pytest configuration for the test suite."""


def pytest_addoption(parser):
    parser.addoption(
        "--run-hardware",
        action="store_true",
        default=False,
        help="Run tests that require a real Sony camera connected via USB.",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "hardware: mark test as requiring real camera hardware"
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-hardware"):
        return
    skip_hw = __import__("pytest").mark.skip(reason="Need --run-hardware option to run")
    for item in items:
        if "hardware" in item.keywords:
            item.add_marker(skip_hw)

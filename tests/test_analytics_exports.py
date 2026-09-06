"""The Index's public surface must be reachable through `src.analytics`,
not just `src.analytics.index` -- everything else in this package
(gspro, hardware.pressure, processing.pressure, ui) re-exports its public
API from `__init__.py`, and the Index was the odd one out.

No behavior change: these re-exports point at the exact same objects
`index.py` defines.
"""
import src.analytics as analytics
import src.analytics.index as index


def test_intended_symbols_are_importable_from_the_package_root():
    from src.analytics import (
        IndexTier,
        bag_index_summary,
        evaluate_coverage,
        player_shanktuary_index,
        shanktuary_index,
    )

    assert bag_index_summary is index.bag_index_summary
    assert evaluate_coverage is index.evaluate_coverage
    assert player_shanktuary_index is index.player_shanktuary_index
    assert shanktuary_index is index.shanktuary_index
    assert IndexTier is index.IndexTier


def test_shanktuary_index_is_still_the_player_shanktuary_index_alias():
    assert analytics.shanktuary_index is analytics.player_shanktuary_index


def test_all_lists_exactly_the_intended_public_symbols():
    assert set(analytics.__all__) == {
        "IndexTier",
        "bag_index_summary",
        "evaluate_coverage",
        "player_shanktuary_index",
        "shanktuary_index",
    }


def test_every_name_in_all_is_actually_exported():
    for name in analytics.__all__:
        assert hasattr(analytics, name), f"{name} is in __all__ but not importable"


def test_wildcard_import_exposes_only_the_declared_public_symbols():
    namespace: dict[str, object] = {}
    exec("from src.analytics import *", namespace)
    exported = {k for k in namespace if not k.startswith("__")}
    assert exported == set(analytics.__all__)


def test_index_module_is_still_directly_importable():
    # the re-export is additive -- the existing `from src.analytics.index
    # import ...` call sites elsewhere in the codebase must keep working.
    assert index.bag_index_summary is analytics.bag_index_summary

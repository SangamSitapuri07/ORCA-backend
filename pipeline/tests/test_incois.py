"""Offline contract tests for the bounded INCOIS OPeNDAP adapter."""
from __future__ import annotations

import numpy as np
import xarray as xr

from pipeline.incois import (
    INCOIS_OPENDAP_BASE,
    INCOIS_PFZ_URL,
    _try_opendap_chl,
    get_sst,
    status,
)


def _dataset_with_time() -> xr.Dataset:
    return xr.Dataset(
        data_vars={
            "CHL": (
                ("time", "lat", "lon"),
                np.array([
                    [[0.2, 0.3, 0.4], [0.4, 0.5, 0.6], [0.6, 0.7, 0.8]],
                    [[0.8, 0.9, 1.0], [1.0, 1.1, 1.2], [1.2, 1.3, 1.4]],
                ]),
                {"units": "mg m^-3"},
            ),
        },
        coords={
            "time": np.array(["2026-08-10", "2026-08-14"], dtype="datetime64[D]"),
            "lat": [18.8, 19.0, 19.2],
            "lon": [72.6, 72.8, 73.0],
        },
    )


def test_incois_catalog_urls_have_expected_hosts():
    assert INCOIS_OPENDAP_BASE.startswith("http://las.incois.gov.in")
    assert "Oceansat2-OCM" in INCOIS_OPENDAP_BASE
    assert INCOIS_PFZ_URL.startswith("https://www.incois.gov.in")


def test_status_describes_conditional_role_without_liveness_claim():
    snapshot = status()
    assert "conditional" in snapshot["role"].lower()
    assert "checked per request" in snapshot["pfz_note"]
    assert "working" not in snapshot["role"].lower()


def test_opendap_selects_and_returns_actual_observation_date(monkeypatch):
    monkeypatch.setattr(xr, "open_dataset", lambda *a, **k: _dataset_with_time())

    result = _try_opendap_chl(19.0, 72.8, "2026-08-15", timeout_sec=2.0)

    assert result is not None and "error" not in result
    assert result["date"] == "2026-08-14"
    assert result["value"] == 1.1
    assert result["n_cells"] == 9
    assert "selected observation date 2026-08-14" in result["note"]


def test_opendap_rejects_unverifiable_time(monkeypatch):
    no_time = xr.Dataset(
        data_vars={"CHL": (("lat", "lon"), [[0.4, 0.5], [0.6, 0.7]])},
        coords={"lat": [18.9, 19.1], "lon": [72.7, 72.9]},
    )
    monkeypatch.setattr(xr, "open_dataset", lambda *a, **k: no_time.copy())

    result = _try_opendap_chl(19.0, 72.8, "2026-08-15", timeout_sec=2.0)

    assert result is not None
    assert "value" not in result
    assert "time coordinate" in result["error"]


def test_opendap_rejects_observation_outside_date_limit(monkeypatch):
    monkeypatch.setattr(xr, "open_dataset", lambda *a, **k: _dataset_with_time())

    result = _try_opendap_chl(19.0, 72.8, "2026-09-15", timeout_sec=2.0)

    assert result is not None
    assert "limit 7 days" in result["error"]


def test_get_sst_reports_not_implemented_without_provider_claim():
    result = get_sst(19.0, 72.8)
    assert result is not None
    assert result["error"] == "INCOIS SST is not implemented in the current ORCA adapter"

import httpx

from astro_mmdc.models.observations import Observation, Reference


SED_ROW = {
    "id": 3632803,
    "catalog": "MMDCXRT",
    "reference": {
        "citation": "Sahakyan N., et al., 2024, Astron. J., 168, 289",
        "bibcode": "2024AJ....168..289S",
        "url": None,
    },
    "is_lightcurve": False,
    "obsid": "00098312003",
    "ra": 217.13608, "dec": 42.67239,
    "sky_identifier": 2780037913,
    "flux": 1.696e-11, "flux_err": 5.11e-12,
    "frequency": 1.951e18, "mjd_start": 60947.48, "mjd_end": 60947.48,
    "is_upper_limit": False,
    "mjd_mid": None, "filter_band": None,
    "spectral_index": None, "spectral_index_err": None,
    "created_at": "2026-05-14T16:58:16.990821+04:00",
}

LC_ROW = {
    "id": 12775669,
    "catalog": "ZTF",
    "reference": None,
    "is_lightcurve": True,
    "obsid": None,
    "ra": 187.445, "dec": 8.0004,
    "sky_identifier": 7266497831,
    "flux": 1.133e-10, "flux_err": 2.078e-12,
    "frequency": None, "mjd_start": None, "mjd_end": None,
    "is_upper_limit": False,
    "mjd_mid": 60613.55, "filter_band": "R",
    "spectral_index": None, "spectral_index_err": None,
    "created_at": "2025-11-18T17:24:05.527223+04:00",
}


UPPER_LIMIT_ROW = {
    "id": 15853830,
    "catalog": "MMDCGR",
    "reference": None,
    "is_lightcurve": False,
    "obsid": None,
    "ra": 166.1138, "dec": 38.2088,
    "sky_identifier": 3221619842,
    "flux": 3.021e-12, "flux_err": None,
    "frequency": 1.813e23, "mjd_start": 55198.0, "mjd_end": 55228.0,
    "is_upper_limit": True,
    "mjd_mid": None, "filter_band": None,
    "spectral_index": None, "spectral_index_err": None,
    "created_at": "2026-05-14T16:58:16.990821+04:00",
}


def test_upper_limit_row_has_null_flux_err(mock_api, client):
    """Upper limits carry no measurement error, so flux_err comes back NULL.

    One such row used to abort the whole query with a ValidationError.
    """
    mock_api.get("/api/observations/").mock(
        return_value=httpx.Response(200, json=[SED_ROW, UPPER_LIMIT_ROW])
    )
    rows = client.observations.cone_search(
        ra=166.1138, dec=38.2088, radius_arcsec=4, catalog="MMDCGR"
    )
    assert len(rows) == 2
    assert rows[0].flux_err == 5.11e-12
    assert rows[1].flux_err is None
    assert rows[1].is_upper_limit


def test_query_returns_typed_observations(mock_api, client):
    mock_api.get("/api/observations/").mock(
        return_value=httpx.Response(200, json=[SED_ROW, LC_ROW])
    )
    rows = client.observations.query()
    assert len(rows) == 2
    assert all(isinstance(r, Observation) for r in rows)
    assert rows[0].catalog == "MMDCXRT"
    assert isinstance(rows[0].reference, Reference)
    assert rows[0].reference.bibcode == "2024AJ....168..289S"
    assert rows[1].catalog == "ZTF"
    assert rows[1].reference is None
    assert rows[1].filter_band == "R"


def test_query_filters_passed_as_params(mock_api, client):
    route = mock_api.get("/api/observations/").mock(
        return_value=httpx.Response(200, json=[])
    )
    client.observations.query(
        catalog="MMDCGR",
        is_lightcurve=True,
        is_upper_limit=False,
        filter_band="R",
        obsid="ZTF21abcdefg",
        mjd_min=60000.0,
        mjd_max=60100.0,
        ordering="-mjd_mid",
        limit=50,
    )
    url = str(route.calls[0].request.url)
    assert "catalog=MMDCGR" in url
    assert "is_lightcurve=true" in url
    assert "is_upper_limit=false" in url
    assert "filter_band=R" in url
    assert "obsid=ZTF21abcdefg" in url
    assert "mjd_min=60000.0" in url
    assert "mjd_max=60100.0" in url
    assert "ordering=-mjd_mid" in url
    assert "limit=50" in url


def test_query_drops_none_params(mock_api, client):
    route = mock_api.get("/api/observations/").mock(
        return_value=httpx.Response(200, json=[])
    )
    client.observations.query(catalog="ZTF")
    url = str(route.calls[0].request.url)
    assert "catalog=ZTF" in url
    assert "is_lightcurve" not in url
    assert "limit" not in url


def test_cone_search_passes_ra_dec_radius(mock_api, client):
    route = mock_api.get("/api/observations/").mock(
        return_value=httpx.Response(200, json=[LC_ROW])
    )
    rows = client.observations.cone_search(ra=187.28, dec=2.05, radius_arcsec=30.0)
    assert len(rows) == 1
    url = str(route.calls[0].request.url)
    assert "ra=187.28" in url
    assert "dec=2.05" in url
    assert "radius_arcsec=30.0" in url


def test_cone_search_default_radius(mock_api, client):
    route = mock_api.get("/api/observations/").mock(
        return_value=httpx.Response(200, json=[])
    )
    client.observations.cone_search(ra=1.0, dec=2.0)
    url = str(route.calls[0].request.url)
    assert "radius_arcsec=5.0" in url


def test_cone_search_with_extra_filters(mock_api, client):
    route = mock_api.get("/api/observations/").mock(
        return_value=httpx.Response(200, json=[])
    )
    client.observations.cone_search(
        ra=187.28, dec=2.05, radius_arcsec=10, catalog="ZTF", is_lightcurve=True
    )
    url = str(route.calls[0].request.url)
    assert "catalog=ZTF" in url
    assert "is_lightcurve=true" in url
    assert "ra=187.28" in url


def test_query_empty_result(mock_api, client):
    mock_api.get("/api/observations/").mock(
        return_value=httpx.Response(200, json=[])
    )
    rows = client.observations.query(catalog="MMDCGR")
    assert rows == []

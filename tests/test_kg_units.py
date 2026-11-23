from app import build_synthetic_district_summary, build_synthetic_markers


def test_synthetic_gamalama_is_included_in_ternate_tengah_summary():
    markers = build_synthetic_markers()
    gamalama = next(marker for marker in markers if marker['label'] == 'Gamalama')
    assert gamalama['district_name'] == 'Ternate Tengah'

    summary = build_synthetic_district_summary()
    assert summary['Ternate Tengah']['ikan'] >= 12.5
    assert 'Ternate Selatan' not in summary or summary['Ternate Selatan'].get('ikan', 0) < 12.5

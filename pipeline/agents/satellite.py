"""Agent 2: Satellite Analysis 🛰️

Processes chlorophyll, ocean colour, and satellite observations
from NOAA ERDDAP, INCOIS LAS, and (later) MOSDAC OCM-3.

Inputs: ZoneSnapshot
Outputs: dict of findings (same shape as ocean agent)
"""
from __future__ import annotations

from typing import Any
import math


def analyze(snap: dict[str, Any]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []

    chl = snap.get("chlorophyll")
    chl_source = snap.get("chlorophyll_source", "unknown")
    chl_unit = snap.get("chlorophyll_unit", "mg/m^3")

    if chl is None:
        return {
            "agent": "satellite",
            "findings": [{
                "type": "no_chlorophyll_data",
                "severity": "info",
                "value": None,
                "msg": f"No chlorophyll data available from {chl_source or 'any source'}.",
            }],
            "summary": "Chlorophyll data unavailable — ocean color cannot be assessed.",
            "risk_level": "unknown",
        }

    # Chlorophyll interpretation (mg/m^3):
    #  < 0.1  : oligotrophic (very low productivity, blue water)
    #  0.1-0.5: low productivity
    #  0.5-1.5: productive (good for fishing)
    #  1.5-5.0: highly productive (often upwelling zones)
    #  > 5.0  : very high (possible bloom, may be harmful)
    if chl < 0.1:
        sev = "info"
        typ = "chl_oligotrophic"
        msg = f"Chlorophyll {chl:.2f} {chl_unit} — very low productivity (oligotrophic)."
    elif chl < 0.5:
        sev = "info"
        typ = "chl_low"
        msg = f"Chlorophyll {chl:.2f} {chl_unit} — low productivity."
    elif chl < 1.5:
        sev = "good"
        typ = "chl_productive"
        msg = f"Chlorophyll {chl:.2f} {chl_unit} — productive zone, good for fishing."
    elif chl < 5.0:
        sev = "good"
        typ = "chl_high"
        msg = f"Chlorophyll {chl:.2f} {chl_unit} — highly productive (likely upwelling or bloom)."
    else:
        sev = "warn"
        typ = "chl_bloom"
        msg = f"Chlorophyll {chl:.2f} {chl_unit} — very high, possible harmful algal bloom."

    findings.append({
        "type": typ,
        "severity": sev,
        "value": chl,
        "msg": msg,
    })

    # log10 band: classical ocean-color zones
    if chl > 0:
        findings.append({
            "type": "chl_log10",
            "severity": "info",
            "value": round(math.log10(chl), 2),
            "msg": f"log10(chl) = {math.log10(chl):.2f} (ocean color band reference).",
        })

    findings.append({
        "type": "source_attribution",
        "severity": "info",
        "value": chl_source,
        "msg": f"Data source: {chl_source}",
    })

    # Cross-validation: if OC-CCI is also available, compare.
    # If they disagree by >2x, that's a flag — the value is uncertain.
    chl_occci = snap.get("chlorophyll_occci")
    chl_occci_source = snap.get("chlorophyll_occci_source", "ESA OC-CCI")
    if chl_occci is not None and chl > 0:
        ratio = max(chl, chl_occci) / min(chl, chl_occci)
        if ratio > 3.0:
            # >3x disagreement — this is real, surface it
            findings.append({
                "type": "chl_cross_check_disagree",
                "severity": "warn",
                "value": {"primary": chl, "occci": chl_occci, "ratio": round(ratio, 1)},
                "msg": (
                    f"⚠️ Cross-check disagrees: NOAA reports {chl:.2f} but "
                    f"OC-CCI reports {chl_occci:.2f} ({ratio:.1f}x apart). "
                    f"Chlorophyll is highly variable spatially — coastal blooms "
                    f"can be 10-100x higher than offshore water in the same "
                    f"0.2° box."
                ),
            })
        else:
            findings.append({
                "type": "chl_cross_check_ok",
                "severity": "good",
                "value": {"primary": chl, "occci": chl_occci, "ratio": round(ratio, 1)},
                "msg": (
                    f"✓ Cross-check agrees: NOAA {chl:.2f} vs OC-CCI "
                    f"{chl_occci:.2f} ({ratio:.1f}x apart, within 3x)."
                ),
            })
    else:
        # Cross-check absent (usually monsoon cloud cover masking OC-CCI).
        # Say "not cross-validated" explicitly — it is NOT "no data":
        # the primary measurement above is real and drives the risk tag.
        findings.append({
            "type": "chl_cross_check_missing",
            "severity": "info",
            "value": None,
            "msg": (
                "OC-CCI cross-check unavailable (usually monsoon clouds) — "
                "value above is the primary measurement, shown WITHOUT "
                "independent cross-validation."
            ),
        })

    # ISRO MOSDAC OCM-3 live — India's own satellite as a second,
    # INDEPENDENT cross-check (1 km LAC resolution — finer than the
    # primary's global grid). 🇮🇳
    chl_mosdac = snap.get("chlorophyll_mosdac")
    if chl_mosdac is not None and chl > 0:
        ratio_m = max(chl, chl_mosdac) / min(chl, chl_mosdac)
        mosdac_date = snap.get("chlorophyll_mosdac_date") or "latest"
        v3 = {"primary": chl, "mosdac": chl_mosdac, "ratio": round(ratio_m, 1)}

        # Pixel forensics from the direct-swath reader: how far the chosen
        # pixel drifted and what its own ~3 km neighbourhood reads. This is
        # the evidence that separates a REAL fine-scale bloom (whole patch
        # high) from a lone HOT pixel (cloud-contamination suspect).
        px_km = snap.get("chlorophyll_mosdac_pixel_km")
        ring_med = snap.get("chlorophyll_mosdac_ring_median")
        ring_n = snap.get("chlorophyll_mosdac_ring_valid")
        area_med = snap.get("chlorophyll_mosdac_area_median")
        cdom_v = snap.get("chlorophyll_mosdac_cdom_value")
        cdom_u = snap.get("chlorophyll_mosdac_cdom_units")
        scene_uniform = False  # set when the wider area is uniformly high too
        forensics = ""
        if ring_med is not None and ring_n:
            med_vs_mosdac = max(ring_med, chl_mosdac) / max(min(ring_med, chl_mosdac), 1e-9)
            patch_real = med_vs_mosdac <= 2.0  # neighbourhood agrees with the pixel
            where = f" ≈{px_km:g} km from the exact point" if px_km is not None else ""
            if patch_real:
                if (area_med is not None and ring_med
                        and max(area_med, ring_med) / max(min(area_med, ring_med), 1e-9) <= 2.0):
                    scene_uniform = True
                    forensics = (
                        f" Pixel forensics: the granule reads UNIFORMLY high here — the "
                        f"~3 km neighbourhood{where} reads ~{ring_med:.2f} and even the wider "
                        f"~80-pixel area reads ~{area_med:.2f}. That rules OUT fine coastal "
                        f"structure: a granule-level offset/bias in this pass is more likely "
                        f"than a real bloom."
                    )
                else:
                    forensics = (
                        f" Pixel forensics: OCM-3's whole ~3 km neighbourhood{where} reads "
                        f"high too (~{ring_med:.2f})"
                    )
                    if (area_med is not None and chl > 0
                            and max(area_med, chl) / min(area_med, chl) <= 3.0):
                        forensics += (
                            f", while the wider ~80-pixel area reads normal (~{area_med:.2f}) "
                            f"— OCM-3 may genuinely be resolving a small sharp patch here."
                        )
                    else:
                        forensics += " — the granule reports a real local patch, not one bad pixel."
            else:
                forensics = (
                    f" Pixel forensics: the chosen pixel{where} reads {chl_mosdac:.2f} "
                    f"while its own ~3 km neighbourhood reads ~{ring_med:.2f} — a lone "
                    f"HOT pixel, the classic cloud-contamination signature."
                )
        if cdom_v is not None:
            _u = f" {cdom_u}" if cdom_u else ""
            # Value-aware, not a blanket line: LOW CDOM means clear Case-1
            # water — then turbidity CANNOT explain the gap. (10.12N/80.62E
            # read 0.0048 1/m — very clear; rough 1/m scale bands below.)
            if cdom_v < 0.02:
                forensics += (
                    f" OCM-3 also reports CDOM={cdom_v:g}{_u} at this pixel — LOW, "
                    f"i.e. clear open-ocean (Case-1) water: a CDOM/turbidity artifact "
                    f"cannot explain the gap."
                )
            elif cdom_v < 0.15:
                forensics += (
                    f" OCM-3 also reports CDOM={cdom_v:g}{_u} at this pixel — moderate; "
                    f"dissolved organic matter may contribute a little to the gap."
                )
            else:
                forensics += (
                    f" OCM-3 also reports CDOM={cdom_v:g}{_u} at this pixel — high; "
                    f"CDOM-rich (Case-2) water makes satellite chlorophyll algorithms "
                    f"disagree."
                )

        if ratio_m <= 3.0:
            findings.append({
                "type": "chl_mosdac_check_ok",
                "severity": "good",
                "value": v3,
                "msg": (
                    f"✓ ISRO OCM-3 agrees: {chl_mosdac:.2f} mg/m³ (granule {mosdac_date}) "
                    f"vs primary {chl:.2f} ({ratio_m:.1f}x, within 3x) — India's own "
                    f"satellite independently confirms the reading. 🇮🇳"
                ),
            })
        elif ratio_m <= 5.0:
            # Moderate gap — the finer-resolution story is PLAUSIBLE here,
            # but still a difference, not a confirmation.
            findings.append({
                "type": "chl_mosdac_check_disagree",
                "severity": "warn",
                "value": v3,
                "msg": (
                    f"⚠️ ISRO OCM-3 ({chl_mosdac:.2f}, granule {mosdac_date}) vs primary "
                    f"{chl:.2f} — {ratio_m:.1f}x apart. Most likely OCM-3's 1 km pixels "
                    f"are resolving coastal fine structure the global grids smear out — "
                    f"but treat this as an UNRESOLVED difference, not a confirmation."
                    + forensics
                ),
            })
        else:
            # LARGE gap (>5x) — do NOT hide behind the resolution story.
            # Arbitrate with evidence: does the other independent source
            # (OC-CCI) side with the primary? Do the granule's own
            # neighbouring pixels back the value?
            occci_arbiter = ""
            if chl_occci is not None and min(chl, chl_occci) > 0:
                ratio_o = max(chl, chl_occci) / min(chl, chl_occci)
                if ratio_o <= 3.0:
                    occci_arbiter = (
                        f" NOAA and OC-CCI AGREE with each other "
                        f"({chl:.2f} vs {chl_occci:.2f}, {ratio_o:.1f}x) — OCM-3 is "
                        f"the outlier here."
                    )
            primary_date = snap.get("chlorophyll_date")
            date_note = ""
            if primary_date and mosdac_date != "latest" and primary_date != mosdac_date:
                date_note = (
                    f" Different dates may contribute (primary {primary_date} vs "
                    f"OCM-3 {mosdac_date})."
                )
            findings.append({
                "type": "chl_mosdac_check_outlier",
                "severity": "warn",
                "value": v3,
                "msg": (
                    f"⚠️ ISRO OCM-3 ({chl_mosdac:.2f}, granule {mosdac_date}) vs primary "
                    f"{chl:.2f} — {ratio_m:.1f}x apart, too large to explain by "
                    f"resolution alone."
                    + (occci_arbiter or " No third source available to arbitrate.")
                    + (" The evidence points to a scene-level overestimate in "
                       "this pass, not a real bloom." if scene_uniform else
                       " Likely a cloud-contaminated or misregistered pixel in this "
                       "granule, less likely a real bloom this sharp.")
                    + forensics + date_note
                    + " Verify against the image on mosdac.gov.in before trusting "
                      "this value; it is NOT counted as an independent confirmation."
                ),
            })

    # Risk — CENTRAL shared rule (agents.risk_from_findings). Tag comes
    # from the PRIMARY measurement's hazard level — never from whether an
    # optional cross-check source succeeded.
    from pipeline.agents import risk_from_findings
    risk = risk_from_findings(findings, has_data=True)  # chl is not None here

    n_good = sum(1 for f in findings if f["severity"] == "good")
    n_warn = sum(1 for f in findings if f["severity"] in ("warn", "high"))
    if n_warn > 0:
        summary = f"Satellite: chlorophyll shows concerning level ({chl:.2f} {chl_unit})."
    elif n_good > 0:
        summary = f"Satellite: chlorophyll indicates productive zone ({chl:.2f} {chl_unit})."
    else:
        summary = f"Satellite: chlorophyll {chl:.2f} {chl_unit} (low activity)."

    return {
        "agent": "satellite",
        "findings": findings,
        "summary": summary,
        "risk_level": risk,
    }

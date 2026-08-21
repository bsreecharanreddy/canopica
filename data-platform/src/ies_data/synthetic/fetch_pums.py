"""Fetches one state-year ACS PUMS person + household file and computes the marginal
distributions ``generator.py`` samples from, writing ``data/acs_pums_marginals.json``.

Not run at test time or build time -- the computed marginals are committed, so a clone with
no network still generates data. This script exists so a reader can re-derive them, and so a
future session can re-run it against a newer vintage.

Usage::

    uv run python -m ies_data.synthetic.fetch_pums

See ``docs/design/synthetic-data-methodology.md`` for the full provenance record: the exact
source files, every variable used and why, the transformation to monthly dollar amounts, and
the honest limitations of what these marginals can and cannot support.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import polars as pl

from ies_data.synthetic.distributions import age_band

VINTAGE = 2024
STATE_NAME = "Wyoming"
STATE_ABBR = "wy"
STATE_FIPS = "56"
BASE_URL = f"https://www2.census.gov/programs-surveys/acs/data/pums/{VINTAGE}/1-Year"
PERSON_URL = f"{BASE_URL}/csv_p{STATE_ABBR}.zip"
HOUSEHOLD_URL = f"{BASE_URL}/csv_h{STATE_ABBR}.zip"

OUTPUT_PATH = Path(__file__).parent / "data" / "acs_pums_marginals.json"

# Household sizes above this are folded into the top bucket -- matches Phase 1a's own
# policy_parameter_set seeding, which only covers SNAP household sizes 1-8 (Task 3).
MAX_HOUSEHOLD_SIZE = 8

# RELSHIPP -> the household_member.relationship values the operational schema's CHECK
# constraint allows (V1__core_entities.sql). Parent-in-law/son-in-law/daughter-in-law fold
# into OTHER_RELATIVE rather than getting their own bucket -- the schema has no room for that
# distinction and it isn't SNAP-material.
_RELATIONSHIP_MAP: dict[int, str] = {
    20: "SELF",
    21: "SPOUSE",
    22: "SPOUSE",
    23: "SPOUSE",
    24: "SPOUSE",
    25: "CHILD",
    26: "CHILD",
    27: "CHILD",
    28: "OTHER_RELATIVE",
    29: "PARENT",
    30: "OTHER_RELATIVE",
    31: "OTHER_RELATIVE",
    32: "OTHER_RELATIVE",
    33: "OTHER_RELATIVE",
    34: "UNRELATED",
    35: "OTHER_RELATIVE",
    36: "UNRELATED",
    # 37/38 = group quarters population -- excluded entirely, see load_person() below.
}

ROLES = ["SELF", "SPOUSE", "CHILD", "PARENT", "OTHER_RELATIVE", "UNRELATED"]

# TEN (tenure): 1 = owned with mortgage, 2 = owned free and clear, 3 = rented,
# 4 = occupied without payment of rent.
_TEN_OWNED_MORTGAGE = 1
_TEN_OWNED_FREE = 2
_TEN_RENTED = 3
_TEN_NO_PAY = 4


def _download_zip_csv(url: str) -> bytes:
    response = httpx.get(url, timeout=60.0, follow_redirects=True)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        (csv_name,) = [n for n in archive.namelist() if n.lower().endswith(".csv")]
        return archive.read(csv_name)


def _load_person(raw_csv: bytes) -> pl.DataFrame:
    person = pl.read_csv(
        raw_csv,
        columns=[
            "SERIALNO", "RELSHIPP", "AGEP", "SEX", "DIS", "ESR",
            "WAGP", "SEMP", "RETP", "SSIP", "ADJINC", "PWGTP",
        ],
        schema_overrides={"SERIALNO": pl.Utf8},
        infer_schema_length=10_000,
    )
    person = person.with_columns(
        pl.col("RELSHIPP").replace_strict(_RELATIONSHIP_MAP, default="EXCLUDE").alias("role")
    )
    # 37/38 (group quarters population) -- IES models households, not institutions.
    return person.filter(pl.col("role") != "EXCLUDE")


def _load_household(raw_csv: bytes) -> pl.DataFrame:
    household = pl.read_csv(
        raw_csv,
        columns=["SERIALNO", "NP", "TEN", "GRNTP", "SMOCP", "ELEP", "ADJHSG", "TYPEHUGQ", "WGTP"],
        schema_overrides={"SERIALNO": pl.Utf8},
        infer_schema_length=10_000,
    )
    # TYPEHUGQ == 1: housing units only, excluding group quarters -- see the same exclusion
    # on the person side, and the honest limitation this implies in the methodology doc.
    return household.filter(pl.col("TYPEHUGQ") == 1)


def _weighted_share(
    df: pl.DataFrame, group_col: str, weight_col: str = "PWGTP"
) -> dict[str, float]:
    grouped = df.group_by(group_col).agg(pl.col(weight_col).sum().alias("w"))
    total = grouped["w"].sum()
    return {
        str(row[group_col]): round(row["w"] / total, 5) for row in grouped.iter_rows(named=True)
    }


def _household_size_marginal(household: pl.DataFrame) -> dict[str, float]:
    sized = household.filter(pl.col("NP") >= 1).with_columns(
        pl.min_horizontal(pl.col("NP"), pl.lit(MAX_HOUSEHOLD_SIZE)).alias("np_capped")
    )
    return _weighted_share(sized, "np_capped", weight_col="WGTP")


def _age_by_role(person: pl.DataFrame) -> dict[str, dict[str, float]]:
    binned = person.with_columns((pl.col("AGEP") // 5 * 5).alias("age_bin5"))
    result: dict[str, dict[str, float]] = {}
    for role in ROLES:
        sub = binned.filter(pl.col("role") == role)
        if sub.height == 0:
            continue
        result[role] = _weighted_share(sub, "age_bin5")
    return result


def _rate_by_age_band(person: pl.DataFrame, positive_expr: pl.Expr) -> dict[str, float]:
    banded = person.with_columns(
        pl.col("AGEP").map_elements(age_band, return_dtype=pl.Utf8).alias("age_band")
    )
    grouped = banded.group_by("age_band").agg(
        [
            pl.col("PWGTP").filter(positive_expr).sum().alias("positive_w"),
            pl.col("PWGTP").sum().alias("total_w"),
        ]
    )
    return {
        row["age_band"]: round(row["positive_w"] / row["total_w"], 5)
        for row in grouped.iter_rows(named=True)
    }


def _deciles(values: pl.Series) -> list[float]:
    deciles = []
    for p in range(1, 10):
        quantile = values.quantile(p / 10)
        assert quantile is not None, "quantile() only returns None for an empty series"
        deciles.append(round(quantile, 2))
    return deciles


def compute_marginals(person_csv: bytes, household_csv: bytes) -> dict[str, Any]:
    person = _load_person(person_csv)
    household = _load_household(household_csv)

    adjinc = person["ADJINC"][0] / 1_000_000
    adjhsg = household["ADJHSG"][0] / 1_000_000

    non_head = person.filter(pl.col("role") != "SELF")
    earners = person.filter(pl.col("ESR").is_in([1, 2, 4, 5])).with_columns(
        ((pl.col("WAGP").fill_null(0) + pl.col("SEMP").fill_null(0)) * adjinc / 12).alias("v")
    ).filter(pl.col("v") > 0)
    unearned = person.with_columns(
        ((pl.col("RETP").fill_null(0) + pl.col("SSIP").fill_null(0)) * adjinc / 12).alias("v")
    ).filter(pl.col("v") > 0)
    renters = household.filter((pl.col("TEN") == _TEN_RENTED) & (pl.col("GRNTP") > 0)).with_columns(
        (pl.col("GRNTP") * adjhsg).alias("v")
    )
    owned = [_TEN_OWNED_MORTGAGE, _TEN_OWNED_FREE]
    owners = household.filter(pl.col("TEN").is_in(owned) & (pl.col("SMOCP") > 0)).with_columns(
        (pl.col("SMOCP") * adjhsg).alias("v")
    )
    utility = household.filter(pl.col("ELEP") > 0)
    utility = utility.with_columns((pl.col("ELEP") * adjhsg).alias("v"))

    tenure_occupied = household.filter(pl.col("TEN").is_not_null())
    tenure_share = _weighted_share(tenure_occupied, "TEN", weight_col="WGTP")
    p_owner_mortgage = tenure_share.get(str(_TEN_OWNED_MORTGAGE), 0.0)
    p_owner_free = tenure_share.get(str(_TEN_OWNED_FREE), 0.0)
    p_owner = p_owner_mortgage + p_owner_free
    p_renter = tenure_share.get(str(_TEN_RENTED), 0.0)
    p_no_pay = tenure_share.get(str(_TEN_NO_PAY), 0.0)

    return {
        "source": {
            "dataset": "American Community Survey 1-Year Public Use Microdata Sample (PUMS)",
            "vintage": VINTAGE,
            "state": STATE_NAME,
            "state_fips": STATE_FIPS,
            "person_file_url": PERSON_URL,
            "household_file_url": HOUSEHOLD_URL,
            "retrieved_on": datetime.now(UTC).date().isoformat(),
            "person_records_used": person.height,
            "household_records_used": household.height,
            "variables_used": [
                "NP", "AGEP", "SEX", "DIS", "ESR", "RELSHIPP", "WAGP", "SEMP", "RETP", "SSIP",
                "TEN", "GRNTP", "SMOCP", "ELEP", "ADJINC", "ADJHSG", "PWGTP", "WGTP", "TYPEHUGQ",
            ],
        },
        "household_size": _household_size_marginal(household),
        "sex": {"M": _weighted_share(person, "SEX")["1"], "F": _weighted_share(person, "SEX")["2"]},
        "age_by_role": _age_by_role(person),
        "relationship_distribution_for_additional_members": _weighted_share(non_head, "role"),
        "disability_by_age_band": _rate_by_age_band(person, pl.col("DIS") == 1),
        "employment_by_age_band": _rate_by_age_band(person, pl.col("ESR").is_in([1, 2, 4, 5])),
        "earned_income_monthly_deciles": _deciles(earners["v"]),
        "p_has_unearned_income": round(unearned.height / person.height, 5),
        "unearned_income_monthly_deciles": _deciles(unearned["v"]),
        "tenure": {
            "OWNS": round(p_owner, 5),
            "RENTS": round(p_renter, 5),
            "SHARED_HOUSING": round(p_no_pay, 5),
        },
        "rent_monthly_deciles": _deciles(renters["v"]),
        "mortgage_monthly_deciles": _deciles(owners["v"]),
        "p_pays_utilities": round(utility.height / household.height, 5),
        "utility_monthly_deciles": _deciles(utility["v"]),
    }


def main() -> None:
    print(f"Downloading {PERSON_URL}")
    person_csv = _download_zip_csv(PERSON_URL)
    print(f"Downloading {HOUSEHOLD_URL}")
    household_csv = _download_zip_csv(HOUSEHOLD_URL)

    marginals = compute_marginals(person_csv, household_csv)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(marginals, indent=2) + "\n")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

import pandas as pd

URL = "https://data.texas.gov/api/views/bc5r-88dy/rows.csv?accessType=DOWNLOAD"

df = pd.read_csv(URL, low_memory=False)

required = [
    "OPERATION_ID", "OPERATION_NUMBER", "OPERATION_TYPE", "OPERATION_NAME", "CITY", "COUNTY",
    "TOTAL_CAPACITY", "TOTAL_INSPECTIONS", "OPERATION_STATUS",
    "CORRECTIVE_ACTION", "ADVERSE_ACTION",
    "PROGRAMMATIC_SERVICES", "TREATMENT_SERVICES",
    "DEFICIENCY_HIGH", "DEFICIENCY_MEDIUM_HIGH", "DEFICIENCY_MEDIUM",
    "DEFICIENCY_MEDIUM_LOW", "DEFICIENCY_LOW",
]
missing = [c for c in required if c not in df.columns]
if missing:
    raise SystemExit("Missing expected columns, stopping so the site is not broken: " + str(missing))

gro = df[(df["OPERATION_TYPE"] == "General Residential Operation") & (df["OPERATION_STATUS"] == "Y")].copy()

if len(gro) < 200:
    raise SystemExit("Only " + str(len(gro)) + " open residential operations found, which looks wrong. Stopping so the site is not broken.")

w = {"DEFICIENCY_HIGH": 5, "DEFICIENCY_MEDIUM_HIGH": 4, "DEFICIENCY_MEDIUM": 3, "DEFICIENCY_MEDIUM_LOW": 2, "DEFICIENCY_LOW": 1}
gro["weighted"] = sum(gro[c] * v for c, v in w.items())
gro = gro[gro["TOTAL_INSPECTIONS"] > 0].copy()
gro["rate"] = gro["weighted"] / gro["TOTAL_INSPECTIONS"]

MIN_INSPECTIONS = 5
GOOD_MAX = 1.5
POOR_MIN = 3.5
POOR_WITH_ACTION_MIN = 2.5

scored = gro["TOTAL_INSPECTIONS"] >= MIN_INSPECTIONS
gro["flag"] = (gro["CORRECTIVE_ACTION"] == "YES") | (gro["ADVERSE_ACTION"] == "YES")

# Safety score: only for facilities with enough inspections, ranked against each other.
gro["safety_score"] = None
gro.loc[scored, "safety_score"] = (100 * (1 - gro.loc[scored, "rate"].rank(pct=True))).round(0)

# Inspection record rating, from fixed standards (not rank).
def rating(row):
    if row["TOTAL_INSPECTIONS"] < MIN_INSPECTIONS:
        return ""
    r = row["rate"]
    if row["flag"]:
        return "Poor" if r > POOR_WITH_ACTION_MIN else "Average"
    if r > POOR_MIN:
        return "Poor"
    if r <= GOOD_MAX:
        return "Good"
    return "Average"

gro["rating"] = gro.apply(rating, axis=1)

# Early signs: for facilities with too few inspections, compare their rate
# with the 25th and 75th percentile rates of the scored facilities.
low_cut = gro.loc[scored, "rate"].quantile(0.25)
high_cut = gro.loc[scored, "rate"].quantile(0.75)

def early(row):
    if row["TOTAL_INSPECTIONS"] >= MIN_INSPECTIONS:
        return ""
    if row["rate"] <= low_cut:
        return "Fewer findings than most"
    if row["rate"] >= high_cut:
        return "More findings than most"
    return "About average"

gro["early_signs"] = gro.apply(early, axis=1)
gro["has_score"] = scored
gro["rate"] = gro["rate"].round(2)

keep = [
    "OPERATION_ID", "OPERATION_NUMBER", "OPERATION_NAME", "CITY", "COUNTY",
    "TOTAL_CAPACITY", "TOTAL_INSPECTIONS", "safety_score", "has_score", "rating", "early_signs", "flag",
    "PROGRAMMATIC_SERVICES", "TREATMENT_SERVICES",
    "DEFICIENCY_HIGH", "DEFICIENCY_MEDIUM_HIGH", "DEFICIENCY_MEDIUM",
    "DEFICIENCY_MEDIUM_LOW", "DEFICIENCY_LOW", "rate",
    "CORRECTIVE_ACTION", "ADVERSE_ACTION",
]
out = gro[keep].copy()
out["TREATMENT_SERVICES"] = out["TREATMENT_SERVICES"].fillna("").str.replace("Mental Retardation", "Intellectual Disability")
out["PROGRAMMATIC_SERVICES"] = out["PROGRAMMATIC_SERVICES"].fillna("")
out.to_csv("scored_placements.csv", index=False)
print("Wrote", len(out), "placements,", int(scored.sum()), "with scores")
print(gro.loc[scored, "rating"].value_counts())

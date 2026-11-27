"""Day 13: configurable weight system for the ATS scoring engine.

The four scoring parts are:  skill_match, experience_relevance, education_alignment, semantic_similarity.
How much each part counts is NOT written inside the code. It lives in `ats_engine/ats_weights.json`,
so a recruiter or developer can change it without touching Python.

Which weights does a job get?  (first rule that fits wins)
    1. "roles"     the job's normalized title is listed        e.g. "data scientist"
    2. "profiles"  entry_level / senior (from the job level), then non_technical (from role_category)
    3. "default_weights"
    Then, if the job itself has an "ats_weights" dict, those numbers are applied on top.
Weights are always scaled so that they add up to 1.0 (100%).
"""
import json
from pathlib import Path

COMPONENTS = ("skill_match", "experience_relevance", "education_alignment", "semantic_similarity")
CONFIG_PATH = Path(__file__).with_name("ats_weights.json")
POLICIES = ("skip", "neutral", "zero")

_ENTRY_WORDS = ("fresher", "intern", "junior", "entry", "trainee")
_SENIOR_WORDS = ("senior", "lead", "principal", "head", "manager", "architect")
_cache = {}


def validate_config(config):
    """Return a list of problems (empty list = config is fine)."""
    errors = []

    def check_weights(name, weights, complete):
        if not isinstance(weights, dict):
            errors.append(f"{name}: must be an object")
            return
        unknown = [k for k in weights if k not in COMPONENTS]
        if unknown:
            errors.append(f"{name}: unknown part(s) {unknown}")
        if complete and set(weights) != set(COMPONENTS):
            errors.append(f"{name}: must contain all of {list(COMPONENTS)}")
        if any(not isinstance(v, (int, float)) or v < 0 for v in weights.values()):
            errors.append(f"{name}: weights must be numbers that are 0 or more")
        elif sum(weights.values()) <= 0:
            errors.append(f"{name}: weights must not all be 0")

    check_weights("default_weights", config.get("default_weights"), complete=True)
    for key, weights in config.get("profiles", {}).items():
        check_weights(f"profiles.{key}", weights, complete=True)
    for key, weights in config.get("roles", {}).items():
        check_weights(f"roles.{key}", weights, complete=False)
    for part in COMPONENTS:
        if config.get("missing_data", {}).get(part) not in POLICIES:
            errors.append(f"missing_data.{part}: must be one of {list(POLICIES)}")
    return errors


def load_config(path=None):
    """Read (and cache) the weight configuration file."""
    path = Path(path) if path else CONFIG_PATH
    key = str(path.resolve())
    if key not in _cache:
        config = json.loads(path.read_text(encoding="utf-8"))
        errors = validate_config(config)
        if errors:
            raise ValueError("Bad ATS weight config: " + "; ".join(errors))
        _cache[key] = config
    return _cache[key]


def normalize(weights):
    """Scale weights so they add up to exactly 1.0.  {'a': 2, 'b': 2} -> {'a': 0.5, 'b': 0.5}"""
    clean = {k: float(v) for k, v in weights.items() if v is not None}
    unknown = [k for k in clean if k not in COMPONENTS]
    if unknown:
        raise ValueError(f"Unknown scoring part(s): {unknown}")
    if any(v < 0 for v in clean.values()):
        raise ValueError("Weights cannot be negative")
    total = sum(clean.values())
    if total <= 0:
        raise ValueError("Weights must not all be 0")
    return {k: v / total for k, v in clean.items()}


def rescale(weights, active):
    """Keep only the parts that have data and scale them back up to 100%.

    Example: education is missing, so {skill .4, exp .25, edu .1, sem .25} becomes
    {skill .44, exp .28, sem .28}.  If every active weight is 0 the parts share equally.
    """
    chosen = {k: weights[k] for k in active if k in weights}
    if not chosen:
        return {}
    if sum(chosen.values()) <= 0:
        return {k: 1 / len(chosen) for k in chosen}
    return normalize(chosen)


def pick_profile(job, config):
    """Name of the weight set this job uses, e.g. 'role: data scientist' or 'profile: entry_level'."""
    title = (job.get("normalized_title") or job.get("title") or "").strip().lower()
    if title in config.get("roles", {}):
        return f"role: {title}"
    level = (job.get("level") or "").lower()
    profiles = config.get("profiles", {})
    if "entry_level" in profiles and any(w in level for w in _ENTRY_WORDS):
        return "profile: entry_level"
    if "senior" in profiles and any(w in level for w in _SENIOR_WORDS):
        return "profile: senior"
    if "non_technical" in profiles and job.get("role_category") == "non_technical":
        return "profile: non_technical"
    return "default"


def resolve_weights(job, config=None):
    """Return {'weights': {...adds up to 1...}, 'source': 'why these weights'} for one job."""
    config = config or load_config()
    source = pick_profile(job, config)
    if source == "default":
        base = dict(config["default_weights"])
    else:
        kind, name = source.split(": ", 1)
        base = dict(config["default_weights"])
        base.update(config["roles" if kind == "role" else "profiles"][name])
    override = job.get("ats_weights")
    if override:
        base.update(override)
        source += " + job override"
    return {"weights": normalize(base), "source": source}

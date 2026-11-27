"""Day 13: ATS scoring engine - a transparent, explainable candidate score.

Four parts are scored from 0 to 100, then combined with the weights from ats_weights.json:

    skill_match           how many of the job's must-have / good-to-have skills the candidate has
                          (exact = full credit, related skill = partial credit)         [Day 9 + Day 12]
    experience_relevance  how much of the candidate's work is useful for THIS job       [Day 10]
    education_alignment   degree level (60%) + field of study (40%) vs the job          [Day 11]
    semantic_similarity   do the candidate's experience / project text and the job's
                          text mean the same thing (embeddings)                         [Day 12]

    overall = sum( weight_of_part x score_of_part )

Missing data (the part of this task that needs care):
    * The JOB has nothing to compare (e.g. no education requirement)  -> part is skipped.
    * The CANDIDATE has no data for a part, then ats_weights.json "missing_data" says what to do:
          skip    leave the part out, share its weight among the others, lower the confidence
          neutral count it as 50 points
          zero    count it as 0 points
    * Entry-level job + no work experience -> experience is skipped, NOT punished.
    * Skipped parts are listed in `warnings`, and `confidence` / `data_completeness` go down.

Every number in the report comes with `reasons`, so a recruiter can see WHY the score is what it is.
"""
from datetime import datetime, timezone

from ats_engine.weights import COMPONENTS, load_config, rescale, resolve_weights
from parsers.education_relevance import score_education
from parsers.experience_relevance import score_experience
from utils.logger import get_logger

log = get_logger(__name__)

ENGINE_VERSION = "1.0.0"
PRETTY = {"skill_match": "Skill match", "experience_relevance": "Experience relevance",
          "education_alignment": "Education alignment", "semantic_similarity": "Semantic similarity"}
SHORT = {"skill_match": "skills", "experience_relevance": "experience",
         "education_alignment": "education", "semantic_similarity": "semantic"}


def _part(status, score=None, reasons=None, details=None):
    return {"status": status, "score": score, "reasons": list(reasons or []), "details": details or {}}


class ATSScoringEngine:
    def __init__(self, config=None, matcher=None, today=None):
        """matcher: a Day 12 SemanticMatcher (created on first use if not given). today: for tests."""
        self.config = config or load_config()
        self._matcher = matcher
        self._matcher_failed = False
        self.today = today

    @property
    def matcher(self):
        if self._matcher is None and not self._matcher_failed:
            try:
                from matching.semantic_engine import SemanticMatcher
                self._matcher = SemanticMatcher()
            except Exception as exc:                                   # numpy missing, model problem ...
                self._matcher_failed = True
                log.warning("Semantic matcher not available (%s): semantic parts will be skipped", exc)
        return self._matcher

    # ------------------------------------------------------------------ job side
    @staticmethod
    def job_view(job, job_doc=None):
        try:
            from matching.semantic_engine import job_views
            return job_views(job, job_doc)
        except ImportError:
            must, good = job.get("must_have_skills", []), job.get("good_to_have_skills", [])
            return {"skills": must + good, "must": must, "good": good,
                    "experience": job.get("title", ""), "projects": "", "summary": job.get("summary", "")}

    # ------------------------------------------------------------------ part 1: skills
    def _skill_match(self, resume, jv):
        must, good = jv.get("must", []), jv.get("good", [])
        if not (must or good):
            return _part("missing_job", reasons=["The job lists no skills to compare."])
        have = sorted(set(resume.get("skills") or []))
        if not have:
            return _part("missing_candidate", reasons=["No skills were found in the resume."])

        matcher = self.matcher
        if matcher is not None:
            r = matcher.compare_skills(have, jv)
            coverage, exact, related, missing = r["coverage"], r["matched_exact"], r["matched_semantic"], r["missing"]
        else:                                                         # offline fallback: exact matches only
            exact = [s for s in must + good if s in have]
            related, missing = [], [s for s in must + good if s not in have]
            m = sum(s in have for s in must) / len(must) if must else None
            g = sum(s in have for s in good) / len(good) if good else None
            coverage = 0.75 * m + 0.25 * g if (m is not None and g is not None) else (m if m is not None else g)

        wanted = len(must) + len(good)
        reasons = [f"{len(exact)} of {wanted} wanted skills matched exactly: {', '.join(exact) or 'none'}."]
        for r_ in related:
            reasons.append(f"'{r_['resume_skill']}' counts as related to '{r_['job_skill']}' "
                           f"(similarity {r_['similarity']}, partial credit).")
        missing_must = [s for s in missing if s in must]
        missing_good = [s for s in missing if s in good]
        if missing_must:
            reasons.append("Missing must-have skills: " + ", ".join(missing_must) + ".")
        if missing_good:
            reasons.append("Missing good-to-have skills: " + ", ".join(missing_good) + ".")
        return _part("scored", round(coverage * 100, 1), reasons,
                     {"matched_exact": exact, "matched_related": related,
                      "missing_must_have": missing_must, "missing_good_to_have": missing_good})

    # ------------------------------------------------------------------ part 2: experience
    def _experience(self, resume, job):
        exp = resume.get("experience")
        dated = [e for e in (exp or {}).get("entries", []) if e.get("_start_index") is not None]
        min_years = job.get("min_years") or 0
        if not dated:
            if min_years <= self.config["missing_data"].get("entry_level_max_years", 1):
                return _part("skipped_entry_level", reasons=[
                    "No work experience found, but the job is entry level: not penalised."])
            return _part("missing_candidate", reasons=[
                f"No dated work experience found, but the job asks for {min_years}+ years."])
        r = score_experience(exp, job, self.today)
        reasons = [f"{r['relevant_years']} relevant years ({r['effective_years']} after giving recent work more weight) "
                   f"against {r['required_years']}+ years required."] + list(r["notes"][1:])
        return _part("scored", float(r["score"]), reasons,
                     {"label": r["label"], "total_years": r["total_years"], "relevant_years": r["relevant_years"],
                      "required_years": r["required_years"], "years_fit": r["years_fit"],
                      "must_have_covered": r["must_have_covered"], "must_have_missing": r["must_have_missing"]})

    # ------------------------------------------------------------------ part 3: education
    def _education(self, resume, job):
        """Day 11 owns this logic (parsers/education_relevance.py); the engine only wraps the answer."""
        r = score_education(resume.get("education"), job, self.config["education"])
        keep = ("required_level", "preferred_fields", "highest_level")
        details = {k: r["details"][k] for k in keep} if r["status"] == "scored" else {}
        return _part(r["status"], r["score"], r["reasons"], details)

    # ------------------------------------------------------------------ part 4: semantic
    def _semantic(self, resume, jv):
        matcher = self.matcher
        if matcher is None:
            return _part("unavailable", reasons=["Semantic matcher is not available."])
        views, cfg = resume.get("views") or {}, self.config["semantic"]
        found = {}
        for key, weight in (("experience", cfg["experience_weight"]), ("projects", cfg["projects_weight"])):
            result = matcher.compare_text(views.get(key, ""), jv.get(key, ""))
            if result is not None:
                found[key] = (result, weight)
        if not found:
            job_has_text = any((jv.get(k) or "").strip() for k in ("experience", "projects"))
            if job_has_text:
                return _part("missing_candidate", reasons=["The resume has no experience or project text to compare."])
            return _part("missing_job", reasons=["The job has no text to compare."])
        score = 100 * sum(r["score"] * w for r, w in found.values()) / sum(w for _r, w in found.values())
        reasons = [f"{key.capitalize()} text is {r['score']:.0%} similar in meaning to the job text." for key, (r, _w) in found.items()]
        backend = getattr(getattr(matcher, "embedder", None), "name", "unknown")
        return _part("scored", round(score, 1), reasons, {"backend": backend})

    # ------------------------------------------------------------------ missing data policy
    def _apply_missing_policy(self, name, part):
        cfg, status = self.config["missing_data"], part["status"]
        part["policy"] = None
        if status == "missing_candidate":
            part["policy"] = cfg.get(name, "skip")
            if part["policy"] == "zero":
                part["score"] = 0.0
                part["reasons"].append("Missing data counts as 0 points (policy: zero).")
            elif part["policy"] == "neutral":
                part["score"] = float(cfg.get("neutral_score", 50))
                part["reasons"].append(f"Missing data counts as {part['score']:.0f} points (policy: neutral).")
            else:
                part["score"] = None
                part["reasons"].append("Skipped: its weight is shared among the other parts (policy: skip).")
        elif status in ("missing_job", "skipped_entry_level", "unavailable"):
            part["score"] = None
            part["reasons"].append("Skipped: its weight is shared among the other parts.")
        return part

    # ------------------------------------------------------------------ the main function
    def score(self, resume, job, job_doc=None, candidate_id=None):
        """resume: bundle with skills / experience / education / views (see score_generator.py).
        job: the Day 6 flat AI profile (data/parsed_jobs/*.profile.json).  Returns the explainable report."""
        jv = self.job_view(job, job_doc)
        parts = {
            "skill_match": self._skill_match(resume, jv),
            "experience_relevance": self._experience(resume, job),
            "education_alignment": self._education(resume, job),
            "semantic_similarity": self._semantic(resume, jv),
        }
        for name in COMPONENTS:
            self._apply_missing_policy(name, parts[name])

        resolved = resolve_weights(job, self.config)
        configured = resolved["weights"]
        active = [n for n in COMPONENTS if parts[n]["score"] is not None]
        effective = rescale(configured, active)
        overall = round(sum(parts[n]["score"] * effective[n] for n in active), 1) if active else 0.0

        components, warnings = {}, []
        for n in COMPONENTS:
            p = parts[n]
            weight = effective.get(n, 0.0)
            components[n] = {"score": p["score"], "weight": round(weight, 3),
                             "configured_weight": round(configured[n], 3),
                             "contribution": round(p["score"] * weight, 1) if p["score"] is not None else 0.0,
                             "status": p["status"], "missing_data_policy": p["policy"],
                             "reasons": p["reasons"], "details": p["details"]}
            if p["score"] is None:
                warnings.append(f"{PRETTY[n]} was skipped ({p['status'].replace('_', ' ')}); its weight was shared among the other parts.")
            elif p["status"] != "scored":
                warnings.append(f"{PRETTY[n]} used a filled-in value because the data was missing ({p['policy']}).")

        measured = sum(configured[n] for n in COMPONENTS if parts[n]["status"] == "scored")
        completeness = round(measured, 2)
        confidence = "high" if completeness >= 0.85 else "medium" if completeness >= 0.6 else "low"
        if not active:
            warnings.append("Nothing could be scored. The resume may be scanned or empty.")

        label = next(l for t, l in self.config["thresholds"]["labels"] if overall >= t)
        recommendation, why = self._recommend(overall, confidence, job)
        strengths = [f"{PRETTY[n]} is strong ({components[n]['score']:.0f}/100)." for n in active if components[n]["score"] >= 70]
        gaps = [f"{PRETTY[n]} is weak ({components[n]['score']:.0f}/100)." for n in active if components[n]["score"] < 50]
        flags = []
        missing_must = parts["skill_match"]["details"].get("missing_must_have", [])
        if missing_must:
            flags.append("Missing must-have skills: " + ", ".join(missing_must) + ".")
        formula = f"{overall} = " + " + ".join(f"{effective[n]:.2f} x {components[n]['score']:.1f} ({SHORT[n]})" for n in active) if active else "0"

        report = {
            "meta": {"record_type": "ats_score", "model_name": "ats", "model_version": ENGINE_VERSION,
                     "candidate_id": candidate_id, "job_id": job.get("job_id"),
                     "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")},
            "candidate_id": candidate_id, "job_id": job.get("job_id"), "job_title": job.get("title"),
            "overall_score": overall, "label": label,
            "recommendation": recommendation, "recommendation_reason": why,
            "confidence": confidence, "data_completeness": completeness,
            "weights": {"source": resolved["source"], "configured": {k: round(v, 3) for k, v in configured.items()},
                        "effective": {k: round(v, 3) for k, v in effective.items()}},
            "components": components, "formula": formula,
            "strengths": strengths, "gaps": gaps, "flags": flags, "warnings": warnings + list(resume.get("warnings", [])),
        }
        log.info("ATS score for %s vs '%s': %s (%s, %s)", candidate_id, job.get("title"), overall, label, recommendation)
        return report

    def _recommend(self, overall, confidence, job):
        th = self.config["thresholds"]
        cutoff = job.get("ats_cutoff_score") or th["shortlist_score"]
        margin = th["review_margin"]
        if confidence == "low":
            return "review", "Too much data is missing to decide automatically: check the resume manually."
        if overall >= cutoff:
            return "shortlist", f"Score {overall} reaches the cutoff of {cutoff}."
        if overall >= cutoff - margin:
            return "review", f"Score {overall} is within {margin} points of the cutoff of {cutoff}."
        return "reject", f"Score {overall} is below the cutoff of {cutoff}."


def format_report(report):
    """Human-readable version of the report (what a recruiter would read)."""
    lines = [f"{report['candidate_id']}  vs  {report['job_title']}",
             f"OVERALL {report['overall_score']}/100 ({report['label']})  ->  {report['recommendation'].upper()}: {report['recommendation_reason']}",
             f"Confidence: {report['confidence']} (data completeness {report['data_completeness']:.0%})   "
             f"Weights: {report['weights']['source']}", "", "How the score was built:"]
    for name in COMPONENTS:
        c = report["components"][name]
        score = f"{c['score']:5.1f}" if c["score"] is not None else "  --- "
        lines.append(f"  {PRETTY[name]:22} score {score}  weight {c['weight']:.2f}  = {c['contribution']:5.1f} points   [{c['status']}]")
        lines += [f"      - {r}" for r in c["reasons"]]
    lines += ["", "Formula: " + report["formula"]]
    for title, key in (("Strengths", "strengths"), ("Gaps", "gaps"), ("Flags", "flags"), ("Warnings", "warnings")):
        if report[key]:
            lines.append(f"{title}:")
            lines += [f"  - {x}" for x in report[key]]
    return "\n".join(lines)

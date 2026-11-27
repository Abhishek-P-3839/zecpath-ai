
## Day 13 - ATS scoring formula (explainable candidate score)

Scores a resume against a job from 0 to 100 using four parts, and explains every number.

    overall = skill_match x w1 + experience_relevance x w2 + education_alignment x w3 + semantic_similarity x w4

- `ats_engine/scoring_engine.py` : the ATS scoring engine (four parts, missing-data rules, explainable report)
- `ats_engine/ats_weights.json` : the configurable weights (default, per profile, per role, missing-data policy, cutoffs)
- `ats_engine/weights.py` : loads and checks the weights, picks the right set for each job, re-scales when a part is skipped
- `ats_engine/score_generator.py` : candidate score generator (resume file -> all earlier modules -> report, ranking, saving)
- `run_ats_demo.py` : scores every resume in `data/raw_resumes/` against every job in `data/parsed_jobs/` (saves to `data/ats_scores/`)
- `tests/test_ats_engine.py` : unit tests

Run: `python run_ats_demo.py`
One pair: `python -m ats_engine.score_generator data/raw_resumes/Maya.pdf data/parsed_jobs/jd_mern_developer.profile.json`
Test: `python -m unittest tests.test_ats_engine -v`

Change how much each part counts by editing `ats_engine/ats_weights.json` (no Python needed).
A single job can override the weights with an `"ats_weights"` object in its profile.

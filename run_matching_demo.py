"""Day 12 demo: match every sample resume against every parsed job.   python run_matching_demo.py"""
import glob
import json
import os

from extraction.extractor import SUPPORTED
from matching.semantic_engine import SemanticMatcher, job_views, resume_views_from_file

matcher = SemanticMatcher()                      # neural model if installed, otherwise the offline embedder
print("Embedding backend:", matcher.embedder.name)

jobs = {}
for profile_path in sorted(glob.glob("data/parsed_jobs/*.profile.json")):
    name = os.path.basename(profile_path).replace(".profile.json", "")
    doc_path = profile_path.replace(".profile.json", ".json")
    doc = json.load(open(doc_path, encoding="utf-8")) if os.path.exists(doc_path) else None
    jobs[name] = job_views(json.load(open(profile_path, encoding="utf-8")), doc)

for path in sorted(glob.glob("data/raw_resumes/*")):
    if os.path.splitext(path)[1].lower() not in SUPPORTED:
        continue
    views = resume_views_from_file(path)
    if not views["skills"] and not views["experience"]:
        print(f"\n{os.path.basename(path)}: nothing to match (scanned or empty)")
        continue
    print(f"\n{os.path.basename(path)}  ({len(views['skills'])} skills)")
    for name, job in jobs.items():
        r = matcher.match(views, job)
        c = r["components"]
        print(f"  vs {name:26} {r['overall']:3} {r['label']:8} skills {c['skills']['score']:.2f}  experience {c['experience']['score']:.2f}")

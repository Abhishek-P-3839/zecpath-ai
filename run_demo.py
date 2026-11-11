"""Small demo: parse the sample resume, score it and print a decision."""
from ats_engine.ats_scorer import calculate_ats_score
from parsers.resume_parser import parse_resume_text
from scoring.scoring import combine_scores, get_decision

with open("data/sample_resume.txt") as f:
    parsed = parse_resume_text(f.read())

ats = calculate_ats_score(parsed, ["Python", "React", "Node.js"], min_experience=1)
final = combine_scores({"ats": ats, "hr": 70, "technical": 65, "machine_test": 75})
print("Parsed resume :", parsed)
print("ATS score     :", ats)
print("Final score   :", final, "->", get_decision(final))

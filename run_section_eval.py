"""Day 8: measure section detection accuracy and write the report.

    python run_section_eval.py

Writes docs/Day8_Section_Detection_Accuracy_Report.md and data/labeled_resumes/evaluation_results.json
"""
from parsers.section_eval import run_all, write_report
from tests.labeled_sample_builder import build_all

build_all()                      # make sure the labeled samples are up to date
runs = run_all()
path = write_report(runs)
for name in ("rules_all", "hybrid_all", "hybrid_holdout"):
    run = runs[name]
    print(f"{name:15} accuracy {run['accuracy']:.1%}  "
          f"({run['lines_correct']}/{run['lines_total']} lines)  macro-F1 {run['macro_f1']}")
print("Report saved to", path)

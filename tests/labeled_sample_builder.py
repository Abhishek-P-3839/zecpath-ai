"""Builds the Day 8 labeled resume samples in data/labeled_resumes/.

Each sample is saved as  <name>.labeled.txt : one line per resume line, written as
    section<TAB>text            (an empty line = a blank line in the resume)
so the file is both the resume AND its answer key. manifest.json lists every sample.

Labelling convention: a heading line belongs to its own section. For a combined heading
such as "Skills & Certifications" the heading line gets the FIRST section named.

Samples come in two groups:
  - real:  the resumes the Day 5 extractor already produced (labelled by line ranges, by hand)
  - hand-written: small resumes written to cover layouts the real ones do not
Each hand-written sample is tagged split="dev" (used while tuning the classifier) or
split="holdout" (never used for tuning, so its accuracy is an honest estimate).

Run:  python -m tests.labeled_sample_builder
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "labeled_resumes"
EXTRACTED = ROOT / "data" / "extracted"

# ---- real resumes: (file, category, [(first_line, last_line, section), ...])  1-based, inclusive
REAL = {
    "alex": ("standard", [(1, 2, "header"), (3, 7, "summary"), (8, 13, "skills"),
                          (14, 31, "experience"), (32, 34, "education"), (35, 37, "certifications")]),
    "marcus": ("combined_heading", [(1, 2, "header"), (3, 6, "summary"), (7, 17, "experience"),
                                    (18, 19, "education"), (20, 21, "certifications"), (22, 22, "skills")]),
    "Maya": ("standard", [(1, 2, "header"), (3, 6, "summary"), (7, 17, "experience"),
                          (18, 19, "education"), (20, 23, "skills")]),
    "sample_simple": ("standard", [(1, 2, "header"), (3, 4, "summary"), (5, 6, "skills"), (7, 8, "experience")]),
    "sample_two_column": ("two_column", [(1, 5, "skills"), (6, 8, "education"), (9, 12, "experience"),
                                         (13, 16, "projects")]),
    "sample_bullets_table": ("table", [(1, 1, "header"), (2, 5, "experience"), (6, 8, "education")]),
}

# ---- hand-written samples: name -> (category, split, [(section, [lines]), ...])
HAND = {
    # ------------------------------------------------------------------ DEV set
    "dev_caps_headings": ("caps_headings", "dev", [
        ("header", ["RAHUL VERMA", "Pune, Maharashtra | +91 91234 56780 | rahul.verma@example.com | github.com/rahulverma"]),
        ("summary", ["OBJECTIVE:", "Motivated fresher seeking an entry-level software developer role to apply Python and web skills."]),
        ("education", ["EDUCATION:", "B.Tech in Computer Science, Savitribai Phule Pune University",
                       "CGPA: 8.4/10 | 2021 - 2025", "Higher Secondary (HSC), Fergusson College, 2021, 88%"]),
        ("skills", ["TECHNICAL SKILLS:", "Languages: Python, Java, JavaScript, SQL",
                    "Web: HTML, CSS, React, Node.js", "Tools: Git, Docker, VS Code"]),
        ("projects", ["PROJECTS:", "Library Management System - web app built with Flask and MySQL",
                      "Hospital Appointment Portal - React frontend with a REST API backend",
                      "Tech stack: React, Node.js, MongoDB"]),
        ("certifications", ["CERTIFICATIONS:", "Python for Everybody - Coursera",
                            "AWS Cloud Practitioner (Certified), 2024"]),
    ]),
    "dev_numbered": ("numbered_headings", "dev", [
        ("header", ["Neha Kapoor", "Delhi | neha.kapoor@example.com | 98100 12345"]),
        ("summary", ["1. Professional Summary",
                     "Data analyst with 4 years of experience turning messy datasets into dashboards that leaders use."]),
        ("experience", ["2. Work History", "Data Analyst | Orbit Analytics Pvt Ltd | Mar 2021 - Present",
                        "- Built Power BI dashboards that cut weekly reporting time by 40%",
                        "- Cleaned and modelled sales data in SQL and Python for 6 regional teams",
                        "Junior Analyst | Bright Retail Ltd | Jul 2019 - Feb 2021",
                        "- Prepared monthly MIS reports for senior management"]),
        ("skills", ["3. Core Competencies", "SQL, Python, Power BI, Tableau, Excel, Statistics, A/B Testing"]),
        ("education", ["4. Academic Background", "M.Sc Statistics, University of Delhi, 2019",
                       "B.Sc Mathematics, Hansraj College, 2017"]),
    ]),
    "dev_inline_headings": ("inline_headings", "dev", [
        ("header", ["Karan Mehta", "karan.mehta@example.com | +91 99887 76655 | Bengaluru"]),
        ("skills", ["Skills: Java, Spring Boot, MySQL, Docker, AWS, Kafka"]),
        ("education", ["Education: B.E. Information Technology, VIT Vellore, 2020"]),
        ("certifications", ["Certifications: Oracle Certified Associate Java SE 8, AWS Solutions Architect Associate (SAA-C03)"]),
        ("experience", ["Work Experience", "Software Engineer - Finserve Technologies, Chennai  Aug 2020 - Present",
                        "- Designed Spring Boot microservices handling 2M requests per day",
                        "- Migrated a monolith to AWS ECS, reducing infrastructure cost by 25%"]),
        ("projects", ["Projects", "Expense tracker app - Spring Boot, React, MySQL"]),
    ]),
    "dev_no_headings_fresher": ("no_headings", "dev", [
        ("header", ["Ananya Rao", "Hyderabad | ananya.rao@example.com | 90000 11122 | linkedin.com/in/ananyarao"]),
        ("summary", ["Final year computer science student looking for an internship in machine learning."]),
        ("skills", ["Python, NumPy, Pandas, scikit-learn, TensorFlow, SQL, Git"]),
        ("education", ["B.Tech Computer Science and Engineering", "JNTU Hyderabad, 2021 - 2025, CGPA 8.9"]),
        ("projects", ["Movie recommendation system using collaborative filtering",
                      "Handwritten digit classifier built with TensorFlow",
                      "Tech stack: Python, TensorFlow, Flask"]),
        ("certifications", ["Machine Learning Specialization - Coursera",
                            "Deep Learning with PyTorch - Udemy certificate"]),
    ]),
    "dev_no_headings_experienced": ("no_headings", "dev", [
        ("header", ["James Carter", "Seattle, WA | (206) 555-0172 | james.carter@example.com"]),
        ("summary", ["Backend engineer with 9 years of experience building payment systems. Passionate about reliability and clean APIs."]),
        ("experience", ["Senior Backend Engineer, Northwind Payments Inc., Seattle, WA  2019 - Present",
                        "- Led a team of 5 engineers to rebuild the payouts service in Go",
                        "- Reduced p99 latency from 900ms to 120ms by redesigning the cache layer",
                        "Software Engineer, Contoso Systems, Portland, OR  2015 - 2019",
                        "- Developed REST APIs in Java for an order management platform",
                        "- Mentored 3 interns and ran weekly code reviews"]),
        ("education", ["B.S. Computer Science, Oregon State University, 2015"]),
        ("skills", ["Go, Java, PostgreSQL, Redis, Kafka, Docker, Kubernetes, AWS"]),
    ]),
    "dev_partial_headings": ("partial_headings", "dev", [
        ("header", ["Priyanka Das", "Kolkata, West Bengal | priyanka.das@example.com | +91 98300 45678"]),
        ("skills", ["Digital Marketing: SEO, SEM, Google Ads, Google Analytics, Mailchimp",
                    "Content: Copywriting, Canva, WordPress, Email Marketing"]),
        ("experience", ["Experience", "Digital Marketing Executive | BlueWave Media Pvt Ltd | Feb 2022 - Present",
                        "- Managed Google Ads campaigns with a monthly budget of INR 3 Lakhs",
                        "- Grew organic traffic by 55% through an SEO content calendar"]),
        ("education", ["Education", "MBA Marketing, Calcutta University, 2021", "B.Com, St. Xavier's College, 2019"]),
    ]),
    # ------------------------------------------------------------------ HOLDOUT set
    "hold_alt_headings": ("alt_headings", "holdout", [
        ("header", ["Daniel Okafor", "Toronto, ON | (416) 555-0123 | daniel.okafor@example.com | linkedin.com/in/danielokafor"]),
        ("summary", ["Professional Profile",
                     "Cloud engineer who enjoys automating infrastructure and helping teams ship safely."]),
        ("experience", ["Professional Experience", "Cloud Engineer - Maple Cloud Services, Toronto  June 2021 - Present",
                        "- Automated environment provisioning with Terraform, saving 10 hours per release",
                        "- Implemented monitoring dashboards used by 8 product teams",
                        "Systems Administrator - Lakeshore Networks Inc., Mississauga  May 2018 - May 2021",
                        "- Maintained 120 Linux servers with 99.9% uptime"]),
        ("skills", ["Technical Skills", "Terraform, Ansible, AWS, Azure, Linux, Python, Bash, Docker, Kubernetes"]),
        ("projects", ["Selected Projects", "Homelab GitOps - Kubernetes cluster managed with ArgoCD",
                      "Open source contributor to a Terraform provider (github.com/danielokafor)"]),
        ("certifications", ["Licenses & Certifications", "AWS Certified Solutions Architect - Associate",
                            "HashiCorp Certified: Terraform Associate"]),
        ("education", ["Education", "B.Eng. Computer Engineering, University of Waterloo, 2018"]),
    ]),
    "hold_typo_headings": ("typo_headings", "holdout", [
        ("header", ["Sofia Marino", "sofia.marino@example.com | +1 415 555 0166 | San Francisco, CA"]),
        ("summary", ["Summary", "Product designer with 6 years of experience in consumer mobile apps."]),
        ("experience", ["Experiance", "Senior Product Designer - Lumen Apps, San Francisco  Jan 2020 - Present",
                        "- Redesigned onboarding flow, lifting activation by 18%",
                        "- Led design system adoption across 4 squads",
                        "Product Designer - Pixel Forge Studio, Oakland  2017 - 2019",
                        "- Designed 12 client mobile apps from research to launch"]),
        ("education", ["Educaton", "B.F.A. Graphic Design, California College of the Arts, 2017"]),
        ("skills", ["Skils", "Figma, Sketch, Prototyping, User Research, Design Systems, HTML, CSS"]),
    ]),
    "hold_combined_heading": ("combined_heading", "holdout", [
        ("header", ["Vikram Singh", "Jaipur, Rajasthan | vikram.singh@example.com | +91 98290 11223"]),
        ("summary", ["Summary", "Backend developer with 3 years of experience in Python and cloud deployments."]),
        ("experience", ["Experience", "Backend Developer at Pink City Technologies Pvt Ltd  July 2022 - Present",
                        "- Built Django REST services used by 50k monthly users",
                        "- Wrote integration tests that raised coverage from 40% to 85%"]),
        ("skills", ["Skills & Certifications", "Python, Django, REST APIs, PostgreSQL, Docker"]),
        ("certifications", ["AWS Certified Developer - Associate"]),
        ("skills", ["Git, Linux, CI/CD, Redis"]),
        ("certifications", ["Certified Kubernetes Application Developer (CKAD)"]),
        ("education", ["Education", "B.Tech Computer Science, Malaviya National Institute of Technology, 2022"]),
    ]),
    "hold_no_headings_wrapped": ("no_headings", "holdout", [
        ("header", ["Meera Iyer", "Chennai, Tamil Nadu | meera.iyer@example.com | +91 98400 22334"]),
        ("summary", ["Recent graduate passionate about full stack development and eager to learn in a",
                     "fast moving product team."]),
        ("experience", ["Web Development Intern at Marina Softech Pvt Ltd  Jan 2025 - Jun 2025",
                        "- Built reusable React components for an internal admin dashboard that",
                        "reduced page load time by 30%",
                        "- Fixed 40+ bugs reported by the QA team and wrote unit tests"]),
        ("projects", ["Online Quiz Portal - developed with React, Express and MongoDB",
                      "Weather Dashboard app using public APIs, deployed on Netlify"]),
        ("skills", ["React, JavaScript, HTML, CSS, Node.js, Express, MongoDB, Git"]),
        ("education", ["B.E. Computer Science, Anna University, 2021 - 2025", "CGPA 8.2"]),
    ]),
    "hold_two_column_heading_row": ("two_column", "holdout", [
        ("header", ["Arjun Nair"]),
        ("skills", ["Skills Education", "Python, SQL, Excel, Power BI, Tableau"]),
        ("education", ["MBA Finance, Symbiosis Institute of Business Management, 2022",
                       "B.Com, Christ University, 2020"]),
        ("experience", ["Experience", "Financial Analyst | Capital Edge Consulting | Aug 2022 - Present",
                        "- Built variance analysis models used in monthly board reviews",
                        "- Automated reconciliation in Excel and SQL, saving 8 hours a week"]),
    ]),
    "hold_table_rows": ("table", "holdout", [
        ("header", ["Lakshmi Pillai", "lakshmi.pillai@example.com | +91 94470 55667"]),
        ("skills", ["Skills | Python, SQL, Pandas, Matplotlib, Excel"]),
        ("education", ["Education", "Degree | University", "M.Sc Data Science | Kerala University", "B.Sc Statistics | Mahatma Gandhi University"]),
        ("experience", ["Experience", "Role | Company | Duration",
                        "Data Analyst Trainee | Techno Park Analytics | Jan 2024 - Dec 2024"]),
        ("certifications", ["Certifications | Google Data Analytics Professional Certificate, Coursera"]),
    ]),
    "hold_no_headings_extras": ("no_headings", "holdout", [
        ("header", ["Omar Haddad", "Dubai, UAE | omar.haddad@example.com | +971 50 123 4567"]),
        ("summary", ["Accountant with 7 years of experience in audit and financial reporting."]),
        ("experience", ["Senior Accountant, Desert Rose Trading LLC, Dubai  Mar 2019 - Present",
                        "- Prepared consolidated financial statements for 5 subsidiaries",
                        "- Reduced month-end close from 10 days to 6 days",
                        "Audit Associate, Gulf Assurance Group, Abu Dhabi  2016 - 2019",
                        "- Conducted audits for 20+ mid-sized clients"]),
        ("education", ["B.Com Accounting, University of Sharjah, 2016"]),
        ("certifications", ["Certified Public Accountant (CPA), 2018", "ACCA Qualification, 2017"]),
        ("skills", ["SAP, QuickBooks, Excel, IFRS, Budgeting, Forecasting"]),
        ("other", ["Languages: Arabic, English, French", "Hobbies: chess, hiking"]),
    ]),
    "hold_other_sections": ("other_sections", "holdout", [
        ("header", ["Rohan Gupta", "Noida, Uttar Pradesh | rohan.gupta@example.com | +91 98110 77889"]),
        ("summary", ["Career Objective", "Seeking a QA engineer role where I can use my testing and automation skills."]),
        ("skills", ["Key Skills", "Selenium, Java, TestNG, Postman, JIRA, SQL, Manual Testing"]),
        ("experience", ["Employment History", "QA Engineer, Delta Soft Solutions Pvt Ltd  Sep 2022 - Present",
                        "- Automated 150 regression test cases using Selenium and TestNG",
                        "- Raised and tracked 300+ defects in JIRA"]),
        ("education", ["Academic Qualifications", "B.Tech Electronics, Amity University, 2022"]),
        ("other", ["Languages", "English, Hindi", "Interests", "Cricket, photography",
                   "Declaration", "I hereby declare that the information above is true to the best of my knowledge."]),
    ]),
}


def _write(name, category, split, source, labeled_lines):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    body = "\n".join(f"{label}\t{text}" if label else "" for label, text in labeled_lines)
    (OUT_DIR / f"{name}.labeled.txt").write_text(body + "\n", encoding="utf-8")
    return {"name": name, "category": category, "split": split, "source": source, "lines": len(labeled_lines)}


def build_all():
    """Write every labeled sample plus manifest.json. Returns the manifest list."""
    manifest = []
    for name, (category, ranges) in REAL.items():
        lines = (EXTRACTED / f"{name}.txt").read_text(encoding="utf-8").split("\n")
        labels = [None] * len(lines)
        for first, last, section in ranges:
            for number in range(first, last + 1):
                labels[number - 1] = section
        if any(lab is None and ln.strip() for lab, ln in zip(labels, lines)):
            raise ValueError(f"{name}: some lines were not labelled")
        manifest.append(_write(name, category, "real", "real resume (Day 5 extraction)", list(zip(labels, lines))))
    for name, (category, split, groups) in HAND.items():
        pairs = [(section, text) for section, texts in groups for text in texts]
        manifest.append(_write(name, category, split, "hand-written", pairs))
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    for item in build_all():
        print(f"{item['split']:8} {item['category']:18} {item['name']:32} {item['lines']} lines")

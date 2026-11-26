from parsers.section_classifier import detect_heading, score_line, segment_resume

# Part A: is this line a heading?
print(detect_heading("WORK EXPERIENCE"))
print(detect_heading("Experiance"))
print(detect_heading("- Built REST APIs"))
print(detect_heading("Skils"))

# Part B: what does this line look like?
for line in ["Led a team of 5 engineers"]:  
    scores = score_line(line)
    best = max(scores, key=scores.get)
    print(line, "->", best, scores)

# Part C: a resume with NO headings
text = """Ananya Rao
ananya@example.com | 90000 11122
Python, NumPy, Pandas, SQL, Git
B.Tech Computer Science
JNTU Hyderabad, 2021 - 2025, CGPA 8.9
Coursera - Machine Learning Certificate"""
for tag in segment_resume(text)["line_tags"]:
    print(tag["section"], "|", tag["text"])
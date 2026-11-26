"""Master skill dictionary for the Day 9 skill extraction engine.

Everything here is plain Python data, so it is easy to extend. No other code changes are needed
to teach the engine a new skill, synonym, misspelling or stack.

    SKILLS           canonical skill -> (category, [aliases])     the master dictionary
    MISSPELLINGS     canonical skill -> [common wrong spellings]
    AMBIGUOUS        short words that are also normal English ("Go", "R", "Excel", "Spring")
    STACKS           "MERN" -> the skills it stands for
    DOMAIN_OVERRIDES which skills count as business / creative even though their category says tool

The master dictionary STARTS from the Day 6 job-description dictionary (parsers/jd_taxonomy.py),
so resumes and job descriptions always use the same canonical names ("reactjs" -> "react").
Categories are exactly the ones allowed by data/schemas/resume_schema.json (skill.category).
"""
from parsers.jd_taxonomy import SKILLS as JD_SKILLS

ALLOWED_CATEGORIES = (
    "programming_language", "framework", "database", "cloud_devops", "tool",
    "design", "business_domain", "soft_skill", "other",
)
DOMAINS = ("technical", "business", "creative", "soft")

# ------------------------------------------------------------------ 1. master dictionary
# Start from the Day 6 dictionary (copied, so Day 6 is never changed by accident).
SKILLS = {name: (category, list(aliases)) for name, (category, aliases) in JD_SKILLS.items()}

# New skills: canonical name -> (category, [aliases]). The canonical name is also an alias.
_NEW_SKILLS = {
    # ---- programming languages
    "c": ("programming_language", ["c programming", "c language"]),
    "r": ("programming_language", ["r programming", "r language", "rstudio"]),
    "swift": ("programming_language", ["swift", "swiftui"]),
    "rust": ("programming_language", ["rust"]),
    "scala": ("programming_language", ["scala"]),
    "dart": ("programming_language", ["dart"]),
    "perl": ("programming_language", ["perl"]),
    "matlab": ("programming_language", ["matlab"]),
    "bash": ("programming_language", ["bash", "shell scripting", "shell script", "shell scripts"]),
    "powershell": ("programming_language", ["powershell"]),
    "vba": ("programming_language", ["vba", "excel vba"]),
    "sass": ("programming_language", ["sass", "scss"]),
    # ---- frameworks and libraries
    "jquery": ("framework", ["jquery"]),
    "spring": ("framework", ["spring", "spring mvc"]),
    "hibernate": ("framework", ["hibernate"]),
    "svelte": ("framework", ["svelte", "sveltekit"]),
    "nuxt.js": ("framework", ["nuxt.js", "nuxtjs", "nuxt"]),
    "wordpress": ("framework", ["wordpress"]),
    "spark": ("framework", ["apache spark", "pyspark", "spark"]),
    "matplotlib": ("framework", ["matplotlib"]),
    "seaborn": ("framework", ["seaborn"]),
    "plotly": ("framework", ["plotly"]),
    "scipy": ("framework", ["scipy"]),
    "jupyter": ("tool", ["jupyter", "jupyter notebook", "jupyter notebooks"]),
    "keras": ("framework", ["keras"]),
    "opencv": ("framework", ["opencv"]),
    "hugging face": ("framework", ["hugging face", "huggingface"]),
    "langchain": ("framework", ["langchain"]),
    "webpack": ("framework", ["webpack"]),
    "socket.io": ("framework", ["socket.io", "socketio"]),
    "junit": ("framework", ["junit"]),
    "cypress": ("framework", ["cypress"]),
    "playwright": ("framework", ["playwright"]),
    # ---- databases
    "sql server": ("database", ["sql server", "mssql", "ms sql", "microsoft sql server"]),
    "oracle": ("database", ["oracle", "oracle db", "oracle database"]),
    "mariadb": ("database", ["mariadb"]),
    "dynamodb": ("database", ["dynamodb", "dynamo db"]),
    "firebase": ("database", ["firebase", "firestore"]),
    "cassandra": ("database", ["cassandra"]),
    "snowflake": ("database", ["snowflake"]),
    "bigquery": ("database", ["bigquery", "big query"]),
    "neo4j": ("database", ["neo4j"]),
    "nosql": ("database", ["nosql", "no sql"]),
    # ---- cloud and devops
    "nginx": ("cloud_devops", ["nginx"]),
    "apache": ("cloud_devops", ["apache", "apache server", "apache http server"]),
    "ansible": ("cloud_devops", ["ansible"]),
    "helm": ("cloud_devops", ["helm"]),
    "grafana": ("cloud_devops", ["grafana"]),
    "prometheus": ("cloud_devops", ["prometheus"]),
    "heroku": ("cloud_devops", ["heroku"]),
    "vercel": ("cloud_devops", ["vercel"]),
    "netlify": ("cloud_devops", ["netlify"]),
    "kafka": ("cloud_devops", ["kafka", "apache kafka"]),
    "airflow": ("cloud_devops", ["airflow", "apache airflow"]),
    # ---- tools, practices, data
    "npm": ("tool", ["npm", "yarn"]),
    "swagger": ("tool", ["swagger", "openapi"]),
    "jwt": ("tool", ["jwt", "json web token", "json web tokens"]),
    "oauth": ("tool", ["oauth", "oauth2", "oauth 2.0"]),
    "unit testing": ("tool", ["unit testing", "unit tests"]),
    "tdd": ("tool", ["tdd", "test driven development"]),
    "kanban": ("tool", ["kanban"]),
    "confluence": ("tool", ["confluence"]),
    "trello": ("tool", ["trello"]),
    "asana": ("tool", ["asana"]),
    "slack": ("tool", ["slack"]),
    "notion": ("tool", ["notion"]),
    "salesforce": ("tool", ["salesforce", "sfdc"]),
    "hubspot": ("tool", ["hubspot"]),
    "marketo": ("tool", ["marketo"]),
    "google analytics": ("tool", ["google analytics", "ga4", "google analytics 4"]),
    "google ads": ("tool", ["google ads", "google adwords", "adwords"]),
    "meta ads": ("tool", ["meta ads", "facebook ads", "facebook advertising"]),
    "quickbooks": ("tool", ["quickbooks"]),
    "sap": ("tool", ["sap", "sap erp"]),
    "google workspace": ("tool", ["google workspace", "g suite", "gsuite"]),
    "web scraping": ("tool", ["web scraping", "beautifulsoup", "scrapy"]),
    "data visualization": ("other", ["data visualization", "data visualisation"]),
    "data analysis": ("other", ["data analysis", "data analytics"]),
    "etl": ("other", ["etl", "data pipelines", "data pipeline"]),
    "oop": ("other", ["oop", "oops", "object oriented programming"]),
    "data structures": ("other", ["data structures", "data structures and algorithms", "dsa"]),
    "llm": ("other", ["llm", "llms", "large language models"]),
    "generative ai": ("other", ["generative ai", "genai", "gen ai"]),
    "computer vision": ("other", ["computer vision"]),
    # ---- business
    "project management": ("business_domain", ["project management", "project planning"]),
    "stakeholder management": ("business_domain", ["stakeholder management", "stakeholder communication"]),
    "risk management": ("business_domain", ["risk management"]),
    "process optimization": ("business_domain", ["process optimization", "process optimisation",
                                                 "process improvement"]),
    "budgeting": ("business_domain", ["budgeting", "budget management", "budget planning"]),
    "financial analysis": ("business_domain", ["financial analysis", "financial modeling",
                                               "financial modelling"]),
    "financial reporting": ("business_domain", ["financial reporting"]),
    "supply chain": ("business_domain", ["supply chain", "supply chain management", "scm"]),
    "inventory management": ("business_domain", ["inventory management", "inventory control"]),
    "vendor management": ("business_domain", ["vendor management"]),
    "kpi tracking": ("business_domain", ["kpi tracking", "kpi reporting"]),
    "email marketing": ("business_domain", ["email marketing", "email campaigns", "email nurture"]),
    "content marketing": ("business_domain", ["content marketing"]),
    "social media marketing": ("business_domain", ["social media marketing", "social media management"]),
    "marketing automation": ("business_domain", ["marketing automation"]),
    "demand generation": ("business_domain", ["demand generation", "demand gen"]),
    "campaign management": ("business_domain", ["campaign management"]),
    "a/b testing": ("business_domain", ["a/b testing", "ab testing", "a/b tests"]),
    "market research": ("business_domain", ["market research"]),
    "business analysis": ("business_domain", ["business analysis", "requirements gathering"]),
    "account management": ("business_domain", ["account management", "client management"]),
    "payroll": ("business_domain", ["payroll", "payroll processing"]),
    "employee engagement": ("business_domain", ["employee engagement"]),
    "onboarding": ("business_domain", ["onboarding", "employee onboarding"]),
    "performance management": ("business_domain", ["performance management"]),
    "gst": ("business_domain", ["gst", "gst filing"]),
    "auditing": ("business_domain", ["auditing", "internal audit"]),
    "six sigma": ("business_domain", ["six sigma", "lean six sigma"]),
    # ---- soft skills
    "critical thinking": ("soft_skill", ["critical thinking"]),
    "adaptability": ("soft_skill", ["adaptability", "adaptable"]),
    "decision making": ("soft_skill", ["decision making", "decision-making"]),
    "conflict resolution": ("soft_skill", ["conflict resolution"]),
    "negotiation": ("soft_skill", ["negotiation", "negotiating"]),
    "presentation skills": ("soft_skill", ["presentation skills", "public speaking"]),
    "mentoring": ("soft_skill", ["mentoring", "coaching"]),
    "attention to detail": ("soft_skill", ["attention to detail", "detail oriented"]),
    "creativity": ("soft_skill", ["creativity", "creative thinking"]),
    # ---- creative / design
    "adobe illustrator": ("design", ["adobe illustrator", "illustrator"]),
    "adobe xd": ("design", ["adobe xd"]),
    "indesign": ("design", ["indesign", "adobe indesign"]),
    "premiere pro": ("design", ["premiere pro", "adobe premiere", "adobe premiere pro"]),
    "after effects": ("design", ["after effects", "adobe after effects"]),
    "canva": ("design", ["canva"]),
    "blender": ("design", ["blender"]),
    "autocad": ("design", ["autocad"]),
    "graphic design": ("design", ["graphic design", "graphic designing"]),
    "video editing": ("design", ["video editing", "video editor"]),
    "motion graphics": ("design", ["motion graphics"]),
    "wireframing": ("design", ["wireframing", "wireframes"]),
    "prototyping": ("design", ["prototyping", "prototypes"]),
    "branding": ("design", ["branding", "brand identity"]),
    "typography": ("design", ["typography"]),
    "3d modeling": ("design", ["3d modeling", "3d modelling"]),
    "photography": ("design", ["photography", "photo editing"]),
    "storyboarding": ("design", ["storyboarding", "storyboards"]),
    "copywriting": ("other", ["copywriting", "copywriter"]),
    "content writing": ("other", ["content writing", "content creation", "technical writing"]),
}
for _name, (_category, _aliases) in _NEW_SKILLS.items():
    SKILLS[_name] = (_category, sorted({_name, *_aliases}, key=len, reverse=True))

# Extra aliases for skills that already exist in Day 6.
_EXTRA_ALIASES = {
    "aws": ["ec2", "aws ec2", "aws lambda", "amazon s3", "aws s3", "amazon ec2"],
    "ci/cd": ["github actions", "gitlab ci", "continuous integration", "continuous deployment"],
    "agile": ["scrummaster", "scrum master"],
    "express": ["express"],
    "go": ["go"],
    "excel": ["advanced excel", "excel spreadsheets", "excel"],
    "crm": ["customer relationship management", "zoho crm", "salesforce crm"],
    "leadership": ["cross functional leadership", "team leadership", "people management"],
    "teamwork": ["cross functional collaboration", "teamwork"],
    "problem solving": ["problem solving", "problemsolving"],
    "rest api": ["api development", "restful services", "web services"],
    "machine learning": ["machine learning", "ml"],
    "ui/ux": ["user experience", "user interface design"],
    "sales": ["sales"],
}
for _name, _aliases in _EXTRA_ALIASES.items():
    _category, _old = SKILLS[_name]
    SKILLS[_name] = (_category, sorted({*_old, *_aliases}, key=len, reverse=True))

# ------------------------------------------------------------------ 2. misspellings
# Wrong spellings seen in real resumes. They map to the right skill with a lower confidence.
# (A hyphen and a space are treated the same, so "java-script" needs no entry of its own.)
MISSPELLINGS = {
    "python": ["pyhton", "phyton", "pyton", "pythn", "pythom"],
    "javascript": ["javascipt", "javscript", "jvascript", "javascrpit", "java scipt", "javasript"],
    "typescript": ["typescrpit", "typscript", "typesript", "type scipt"],
    "react": ["recat", "reactjs", "raect"],
    "node.js": ["nod.js", "node-js", "nodjs", "noded.js"],
    "mongodb": ["monogdb", "mongdb", "mongo-db", "mongodv"],
    "postgresql": ["postgre sql", "postgress", "postgres sql", "postgre"],
    "mysql": ["my sql", "mysq", "mysqli"],
    "kubernetes": ["kubernates", "kuberentes", "kubernetis", "kubenetes"],
    "docker": ["dockr", "doker", "dockker"],
    "tensorflow": ["tensor flow", "tensorflw", "tensorflo"],
    "pytorch": ["py torch", "pytorc", "pytroch"],
    "tableau": ["tablue", "tablaeu", "tableu"],
    "power bi": ["powerbi", "power b.i", "power-bi", "powr bi"],
    "excel": ["exel", "excell", "ms-excel", "ms excell"],
    "photoshop": ["photoshp", "photo shop", "photoshopp"],
    "angular": ["anguler", "angualr", "angulr"],
    "django": ["djano", "djanga", "djnago"],
    "selenium": ["selenuim", "seleniun"],
    "machine learning": ["machin learning", "machine learing", "machine lerning", "machinelearning"],
    "communication": ["comunication", "communciation", "communicaton", "comunication skills"],
    "leadership": ["leadrship", "leadersihp", "leadeship"],
    "teamwork": ["team work", "teamwrok"],
    "git": ["git hub", "gitub"],
    "fastapi": ["fast-api", "fastpi"],
    "flask": ["falsk", "flaks"],
    "linux": ["linex"],
    "elasticsearch": ["elasticsarch", "elastic-search"],
    "microservices": ["micro-services", "microservice", "micro service"],
    "ci/cd": ["ci-cd", "ci cd pipeline", "cicd pipeline"],
    "rest api": ["restapi", "restfull api", "rest-api"],
    "problem solving": ["problem solvin"],
}

# ------------------------------------------------------------------ 3. ambiguous short words
# These are normal English words (or single letters), so a plain match is NOT trusted.
# A match is accepted only when:
#   (a) it is written exactly as `form` AND sits in a skills list / skills section, or
#   (b) one of the `cues` words appears in the same bullet or sentence.
AMBIGUOUS = {
    "c": {"skill": "c", "form": "C", "cues": ["programming", "language", "embedded", "pointers",
                                              "c++", "c/c++", "firmware"]},
    "r": {"skill": "r", "form": "R", "cues": ["programming", "language", "rstudio", "ggplot",
                                              "tidyverse", "statistical", "statistics"]},
    "go": {"skill": "go", "form": "Go", "cues": ["golang", "programming", "language", "goroutines",
                                                 "microservices", "backend"]},
    "excel": {"skill": "excel", "form": "Excel", "cues": ["pivot", "vlookup", "spreadsheet",
                                                          "spreadsheets", "formulas", "macros",
                                                          "microsoft", "ms"]},
    "express": {"skill": "express", "form": "Express", "cues": ["node", "nodejs", "mongodb", "mern",
                                                                "mean", "middleware", "routes", "api"]},
    "spring": {"skill": "spring", "form": "Spring", "cues": ["java", "boot", "mvc", "hibernate"]},
    "spark": {"skill": "spark", "form": "Spark", "cues": ["apache", "pyspark", "hadoop", "big data",
                                                          "scala", "databricks"]},
    "notion": {"skill": "notion", "form": "Notion", "cues": ["workspace", "wiki", "docs", "pages",
                                                              "database", "templates"]},
    "slack": {"skill": "slack", "form": "Slack", "cues": ["channel", "channels", "workspace",
                                                          "integration", "bot", "messaging"]},
    "snowflake": {"skill": "snowflake", "form": "Snowflake", "cues": ["warehouse", "sql", "etl",
                                                                      "cloud", "data"]},
    "sap": {"skill": "sap", "form": "SAP", "cues": ["erp", "hana", "abap", "fico", "modules"]},
    "swift": {"skill": "swift", "form": "Swift", "cues": ["ios", "xcode", "apple", "swiftui",
                                                          "objective-c"]},
}

# Phrases that prove a word is NOT the skill, e.g. "(SQL)" after "sales qualified lead" is a lead
# type, not the database language. Checked against the lowercase sentence the word sits in.
CONTEXT_EXCLUSIONS = {
    "sql": [r"qualified\s+leads?", r"sales\W?qualified", r"marketing\W?qualified"],
    "sap": [r"\bsap\s+(?:is|was)\b"],
}

# ------------------------------------------------------------------ 4. skill stacks
# A stack name stands for several skills. Finding "MERN" also gives MongoDB, Express, React, Node.js
# (with lower confidence, because the resume never wrote them out).
# `aliases` are matched ignoring case; `exact_aliases` only when written exactly like that
# ("MEAN" the stack, not "mean" the word).
STACKS = {
    "MERN": {"components": ["mongodb", "express", "react", "node.js"],
             "aliases": ["mern", "mern stack", "mern-stack", "m.e.r.n"], "exact_aliases": []},
    "MEAN": {"components": ["mongodb", "express", "angular", "node.js"],
             "aliases": ["mean stack", "mean-stack", "m.e.a.n"], "exact_aliases": ["MEAN"]},
    "MEVN": {"components": ["mongodb", "express", "vue", "node.js"],
             "aliases": ["mevn", "mevn stack"], "exact_aliases": []},
    "PERN": {"components": ["postgresql", "express", "react", "node.js"],
             "aliases": ["pern", "pern stack"], "exact_aliases": []},
    "LAMP": {"components": ["linux", "apache", "mysql", "php"],
             "aliases": ["lamp stack"], "exact_aliases": ["LAMP"]},
    "LEMP": {"components": ["linux", "nginx", "mysql", "php"],
             "aliases": ["lemp", "lemp stack"], "exact_aliases": []},
}

# ------------------------------------------------------------------ 5. business / creative domain
# Default: category -> domain. DOMAIN_OVERRIDES fixes the tools that are not really "technical".
CATEGORY_TO_DOMAIN = {
    "programming_language": "technical", "framework": "technical", "database": "technical",
    "cloud_devops": "technical", "tool": "technical", "other": "technical",
    "design": "creative", "business_domain": "business", "soft_skill": "soft",
}
DOMAIN_OVERRIDES = {
    "excel": "business", "power bi": "business", "tableau": "business", "jira": "business",
    "agile": "business", "kanban": "business", "trello": "business", "asana": "business",
    "slack": "business", "confluence": "business", "notion": "business", "salesforce": "business",
    "hubspot": "business", "marketo": "business", "google analytics": "business",
    "google ads": "business", "meta ads": "business", "quickbooks": "business", "sap": "business",
    "google workspace": "business", "data analysis": "business", "data visualization": "business",
    "copywriting": "creative", "content writing": "creative", "ui/ux": "creative",
}


def domain_of(skill):
    """Return 'technical', 'business', 'creative' or 'soft' for a canonical skill name."""
    if skill in DOMAIN_OVERRIDES:
        return DOMAIN_OVERRIDES[skill]
    return CATEGORY_TO_DOMAIN[SKILLS[skill][0]]

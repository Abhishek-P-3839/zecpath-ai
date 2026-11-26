"""Knowledge base for the job description parser (Day 6).

Holds three things, all plain Python dicts so they are easy to extend:
    SKILLS       canonical skill -> category and all the ways a JD may write it
    ROLES        canonical role  -> role category and all its title variations
    EDUCATION    degree keywords per education level (same levels as job_schema.json)

To teach the parser a new skill or role, add one entry here. No other code changes.
"""

# canonical (lowercase) name -> (category, [aliases]).
# Categories are the ones allowed by data/schemas/job_schema.json (job_skill.category).
SKILLS = {
    # programming languages
    "python": ("programming_language", ["python", "python3", "python 3"]),
    "java": ("programming_language", ["java", "core java"]),
    "javascript": ("programming_language", ["javascript", "java script", "ecmascript", "es6"]),
    "typescript": ("programming_language", ["typescript", "type script"]),
    "c++": ("programming_language", ["c++", "cpp"]),
    "c#": ("programming_language", ["c#", "csharp", "c sharp"]),
    "go": ("programming_language", ["golang", "go lang"]),
    "php": ("programming_language", ["php"]),
    "ruby": ("programming_language", ["ruby"]),
    "kotlin": ("programming_language", ["kotlin"]),
    "sql": ("programming_language", ["sql", "t-sql", "pl/sql", "plsql"]),
    "html": ("programming_language", ["html", "html5"]),
    "css": ("programming_language", ["css", "css3"]),
    # frameworks and libraries
    "react": ("framework", ["react", "reactjs", "react.js", "react js"]),
    "react native": ("framework", ["react native", "react-native"]),
    "angular": ("framework", ["angular", "angularjs", "angular.js"]),
    "vue": ("framework", ["vue", "vuejs", "vue.js"]),
    "next.js": ("framework", ["next.js", "nextjs"]),
    "redux": ("framework", ["redux"]),
    "node.js": ("framework", ["node.js", "nodejs", "node js", "node"]),
    "express": ("framework", ["express.js", "expressjs"]),
    "django": ("framework", ["django"]),
    "flask": ("framework", ["flask"]),
    "fastapi": ("framework", ["fastapi", "fast api"]),
    "spring boot": ("framework", ["spring boot", "springboot", "spring framework"]),
    ".net": ("framework", [".net", "dotnet", "asp.net", ".net core"]),
    "laravel": ("framework", ["laravel"]),
    "flutter": ("framework", ["flutter"]),
    "bootstrap": ("framework", ["bootstrap"]),
    "tailwind css": ("framework", ["tailwind", "tailwind css", "tailwindcss"]),
    "pandas": ("framework", ["pandas"]),
    "numpy": ("framework", ["numpy"]),
    "scikit-learn": ("framework", ["scikit-learn", "scikit learn", "sklearn"]),
    "tensorflow": ("framework", ["tensorflow"]),
    "pytorch": ("framework", ["pytorch"]),
    # databases
    "mongodb": ("database", ["mongodb", "mongo db", "mongo"]),
    "mysql": ("database", ["mysql"]),
    "postgresql": ("database", ["postgresql", "postgres"]),
    "redis": ("database", ["redis"]),
    "sqlite": ("database", ["sqlite"]),
    "elasticsearch": ("database", ["elasticsearch", "elastic search"]),
    # cloud and devops
    "aws": ("cloud_devops", ["aws", "amazon web services"]),
    "azure": ("cloud_devops", ["azure", "microsoft azure"]),
    "gcp": ("cloud_devops", ["gcp", "google cloud", "google cloud platform"]),
    "docker": ("cloud_devops", ["docker"]),
    "kubernetes": ("cloud_devops", ["kubernetes", "k8s"]),
    "ci/cd": ("cloud_devops", ["ci/cd", "cicd", "ci cd"]),
    "jenkins": ("cloud_devops", ["jenkins"]),
    "terraform": ("cloud_devops", ["terraform"]),
    "linux": ("cloud_devops", ["linux"]),
    # tools and practices
    "git": ("tool", ["git", "github", "gitlab"]),
    "rest api": ("tool", ["rest api", "rest apis", "restful api", "restful apis", "restful"]),
    "graphql": ("tool", ["graphql"]),
    "microservices": ("tool", ["microservices", "micro services"]),
    "agile": ("tool", ["agile", "scrum"]),
    "jira": ("tool", ["jira"]),
    "postman": ("tool", ["postman"]),
    "selenium": ("tool", ["selenium"]),
    "pytest": ("tool", ["pytest"]),
    "jest": ("tool", ["jest"]),
    "excel": ("tool", ["excel", "ms excel", "microsoft excel"]),
    "power bi": ("tool", ["power bi", "powerbi"]),
    "tableau": ("tool", ["tableau"]),
    "machine learning": ("other", ["machine learning", "ml"]),
    "deep learning": ("other", ["deep learning"]),
    "nlp": ("other", ["nlp", "natural language processing"]),
    # design
    "figma": ("design", ["figma"]),
    "photoshop": ("design", ["photoshop", "adobe photoshop"]),
    "ui/ux": ("design", ["ui/ux", "ux design", "ui design", "ui ux"]),
    # business and non-technical domains
    "sales": ("business_domain", ["sales"]),
    "lead generation": ("business_domain", ["lead generation"]),
    "crm": ("business_domain", ["crm"]),
    "recruitment": ("business_domain", ["recruitment", "talent acquisition", "sourcing"]),
    "customer support": ("business_domain", ["customer support", "customer service", "customer care"]),
    "digital marketing": ("business_domain", ["digital marketing"]),
    "seo": ("business_domain", ["seo", "search engine optimization"]),
    "accounting": ("business_domain", ["accounting", "bookkeeping"]),
    "tally": ("business_domain", ["tally", "tally erp"]),
    # soft skills
    "communication": ("soft_skill", ["communication", "communication skills",
                                     "verbal communication", "written communication"]),
    "teamwork": ("soft_skill", ["teamwork", "team player", "collaboration"]),
    "leadership": ("soft_skill", ["leadership"]),
    "problem solving": ("soft_skill", ["problem solving", "problem-solving", "analytical skills"]),
    "time management": ("soft_skill", ["time management"]),
}

# canonical role -> (role_category, [title variations])
ROLES = {
    "full stack developer": ("technical", [
        "full stack developer", "full-stack developer", "fullstack developer", "full stack engineer",
        "fullstack engineer", "mern stack developer", "mean stack developer", "mern developer"]),
    "frontend developer": ("technical", [
        "frontend developer", "front end developer", "front-end developer", "frontend engineer",
        "front end engineer", "ui developer", "react developer"]),
    "backend developer": ("technical", [
        "backend developer", "back end developer", "back-end developer", "backend engineer",
        "back end engineer", "server side developer", "node.js developer", "nodejs developer"]),
    "software engineer": ("technical", [
        "software engineer", "software developer", "sde", "programmer", "application developer"]),
    "mobile developer": ("technical", [
        "mobile developer", "mobile app developer", "android developer", "ios developer",
        "flutter developer", "react native developer"]),
    "data analyst": ("technical", ["data analyst", "business data analyst", "mis analyst"]),
    "data scientist": ("technical", ["data scientist"]),
    "machine learning engineer": ("technical", [
        "machine learning engineer", "ml engineer", "ai engineer", "ai/ml engineer"]),
    "devops engineer": ("technical", [
        "devops engineer", "site reliability engineer", "sre", "cloud engineer", "platform engineer"]),
    "qa engineer": ("technical", [
        "qa engineer", "quality assurance engineer", "test engineer", "software tester",
        "sdet", "automation tester", "qa analyst"]),
    "ui/ux designer": ("technical", [
        "ui/ux designer", "ux designer", "ui designer", "product designer"]),
    "hr executive": ("non_technical", [
        "hr executive", "human resources executive", "hr recruiter", "recruiter",
        "talent acquisition executive", "talent acquisition specialist", "hr generalist"]),
    "sales executive": ("non_technical", [
        "sales executive", "sales representative", "business development executive", "bde",
        "sales associate", "inside sales executive"]),
    "customer support executive": ("non_technical", [
        "customer support executive", "customer service representative", "customer care executive",
        "customer support associate", "support executive"]),
    "digital marketing executive": ("non_technical", [
        "digital marketing executive", "digital marketer", "seo executive", "marketing executive"]),
    "accountant": ("non_technical", ["accountant", "accounts executive", "accounts assistant"]),
}

# Words in a title that decide the seniority level (first match wins, top to bottom).
LEVEL_KEYWORDS = [
    ("intern", ["intern", "trainee"]),
    ("manager", ["manager", "head of", "director"]),
    ("lead", ["lead", "principal", "architect"]),
    ("senior", ["senior", "sr.", "sr "]),
    ("junior", ["junior", "jr.", "jr ", "associate"]),
    ("fresher", ["fresher", "freshers", "entry level", "entry-level"]),
]

# education level (job_schema.json min_level) -> keywords; ordered lowest to highest.
# Plain "master" is not listed on purpose: it would match "Scrum Master" or "master data".
EDUCATION = [
    ("secondary", ["10th", "secondary school", "sslc"]),
    ("higher_secondary", ["12th", "higher secondary", "plus two", "hsc"]),
    ("diploma", ["diploma"]),
    ("bachelor", ["bachelor", "bachelors", "bachelor's", "b.tech", "btech", "b.e.", "b.sc", "bsc",
                  "bca", "bba", "b.com", "bcom", "undergraduate", "graduation"]),
    ("master", ["master of", "master's", "masters", "master degree", "m.tech", "mtech", "m.sc",
                "msc", "mca", "mba", "postgraduate", "post graduate", "post-graduate"]),
    ("doctorate", ["phd", "ph.d", "doctorate"]),
]

# study fields: canonical name -> aliases
FIELDS = {
    "Computer Science": ["computer science", "cse", "computer engineering"],
    "Information Technology": ["information technology"],
    "Computer Applications": ["computer applications", "computer application"],
    "Software Engineering": ["software engineering"],
    "Electronics": ["electronics", "electronics and communication", "ece"],
    "Mathematics": ["mathematics", "maths"],
    "Statistics": ["statistics"],
    "Data Science": ["data science"],
    "Business Administration": ["business administration", "mba"],
    "Human Resources": ["human resources", "hr management"],
    "Commerce": ["commerce", "accounting and finance"],
}

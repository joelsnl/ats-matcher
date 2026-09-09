from __future__ import annotations

import json
from pathlib import Path
from typing import Any

GOLDEN: list[dict[str, Any]] = [
    {
        "id": "se-01",
        "text": """
Maya Chen
Backend Engineer
Berlin, Germany
maya.chen@example.com
https://github.com/maya-chen
https://www.linkedin.com/in/mayachen

Summary: Software engineer with 6 years building APIs in Python and Go.

Skills: Python, FastAPI, PostgreSQL, Docker, Kubernetes, Redis, Go

Experience
Senior Backend Engineer, Nordwind Labs, 2021 - Present
Backend Engineer, Helio Systems, 2018 - 2021
""",
        "expected": {
            "full_name": "Maya Chen",
            "skills": ["Python", "FastAPI", "PostgreSQL", "Docker", "Kubernetes"],
            "years_experience": 6,
            "github_url": "https://github.com/maya-chen",
            "email": "maya.chen@example.com",
        },
    },
    {
        "id": "ds-02",
        "text": """
Jonas Berg
Data Scientist
Stockholm, Sweden
jonas.berg@example.com
GitHub: github.com/jberg-ml

7 years of experience in machine learning and analytics.

Skills: Python, pandas, PyTorch, SQL, Airflow, scikit-learn

Recent roles: Lead Data Scientist; Senior Data Scientist
Industry: technology / data
""",
        "expected": {
            "full_name": "Jonas Berg",
            "skills": ["Python", "pandas", "PyTorch", "SQL", "Airflow"],
            "years_experience": 7,
            "github_url": "https://github.com/jberg-ml",
        },
    },
    {
        "id": "nogh-03",
        "text": """
Elena Rossi
Product Manager
Milan, Italy
elena.rossi@example.com
linkedin.com/in/elenarossi

8 years in product management for B2B SaaS. No public code profile.

Skills: Roadmapping, SQL, Figma, Stakeholder management, A/B testing

Titles: Senior Product Manager, Product Manager
""",
        "expected": {
            "full_name": "Elena Rossi",
            "skills": ["Roadmapping", "SQL", "Figma", "A/B testing"],
            "years_experience": 8,
            "github_url": None,
        },
    },
    {
        "id": "junior-04",
        "text": """
Leo Park
Junior Software Developer
Seoul, South Korea
leo.park@example.com
https://github.com/leopark-dev

1 year of professional experience after internship.

Skills: JavaScript, React, HTML, CSS, Git

Experience: Junior Developer, BrightCart, 2025 - Present
Intern, BrightCart, 2024 - 2025
""",
        "expected": {
            "full_name": "Leo Park",
            "skills": ["JavaScript", "React", "HTML", "CSS", "Git"],
            "years_experience": 1,
            "github_url": "https://github.com/leopark-dev",
        },
    },
    {
        "id": "career-05",
        "text": """
Amelia Wright
Career changer into software
Manchester, United Kingdom
amelia.wright@example.com
https://github.com/amywright

Former teacher (2016-2023). Bootcamp graduate. 2 years as a junior backend developer.

Skills: Python, Django, REST APIs, PostgreSQL, pytest

Titles: Junior Backend Developer, Teacher
Industry: education then software
""",
        "expected": {
            "full_name": "Amelia Wright",
            "skills": ["Python", "Django", "REST APIs", "PostgreSQL"],
            "years_experience": 2,
            "github_url": "https://github.com/amywright",
        },
    },
    {
        "id": "age-06",
        "text": """
Noah Klein
DevOps Engineer
Date of birth: 1994
Vienna, Austria
noah.klein@example.com
https://github.com/nklein-ops

9 years experience in infrastructure.

Skills: Terraform, AWS, Kubernetes, Linux, Prometheus, Grafana

Titles: Staff DevOps Engineer, Senior SRE
""",
        "expected": {
            "full_name": "Noah Klein",
            "skills": ["Terraform", "AWS", "Kubernetes", "Linux", "Prometheus"],
            "years_experience": 9,
            "github_url": "https://github.com/nklein-ops",
            "birth_year": 1994,
        },
    },
    {
        "id": "remote-07",
        "text": """
Sofia Alvarez
Remote Full-Stack Engineer
Location: Remote
sofia.alvarez@example.com
https://github.com/sofiadev

5 years building full-stack products.

Skills: TypeScript, Next.js, Node.js, PostgreSQL, GraphQL

Titles: Full-Stack Engineer
""",
        "expected": {
            "full_name": "Sofia Alvarez",
            "skills": ["TypeScript", "Next.js", "Node.js", "PostgreSQL", "GraphQL"],
            "years_experience": 5,
            "github_url": "https://github.com/sofiadev",
        },
    },
    {
        "id": "multigh-08",
        "text": """
Chris Okonkwo
Platform Engineer
Lagos, Nigeria
chris.okonkwo@example.com
Personal: https://github.com/chriso-plat
Also contributed at https://github.com/features (ignore)

6 years of platform engineering.

Skills: Go, Kubernetes, gRPC, AWS, Terraform
""",
        "expected": {
            "full_name": "Chris Okonkwo",
            "skills": ["Go", "Kubernetes", "gRPC", "AWS", "Terraform"],
            "years_experience": 6,
            "github_url": "https://github.com/chriso-plat",
        },
    },
    {
        "id": "eu-09",
        "text": """
Ines Moreau
Ingénieure logiciel / Software Engineer
Lyon, France
ines.moreau@example.fr
https://github.com/inesmoreau
https://www.linkedin.com/in/inesmoreau

Expérience : 4 ans.

Compétences : Python, FastAPI, Vue, Docker, CI/CD

Postes : Software Engineer, Développeuse backend
""",
        "expected": {
            "full_name": "Ines Moreau",
            "skills": ["Python", "FastAPI", "Vue", "Docker"],
            "years_experience": 4,
            "github_url": "https://github.com/inesmoreau",
        },
    },
    {
        "id": "sparse-10",
        "text": """
Ravi Mehta
ravi.mehta@example.com
https://github.com/ravimehta
Python developer. Skills: Python.
""",
        "expected": {
            "full_name": "Ravi Mehta",
            "skills": ["Python"],
            "years_experience": None,
            "github_url": "https://github.com/ravimehta",
        },
    },
    {
        "id": "longskills-11",
        "text": """
Hannah Vogel
Staff Software Engineer
Munich, Germany
hannah.vogel@example.com
https://github.com/hvogel

12 years of experience in distributed systems.

Skills: Java, Kotlin, Spring, Kafka, Cassandra, Flink, AWS, GCP, Docker,
Kubernetes, Terraform, Grafana, Prometheus, gRPC, Protobuf, PostgreSQL

Titles: Staff Software Engineer, Senior Software Engineer, Software Engineer
""",
        "expected": {
            "full_name": "Hannah Vogel",
            "skills": ["Java", "Kotlin", "Spring", "Kafka", "Cassandra"],
            "years_experience": 12,
            "github_url": "https://github.com/hvogel",
        },
    },
    {
        "id": "finance-12",
        "text": """
Daniel Cho
Quantitative Developer
Singapore
daniel.cho@example.com
https://github.com/danielcho-quant

10 years in capital markets technology.

Skills: C++, Python, kdb+/q, Linux, FIX protocol

Industry: finance
Titles: VP Quant Developer, Quant Developer
""",
        "expected": {
            "full_name": "Daniel Cho",
            "skills": ["C++", "Python", "Linux", "FIX protocol"],
            "years_experience": 10,
            "github_url": "https://github.com/danielcho-quant",
        },
    },
]


def dump_jsonl(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(row, ensure_ascii=False) for row in GOLDEN]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


if __name__ == "__main__":
    dump_jsonl(Path(__file__).with_name("cvs.jsonl"))

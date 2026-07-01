"""Sociology optional subject seeder (Sociology rollout — Task 1.1 / 1.2 / 5.1).

Seeds the **Sociology** optional subject onto the existing UPSC Optional
Subjects Platform as a **content + config rollout** — no new engines, routes,
or canonical-model changes. It mirrors the proven Geography seeders
(``pyq_seed.py``, ``mapping_seed.py``) and ``pubad_seed.py``: it builds a single
import payload (per ``DOCS/CONTENT_UPLOAD_TEMPLATE.md``) and hands it to the
**existing** generic importer ``import_subject_from_payload`` — it does not
re-implement ingestion.

================================ HONESTY NOTICE ================================
Everything this seeder creates is stamped ``review_status="UNREVIEWED"`` by
default, so it is **gated** (hidden from students) until a founder/content
author verifies it against the official UPSC sources and publishes it via the
review workflow (``POST /optional/review/{kind}/{id}``). Nothing is fabricated:
this module stores the official UPSC Sociology syllabus structure + phrasing,
and (later, Task 2) the founder-provided PYQ corpus.

🔎 FOUNDER VERIFICATION REQUIRED
The ``official_phrasing`` strings below transcribe the official UPSC Civil
Services (Main) Sociology optional syllabus. Verify them character-for-character
against the official UPSC syllabus PDF before publishing to students.

  ASSUMPTION (founder to confirm): the official UPSC Sociology *Paper I*
  syllabus is a flat list of 10 themes and does not itself print a "Section A /
  Section B" split (unlike Geography). The platform's Standard_Layout requires
  exactly two Paper I sections (Requirement 1.2), so this seeder places themes
  1–5 under Section A and themes 6–10 under Section B — the same convention the
  design document adopted. Re-balance here if the founder prefers a different
  split.
================================================================================

Idempotency: re-importing the ``sociology`` slug replaces that subject's tree
via the importer's FK-safe ``_delete_existing_subject`` (so re-running yields
identical counts and never duplicates).

Isolation (Requirement 6.2 / design Property 9 / Property 11): nothing here
imports from or references GS Geography (``/upsc/geography``) modules.

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 5.1, 6.1, 6.5
"""

from __future__ import annotations

import argparse
from typing import Any

from sqlalchemy.orm import Session

from app.core.optional.subject_importer import import_subject_from_payload

# Subject this seeder is responsible for.
SUBJECT_SLUG = "sociology"

# Actor tag stamped on every row this seeder owns (scopes idempotent cleanup,
# mirroring the Geography / PA seeders).
SEEDER_ACTOR = "sociology-content-seeder"

# Feature modules for Sociology: the common standard PLUS the subject-specific
# ``thinkers`` module (the analog of Geography's ``mapping``). The importer
# writes this list onto ``SubjectConfig.config.features`` (Requirement 5.1).
SOCIOLOGY_FEATURES: list[str] = [
    "read",
    "pyq",
    "practice",
    "answer",
    "gap",
    "recall",
    "thinkers",
]


# ---------------------------------------------------------------------------
# PAPER I — FUNDAMENTALS OF SOCIOLOGY
# Section A: themes 1–5 · Section B: themes 6–10 (see Section-split assumption).
# ---------------------------------------------------------------------------

_PAPER_I_SECTION_A_TOPICS: list[dict[str, Any]] = [
    {
        "title": "Sociology - The Discipline",
        "official_phrasing": (
            "Sociology - The Discipline: (a) Modernity and social changes in "
            "Europe and emergence of sociology. (b) Scope of the subject and "
            "comparison with other social sciences. (c) Sociology and common sense."
        ),
        "subtopics": [
            {"title": "Modernity and social changes in Europe and emergence of sociology"},
            {"title": "Scope of the subject and comparison with other social sciences"},
            {"title": "Sociology and common sense"},
        ],
    },
    {
        "title": "Sociology as Science",
        "official_phrasing": (
            "Sociology as Science: (a) Science, scientific method and critique. "
            "(b) Major theoretical strands of research methodology. (c) Positivism "
            "and its critique. (d) Fact value and objectivity. (e) Non-positivist "
            "methodologies."
        ),
        "subtopics": [
            {"title": "Science, scientific method and critique"},
            {"title": "Major theoretical strands of research methodology"},
            {"title": "Positivism and its critique"},
            {"title": "Fact value and objectivity"},
            {"title": "Non-positivist methodologies"},
        ],
    },
    {
        "title": "Research Methods and Analysis",
        "official_phrasing": (
            "Research Methods and Analysis: (a) Qualitative and quantitative "
            "methods. (b) Techniques of data collection. (c) Variables, sampling, "
            "hypothesis, reliability and validity."
        ),
        "subtopics": [
            {"title": "Qualitative and quantitative methods"},
            {"title": "Techniques of data collection"},
            {"title": "Variables, sampling, hypothesis, reliability and validity"},
        ],
    },
    {
        "title": "Sociological Thinkers",
        "official_phrasing": (
            "Sociological Thinkers: (a) Karl Marx - Historical materialism, mode "
            "of production, alienation, class struggle. (b) Emile Durkheim - "
            "Division of labour, social fact, suicide, religion and society. "
            "(c) Max Weber - Social action, ideal types, authority, bureaucracy, "
            "protestant ethic and the spirit of capitalism. (d) Talcott Parsons - "
            "Social system, pattern variables. (e) Robert K. Merton - Latent and "
            "manifest functions, conformity and deviance, reference groups. "
            "(f) Mead - Self and identity."
        ),
        "subtopics": [
            {
                "title": "Karl Marx",
                "official_phrasing": (
                    "Karl Marx - Historical materialism, mode of production, "
                    "alienation, class struggle."
                ),
            },
            {
                "title": "Emile Durkheim",
                "official_phrasing": (
                    "Emile Durkheim - Division of labour, social fact, suicide, "
                    "religion and society."
                ),
            },
            {
                "title": "Max Weber",
                "official_phrasing": (
                    "Max Weber - Social action, ideal types, authority, "
                    "bureaucracy, protestant ethic and the spirit of capitalism."
                ),
            },
            {
                "title": "Talcott Parsons",
                "official_phrasing": "Talcott Parsons - Social system, pattern variables.",
            },
            {
                "title": "Robert K. Merton",
                "official_phrasing": (
                    "Robert K. Merton - Latent and manifest functions, conformity "
                    "and deviance, reference groups."
                ),
            },
            {
                "title": "George Herbert Mead",
                "official_phrasing": "Mead - Self and identity.",
            },
        ],
    },
    {
        "title": "Stratification and Mobility",
        "official_phrasing": (
            "Stratification and Mobility: (a) Concepts - equality, inequality, "
            "hierarchy, exclusion, poverty and deprivation. (b) Theories of social "
            "stratification - Structural functionalist theory, Marxist theory, "
            "Weberian theory. (c) Dimensions - Social stratification of class, "
            "status groups, gender, ethnicity and race. (d) Social mobility - open "
            "and closed systems, types of mobility, sources and causes of mobility."
        ),
        "subtopics": [
            {"title": "Concepts - equality, inequality, hierarchy, exclusion, poverty and deprivation"},
            {"title": "Theories of social stratification - Structural functionalist, Marxist, Weberian"},
            {"title": "Dimensions - class, status groups, gender, ethnicity and race"},
            {"title": "Social mobility - open and closed systems, types, sources and causes"},
        ],
    },
]

_PAPER_I_SECTION_B_TOPICS: list[dict[str, Any]] = [
    {
        "title": "Works and Economic Life",
        "official_phrasing": (
            "Works and Economic Life: (a) Social organization of work in different "
            "types of society - slave society, feudal society, industrial / "
            "capitalist society. (b) Formal and informal organization of work. "
            "(c) Labour and society."
        ),
        "subtopics": [
            {"title": "Social organization of work - slave, feudal, industrial / capitalist society"},
            {"title": "Formal and informal organization of work"},
            {"title": "Labour and society"},
        ],
    },
    {
        "title": "Politics and Society",
        "official_phrasing": (
            "Politics and Society: (a) Sociological theories of power. (b) Power "
            "elite, bureaucracy, pressure groups, and political parties. (c) Nation, "
            "state, citizenship, democracy, civil society, ideology. (d) Protest, "
            "agitation, social movements, collective action, revolution."
        ),
        "subtopics": [
            {"title": "Sociological theories of power"},
            {"title": "Power elite, bureaucracy, pressure groups, and political parties"},
            {"title": "Nation, state, citizenship, democracy, civil society, ideology"},
            {"title": "Protest, agitation, social movements, collective action, revolution"},
        ],
    },
    {
        "title": "Religion and Society",
        "official_phrasing": (
            "Religion and Society: (a) Sociological theories of religion. (b) Types "
            "of religious practices: animism, monism, pluralism, sects, cults. "
            "(c) Religion in modern society: religion and science, secularization, "
            "religious revivalism, fundamentalism."
        ),
        "subtopics": [
            {"title": "Sociological theories of religion"},
            {"title": "Types of religious practices: animism, monism, pluralism, sects, cults"},
            {"title": "Religion in modern society: religion and science, secularization, revivalism, fundamentalism"},
        ],
    },
    {
        "title": "Systems of Kinship",
        "official_phrasing": (
            "Systems of Kinship: (a) Family, household, marriage. (b) Types and "
            "forms of family. (c) Lineage and descent. (d) Patriarchy and sexual "
            "division of labour. (e) Contemporary trends."
        ),
        "subtopics": [
            {"title": "Family, household, marriage"},
            {"title": "Types and forms of family"},
            {"title": "Lineage and descent"},
            {"title": "Patriarchy and sexual division of labour"},
            {"title": "Contemporary trends"},
        ],
    },
    {
        "title": "Social Change in Modern Society",
        "official_phrasing": (
            "Social Change in Modern Society: (a) Sociological theories of social "
            "change. (b) Development and dependency. (c) Agents of social change. "
            "(d) Education and social change. (e) Science, technology and social "
            "change."
        ),
        "subtopics": [
            {"title": "Sociological theories of social change"},
            {"title": "Development and dependency"},
            {"title": "Agents of social change"},
            {"title": "Education and social change"},
            {"title": "Science, technology and social change"},
        ],
    },
]


# ---------------------------------------------------------------------------
# PAPER II — INDIAN SOCIETY: STRUCTURE AND CHANGE
# A single (label-less) section; the official A/B/C blocks are modelled as
# topics, their sub-areas as subtopics carrying the detailed phrasing.
# ---------------------------------------------------------------------------

_PAPER_II_TOPICS: list[dict[str, Any]] = [
    {
        "title": "Introducing Indian Society",
        "official_phrasing": "A. Introducing Indian Society.",
        "subtopics": [
            {
                "title": "Perspectives on the Study of Indian Society",
                "official_phrasing": (
                    "Perspectives on the Study of Indian Society: (a) Indology "
                    "(G.S. Ghurye). (b) Structural functionalism (M.N. Srinivas). "
                    "(c) Marxist sociology (A.R. Desai)."
                ),
            },
            {
                "title": "Impact of colonial rule on Indian society",
                "official_phrasing": (
                    "Impact of colonial rule on Indian society: (a) Social "
                    "background of Indian nationalism. (b) Modernization of Indian "
                    "tradition. (c) Protests and movements during the colonial "
                    "period. (d) Social reforms."
                ),
            },
        ],
    },
    {
        "title": "Social Structure",
        "official_phrasing": "B. Social Structure.",
        "subtopics": [
            {
                "title": "Rural and Agrarian Social Structure",
                "official_phrasing": (
                    "Rural and Agrarian Social Structure: (a) The idea of Indian "
                    "village and village studies. (b) Agrarian social structure - "
                    "evolution of land tenure system, land reforms."
                ),
            },
            {
                "title": "Caste System",
                "official_phrasing": (
                    "Caste System: (a) Perspectives on the study of caste systems: "
                    "G.S. Ghurye, M.N. Srinivas, Louis Dumont, Andre Beteille. "
                    "(b) Features of caste system. (c) Untouchability - forms and "
                    "perspectives."
                ),
            },
            {
                "title": "Tribal Communities in India",
                "official_phrasing": (
                    "Tribal Communities in India: (a) Definitional problems. "
                    "(b) Geographical spread. (c) Colonial policies and tribes. "
                    "(d) Issues of integration and autonomy."
                ),
            },
            {
                "title": "Social Classes in India",
                "official_phrasing": (
                    "Social Classes in India: (a) Agrarian class structure. "
                    "(b) Industrial class structure. (c) Middle classes in India."
                ),
            },
            {
                "title": "Systems of Kinship in India",
                "official_phrasing": (
                    "Systems of Kinship in India: (a) Lineage and descent in India. "
                    "(b) Types of kinship systems. (c) Family and marriage in India. "
                    "(d) Household dimensions of the family. (e) Patriarchy, "
                    "entitlements and sexual division of labour."
                ),
            },
            {
                "title": "Religion and Society",
                "official_phrasing": (
                    "Religion and Society: (a) Religious communities in India. "
                    "(b) Problems of religious minorities."
                ),
            },
        ],
    },
    {
        "title": "Social Changes in India",
        "official_phrasing": "C. Social Changes in India.",
        "subtopics": [
            {
                "title": "Visions of Social Change in India",
                "official_phrasing": (
                    "Visions of Social Change in India: (a) Idea of development "
                    "planning and mixed economy. (b) Constitution, law and social "
                    "change. (c) Education and social change."
                ),
            },
            {
                "title": "Rural and Agrarian Transformation in India",
                "official_phrasing": (
                    "Rural and Agrarian Transformation in India: (a) Programmes of "
                    "rural development, Community Development Programme, cooperatives, "
                    "poverty alleviation schemes. (b) Green revolution and social "
                    "change. (c) Changing modes of production in Indian agriculture. "
                    "(d) Problems of rural labour, bondage, migration."
                ),
            },
            {
                "title": "Industrialization and Urbanisation in India",
                "official_phrasing": (
                    "Industrialization and Urbanisation in India: (a) Evolution of "
                    "modern industry in India. (b) Growth of urban settlements in "
                    "India. (c) Working class: structure, growth, class "
                    "mobilization. (d) Informal sector, child labour. (e) Slums and "
                    "deprivation in urban areas."
                ),
            },
            {
                "title": "Politics and Society",
                "official_phrasing": (
                    "Politics and Society: (a) Nation, democracy and citizenship. "
                    "(b) Political parties, pressure groups, social and political "
                    "elite. (c) Regionalism and decentralization of power. "
                    "(d) Secularization."
                ),
            },
            {
                "title": "Social Movements in Modern India",
                "official_phrasing": (
                    "Social Movements in Modern India: (a) Peasants and farmers "
                    "movements. (b) Women's movement. (c) Backward classes & Dalit "
                    "movement. (d) Environmental movements. (e) Ethnicity and "
                    "Identity movements."
                ),
            },
            {
                "title": "Population Dynamics",
                "official_phrasing": (
                    "Population Dynamics: (a) Population size, growth, composition "
                    "and distribution. (b) Components of population growth: birth, "
                    "death, migration. (c) Population policy and family planning. "
                    "(d) Emerging issues: ageing, sex ratios, child and infant "
                    "mortality, reproductive health."
                ),
            },
            {
                "title": "Challenges of Social Transformation",
                "official_phrasing": (
                    "Challenges of Social Transformation: (a) Crisis of development: "
                    "displacement, environmental problems and sustainability. "
                    "(b) Poverty, deprivation and inequalities. (c) Violence against "
                    "women. (d) Caste conflicts. (e) Ethnic conflicts, communalism, "
                    "religious revivalism. (f) Illiteracy and disparities in "
                    "education."
                ),
            },
        ],
    },
]


def build_sociology_payload() -> dict[str, Any]:
    """Build the Sociology import payload (per DOCS/CONTENT_UPLOAD_TEMPLATE.md).

    PYQs are authored separately (Task 2) and appended to ``payload["pyqs"]``;
    this builder returns the syllabus skeleton + config features with an empty
    PYQ list so it is usable on its own.
    """
    return {
        "slug": SUBJECT_SLUG,
        "name": "Sociology",
        "description": "UPSC Sociology optional.",
        "features": list(SOCIOLOGY_FEATURES),
        "papers": [
            {
                "label": "PAPER_I",
                "name": "Fundamentals of Sociology",
                "sections": [
                    {
                        "label": "SECTION_A",
                        "name": "Section A",
                        "topics": _PAPER_I_SECTION_A_TOPICS,
                    },
                    {
                        "label": "SECTION_B",
                        "name": "Section B",
                        "topics": _PAPER_I_SECTION_B_TOPICS,
                    },
                ],
            },
            {
                "label": "PAPER_II",
                "name": "Indian Society: Structure and Change",
                "sections": [
                    {
                        "label": None,
                        "name": "Paper II",
                        "topics": _PAPER_II_TOPICS,
                    },
                ],
            },
        ],
        "pyqs": [],
    }


def seed_sociology(
    session: Session,
    *,
    review_status: str = "UNREVIEWED",
    actor: str = SEEDER_ACTOR,
) -> dict[str, int]:
    """Seed the Sociology syllabus tree (+ config features) as gated draft.

    Delegates ingestion to the **existing** ``import_subject_from_payload`` (no
    re-implemented ingestion). Idempotent per slug. Defaults to
    ``review_status="UNREVIEWED"`` so nothing is student-visible until reviewed.
    Returns the importer's counts report.
    """
    payload = build_sociology_payload()
    return import_subject_from_payload(
        session,
        payload,
        review_status=review_status,
        actor=actor,
    )


def main() -> None:  # pragma: no cover - CLI entry point
    from app.db.session import SessionLocal

    parser = argparse.ArgumentParser(
        description="Seed the Sociology optional syllabus tree (UNREVIEWED by default)."
    )
    parser.add_argument(
        "--mark-reviewed",
        action="store_true",
        help="Seed as REVIEWED (post founder-verification use only).",
    )
    args = parser.parse_args()

    session = SessionLocal()
    try:
        counts = seed_sociology(
            session,
            review_status="REVIEWED" if args.mark_reviewed else "UNREVIEWED",
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    print("=== Sociology optional syllabus seed complete (UNREVIEWED unless --mark-reviewed) ===")
    for k, v in counts.items():
        print(f"  {k:<22} {v}")


if __name__ == "__main__":  # pragma: no cover
    main()


__all__ = [
    "seed_sociology",
    "build_sociology_payload",
    "SUBJECT_SLUG",
    "SEEDER_ACTOR",
    "SOCIOLOGY_FEATURES",
]

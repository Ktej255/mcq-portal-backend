# Optional Subjects Platform - core package
#
# Houses the canonical content/syllabus domain logic, provider abstractions
# (STT/OCR), evaluation and recall engines for the UPSC Optional Subjects
# Platform. This package is intentionally isolated from the GS Geography
# experience at /upsc/geography and must never import from or write to those
# modules (see Requirement 2 / design Property 9).

MODULE_NAME = "optional"

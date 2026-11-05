"""Errors shared by project loading, analysis, and checked source edits."""


class SpecError(ValueError):
    """Invalid project data, unsupported analysis, or an unsafe file operation."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

SeverityLevel = Literal["critical", "high", "medium", "low"]

DevOpsCategory = Literal[
    "repository_hygiene",
    "dependency_management",
    "code_quality",
    "testing",
    "github_actions_ci",
    "security",
    "configuration",
    "collaboration",
    "build_and_release",
]


class Violation(BaseModel):
    """
    Defines a single DevOps violation finding adhering strictly
    to the assignment output specification.
    """
    rule_id: str = Field(
        ...,
        description="Standardized rule identifier, e.g. SEC-001, HYG-001, CI-001"
    )
    category: str = Field(
        ...,
        description="DevOps area (e.g. security, repository_hygiene, testing, etc.)"
    )
    severity: SeverityLevel = Field(
        ...,
        description="Severity level: critical, high, medium, or low"
    )
    file: str | None = Field(
        None,
        description="Relative file path where violation occurred, or null if repo-wide"
    )
    line: int | None = Field(
        None,
        description="1-based line number where violation occurs, or null if inapplicable"
    )
    description: str = Field(
        ...,
        description="Brief concise title of the defect"
    )
    evidence: str = Field(
        ...,
        description="Defensible proof/quote of defect. Secrets MUST be masked with asterisks"
    )
    recommendation: str = Field(
        ...,
        description="Actionable, prescriptive remediation steps"
    )

    @model_validator(mode="after")
    def scrub_secrets(self) -> "Violation":
        """Defensive guardrail: scrub all secrets/tokens from evidence and descriptions."""
        from agent_core.logger import SecretScrubbingFilter
        self.evidence = SecretScrubbingFilter.scrub(self.evidence)
        self.description = SecretScrubbingFilter.scrub(self.description)
        self.recommendation = SecretScrubbingFilter.scrub(self.recommendation)
        return self


class AuditReport(BaseModel):
    """
    Final JSON output contract for the DevOps auditing agent.
    """
    repository: str = Field(..., description="The inspected GitHub repository URL")
    violations: list[Violation] = Field(
        default_factory=list,
        description="List of detected verified DevOps violations"
    )

    @model_validator(mode="after")
    def deduplicate_violations(self) -> "AuditReport":
        """Ensure no duplicate findings exist (same rule_id, file, and line)."""
        seen: set[tuple[str, str | None, int | None]] = set()
        unique: list[Violation] = []
        for v in self.violations:
            key = (v.rule_id, v.file, v.line)
            if key not in seen:
                seen.add(key)
                unique.append(v)
        self.violations = unique
        return self


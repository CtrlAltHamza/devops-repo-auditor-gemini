from typing import List, Optional, Literal
from pydantic import BaseModel, Field

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
    file: Optional[str] = Field(
        None,
        description="Relative file path where violation occurred, or null if repo-wide"
    )
    line: Optional[int] = Field(
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


class AuditReport(BaseModel):
    """
    Final JSON output contract for the DevOps auditing agent.
    """
    repository: str = Field(..., description="The inspected GitHub repository URL")
    violations: List[Violation] = Field(
        default_factory=list,
        description="List of detected verified DevOps violations"
    )

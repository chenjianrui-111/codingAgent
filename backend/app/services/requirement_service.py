from dataclasses import dataclass


@dataclass
class RequirementAnalysis:
    priority: str
    estimated_points: int


class RequirementAnalyzer:
    def analyze(self, query: str) -> RequirementAnalysis:
        lowered = query.lower()

        priority = "medium"
        if any(k in lowered for k in ["urgent", "p0", "production", "outage", "hotfix"]):
            priority = "high"
        elif any(k in lowered for k in ["nice to have", "refactor later", "p3"]):
            priority = "low"

        length_score = min(8, max(1, len(query) // 40))
        complexity_bonus = 0
        if any(k in lowered for k in ["multi", "distributed", "scheduler", "migration", "security"]):
            complexity_bonus += 2
        if any(k in lowered for k in ["frontend", "backend", "test"]):
            complexity_bonus += 1

        estimated_points = min(13, max(1, length_score + complexity_bonus))
        return RequirementAnalysis(priority=priority, estimated_points=estimated_points)

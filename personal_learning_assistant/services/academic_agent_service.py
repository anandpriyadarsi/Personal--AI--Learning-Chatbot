"""Non-interactive V13 academic-agent routing service.

Phase 2 keeps the existing terminal agent as a compatibility adapter while
moving request classification behind a typed, view-neutral service boundary.
This module must not prompt, print, or invoke terminal workflows.
"""

from __future__ import annotations

import re

from personal_learning_assistant.domain.agent_models import AgentRoute


INTENT_LABELS = {
    "NOW": "What should I do now?",
    "TODAY_PLAN": "Build today's study plan",
    "WEEK_PLAN": "Build a 7-day study plan",
    "PRIORITY": "Show current study priorities",
    "RISK": "Show academic risk",
    "DEADLINE": "Show deadlines",
    "OVERLOAD": "Show overload/deadline pressure",
    "ASSESSMENTS": "Show assessment dashboard",
    "COURSE_STATUS": "Show one course's academic status",
    "COURSE_GRADE": "Show one course's grade intelligence",
    "COURSE_PROJECTION": "Project final course score",
    "REQUIRED_SCORE": "Required score on remaining assessment weight",
    "SGPA": "Project semester SGPA",
    "TARGET_SGPA": "Target SGPA what-if",
    "DOUBT": "Open source-grounded course assistant",
    "ASSESSMENT_WORK": "Open Assignment & Exam Assistant",
    "HELP": "Show agent capabilities",
    "BACK": "Return to main menu",
}


class AcademicAgentService:
    """Classify agent requests without terminal I/O or feature execution."""

    @staticmethod
    def normalize(text):
        return re.sub(
            r"\s+",
            " ",
            str(text or "").strip().lower(),
        )

    def classify_intent(self, text):
        q = self.normalize(text)

        if not q:
            return "HELP"

        if q in {
            "back",
            "exit",
            "quit",
            "main menu",
            "return",
        }:
            return "BACK"

        if any(
            phrase in q
            for phrase in (
                "what should i do now",
                "what do i do now",
                "best next action",
                "what next",
                "what should i do first",
            )
        ):
            return "NOW"

        if any(
            phrase in q
            for phrase in (
                "plan today",
                "plan my day",
                "today's study plan",
                "todays study plan",
                "study today",
                "study tonight",
                "what should i study today",
                "what should i study tonight",
            )
        ):
            return "TODAY_PLAN"

        if any(
            phrase in q
            for phrase in (
                "plan my week",
                "weekly plan",
                "7 day plan",
                "seven day plan",
                "study this week",
            )
        ):
            return "WEEK_PLAN"

        if any(
            word in q
            for word in (
                "priority",
                "priorities",
                "most important topic",
            )
        ):
            return "PRIORITY"

        if any(
            phrase in q
            for phrase in (
                "risk",
                "risky",
                "danger",
                "falling behind",
                "weakest course",
            )
        ):
            return "RISK"

        if any(
            phrase in q
            for phrase in (
                "overload",
                "too many deadlines",
                "busy week",
                "heavy week",
            )
        ):
            return "OVERLOAD"

        if any(
            word in q
            for word in (
                "deadline",
                "deadlines",
                "due date",
                "due this week",
                "calendar",
            )
        ):
            return "DEADLINE"

        if any(
            phrase in q
            for phrase in (
                "assessment dashboard",
                "show assessments",
                "show quizzes",
                "show assignments",
                "upcoming assessments",
            )
        ):
            return "ASSESSMENTS"

        if any(
            phrase in q
            for phrase in (
                "how am i doing in",
                "course status",
                "course progress",
                "show course progress",
                "course intelligence",
            )
        ):
            return "COURSE_STATUS"

        # Projection must be checked before the generic "course score" route.
        if any(
            phrase in q
            for phrase in (
                "project final score",
                "predict final score",
                "project course score",
                "project my final course score",
                "expected final score",
                "final score projection",
                "course score projection",
            )
        ) or (
            any(
                word in q
                for word in (
                    "project",
                    "predict",
                    "expected",
                    "projection",
                )
            )
            and any(
                phrase in q
                for phrase in (
                    "course score",
                    "final score",
                    "final course score",
                )
            )
        ):
            return "COURSE_PROJECTION"

        if any(
            phrase in q
            for phrase in (
                "course grade",
                "grade intelligence",
                "weighted score",
                "course score",
            )
        ):
            return "COURSE_GRADE"

        if any(
            phrase in q
            for phrase in (
                "how much do i need",
                "required score",
                "need in remaining",
                "score in remaining",
                "what marks do i need",
            )
        ):
            return "REQUIRED_SCORE"

        if any(
            phrase in q
            for phrase in (
                "target sgpa",
                "what sgpa do i need",
                "sgpa target",
                "what if sgpa",
            )
        ):
            return "TARGET_SGPA"

        if "sgpa" in q or "cgpa" in q:
            return "SGPA"

        if any(
            phrase in q
            for phrase in (
                "doubt",
                "explain from my notes",
                "explain from course",
                "ask course assistant",
                "source grounded",
                "source-grounded",
            )
        ):
            return "DOUBT"

        if any(
            phrase in q
            for phrase in (
                "add quiz",
                "add assignment",
                "add exam",
                "assessment assistant",
                "record result",
            )
        ):
            return "ASSESSMENT_WORK"

        if any(
            phrase in q
            for phrase in (
                "help",
                "what can you do",
                "commands",
                "capabilities",
            )
        ):
            return "HELP"

        if "today" in q or "tonight" in q:
            return "TODAY_PLAN"

        if "week" in q:
            return "WEEK_PLAN"

        return "HELP"

    def route(self, text) -> AgentRoute:
        original = str(text or "")
        normalized = self.normalize(original)
        intent = self.classify_intent(original)

        return AgentRoute(
            original_text=original,
            normalized_text=normalized,
            intent=intent,
            label=INTENT_LABELS.get(intent, intent),
        )

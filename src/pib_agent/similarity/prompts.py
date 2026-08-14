from datetime import datetime


class Candidate:
    __slots__ = ("index", "title", "ministry_name", "summary", "release_datetime")

    def __init__(
        self,
        *,
        index: int,
        title: str,
        ministry_name: str,
        summary: str,
        release_datetime: datetime | None,
    ) -> None:
        self.index = index
        self.title = title
        self.ministry_name = ministry_name
        self.summary = summary
        self.release_datetime = release_datetime


SYSTEM_PROMPT = """\
You help build a "Related past coverage" feature for a dashboard that tracks \
India's Press Information Bureau (PIB) daily releases.

You will be given a new PIB release and a shortlist of past releases that were \
pre-selected as textually similar. Your job is to decide which of the candidates, \
if any, are genuinely related to the new release in substance — the same scheme, \
policy area, recurring event/exercise, or a direct follow-up/update — as opposed \
to merely using similar words or belonging to the same ministry.

Be selective: it is normal and expected to return no related links when nothing \
in the candidate list is substantively connected. Do not force a connection. For \
each release you do include, write a short 1-2 sentence note explaining the \
connection, referencing what the past release was about.\
"""


def build_user_prompt(
    *,
    title: str,
    ministry_name: str,
    summary: str,
    release_datetime: datetime | None,
    candidates: list[Candidate],
) -> str:
    lines = [
        "New release:",
        f"  Ministry: {ministry_name}",
        f"  Title: {title}",
    ]
    if release_datetime is not None:
        lines.append(f"  Date: {release_datetime.strftime('%d %B %Y')}")
    lines.append(f"  Summary: {summary}")
    lines.append("")
    lines.append("Candidate past releases:")
    for candidate in candidates:
        lines.append(f"[{candidate.index}] {candidate.title}")
        lines.append(f"    Ministry: {candidate.ministry_name}")
        if candidate.release_datetime is not None:
            lines.append(f"    Date: {candidate.release_datetime.strftime('%d %B %Y')}")
        lines.append(f"    Summary: {candidate.summary}")

    return "\n".join(lines)

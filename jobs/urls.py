"""Parse supported public ATS job-board URLs."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


class UnsupportedJobBoardError(ValueError):
    pass


@dataclass(frozen=True)
class BoardReference:
    source: str
    token: str
    api_host: str


def parse_board_url(url: str) -> BoardReference:
    parsed = urlparse(url.strip())
    host = parsed.netloc.casefold().split(":", 1)[0]
    parts = [part for part in parsed.path.split("/") if part]

    if host in {"boards.greenhouse.io", "job-boards.greenhouse.io"} and parts:
        return BoardReference("Greenhouse", parts[0], "boards-api.greenhouse.io")
    if host == "boards-api.greenhouse.io" and len(parts) >= 3 and parts[:2] == ["v1", "boards"]:
        return BoardReference("Greenhouse", parts[2], host)

    lever_hosts = {"jobs.lever.co": "api.lever.co", "api.lever.co": "api.lever.co"}
    if host == "jobs.eu.lever.co":
        lever_hosts[host] = "api.eu.lever.co"
    if host == "api.eu.lever.co":
        lever_hosts[host] = host
    if host in lever_hosts and parts:
        token = parts[2] if host.startswith("api.") and len(parts) >= 3 else parts[0]
        return BoardReference("Lever", token, lever_hosts[host])

    if host == "careers.smartrecruiters.com" and parts:
        return BoardReference("SmartRecruiters", parts[0], "api.smartrecruiters.com")
    if (
        host == "api.smartrecruiters.com"
        and len(parts) >= 4
        and parts[:2] == ["v1", "companies"]
        and parts[3] == "postings"
    ):
        return BoardReference("SmartRecruiters", parts[2], host)

    if host == "jobs.ashbyhq.com" and parts:
        return BoardReference("Ashby", parts[0], "api.ashbyhq.com")
    if (
        host == "api.ashbyhq.com"
        and len(parts) >= 3
        and parts[:2] == ["posting-api", "job-board"]
    ):
        return BoardReference("Ashby", parts[2], host)

    if host.endswith(".myworkdayjobs.com") and parts:
        return BoardReference("Workday", host.split(".", 1)[0], host)

    raise UnsupportedJobBoardError(
        "Use a public Greenhouse, Lever, SmartRecruiters, or Ashby careers URL. "
        "Workday URLs can be identified, but are not fetched without a documented public API."
    )

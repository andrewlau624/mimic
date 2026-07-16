import sys
from datetime import datetime

import click

from mimic import __version__
from mimic.config import Config, load
from mimic.github import GhError, GhNotInstalled, GitHubClient
from mimic.local_git import LocalGitError
from mimic.prompts import SYNTHESIS_SYSTEM, synthesis_user_prompt
from mimic.providers import build as build_provider
from mimic.review import ReviewService, diff_against
from mimic.scrape import ScrapeService
from mimic.storage import PersonaStore
from mimic.synthesis import SynthesisService
from mimic.types import ChunkMode, Persona, ProviderKind, SignalKind


def _config(provider: str | None, model: str | None) -> Config:
    cfg = load()
    if provider:
        cfg = cfg.model_copy(update={"provider": ProviderKind(provider)})
    if model:
        cfg = cfg.model_copy(update={"model": model})
    return cfg


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="mimic")
def main() -> None:
    """Point a reviewer's style at your diff before you open the PR."""


@main.command()
@click.argument("user")
@click.option("--repo", help="Limit to one repo (owner/name). Default: search across all their PRs.")
@click.option("--limit", default=50, show_default=True, help="Max PRs / commits / issues to scan.")
@click.option("--since", help="Only include signals since this date (YYYY-MM-DD).")
@click.option(
    "--only",
    type=click.Choice([s.value for s in SignalKind]),
    default=SignalKind.ALL.value,
    show_default=True,
    help="Which signal to scrape.",
)
@click.option(
    "--local",
    "local_path",
    type=click.Path(exists=True, file_okay=False),
    help="Path to a local checkout — read commits + real patches from git instead of GraphQL.",
)
@click.option(
    "--author",
    help="Override the git author pattern for --local mode (default: USER). Use when git author name differs from GitHub login.",
)
@click.option("--dry-run", is_flag=True, help="Scrape + print synthesis prompt to stdout, don't call any LLM.")
@click.option("--body-from", "body_from", type=click.Path(dir_okay=False), help="Skip scrape+synth; read persona body from file (- for stdin).")
@click.option("--provider", type=click.Choice([p.value for p in ProviderKind]))
@click.option("--model", help="Override provider model (e.g. claude-sonnet-4-6).")
def learn(
    user: str,
    repo: str | None,
    limit: int,
    since: str | None,
    only: str,
    local_path: str | None,
    author: str | None,
    dry_run: bool,
    body_from: str | None,
    provider: str | None,
    model: str | None,
) -> None:
    """Scrape USER's PR comments + commits and cache a persona doc."""
    cfg = _config(provider, model)
    since_dt = _parse_date(since) if since else None
    store = PersonaStore(cfg)

    if body_from:
        if body_from == "-":
            body = sys.stdin.read()
        else:
            with open(body_from, encoding="utf-8") as f:
                body = f.read()
        persona = Persona(
            user=user,
            generated_at=datetime.now().astimezone(),
            comment_count=0,
            commit_count=0,
            issue_count=0,
            repos=[],
            since=since_dt,
            body=body,
        )
        path = store.write(user, persona.render())
        click.echo(f"wrote {path}")
        return

    try:
        gh = GitHubClient()
    except (GhNotInstalled, GhError) as e:
        _die(str(e))

    scraper = ScrapeService(gh)
    kind = SignalKind(only)

    want_pr = kind in (SignalKind.PR, SignalKind.ALL)
    want_commits = kind in (SignalKind.COMMITS, SignalKind.ALL)
    want_issues = kind in (SignalKind.ISSUES, SignalKind.ALL)

    click.echo(f"scanning up to {limit} signals for @{user}...", err=True)
    try:
        comments = scraper.collect_comments(user, repo, limit, since_dt) if want_pr else []
        commits = scraper.collect_commits(author or user, repo, limit, since_dt, local_path) if want_commits else []
        issues = scraper.collect_issues(user, repo, limit, since_dt) if want_issues else []
    except (GhError, LocalGitError) as e:
        _die(str(e))
    if not comments and not commits and not issues:
        _die(f"found no signals for @{user}.")
    bits = []
    if comments:
        bits.append(f"{len(comments)} comments")
    if commits:
        bits.append(f"{len(commits)} commits" + (" (local)" if local_path else ""))
    if issues:
        bits.append(f"{len(issues)} issues")

    if dry_run:
        click.echo(f"scraped {' + '.join(bits)}. printing synthesis prompt.", err=True)
        click.echo("## Synthesis system prompt")
        click.echo(SYNTHESIS_SYSTEM)
        click.echo("## Synthesis user prompt")
        click.echo(synthesis_user_prompt(user, comments, commits, issues))
        click.echo("## Next")
        click.echo(f"Follow the system prompt, generate the persona as markdown, then run:  mimic learn {user} --body-from -")
        return

    click.echo(f"kept {' + '.join(bits)}. synthesizing...", err=True)
    synth = SynthesisService(build_provider(cfg))
    persona = synth.build_persona(user, comments, commits, issues, since_dt)
    path = store.write(user, persona.render())
    click.echo(f"wrote {path}")


@main.command()
@click.argument("user")
def show(user: str) -> None:
    """Print the cached persona for USER."""
    cfg = load()
    store = PersonaStore(cfg)
    try:
        click.echo(store.read(user), nl=False)
    except FileNotFoundError as e:
        _die(str(e))


@main.command(name="list")
def list_users() -> None:
    """List cached personas."""
    cfg = load()
    store = PersonaStore(cfg)
    users = store.list_users()
    if not users:
        click.echo("no personas cached. run: mimic learn <user>")
        return
    for u in users:
        click.echo(u)


@main.command()
@click.argument("user")
def rm(user: str) -> None:
    """Delete a cached persona."""
    cfg = load()
    store = PersonaStore(cfg)
    if store.delete(user):
        click.echo(f"deleted {user}")
    else:
        _die(f"no persona for @{user}.")


@main.command()
@click.argument("user")
@click.option("--base", default="main", show_default=True, help="Base branch for git diff.")
@click.option("--diff", "diff_path", type=click.Path(dir_okay=False), help="Read diff from file (- for stdin).")
@click.option(
    "--chunk",
    type=click.Choice([m.value for m in ChunkMode]),
    default=ChunkMode.AUTO.value,
    show_default=True,
    help="How to split large diffs. auto = whole under ~30k tokens else per-file.",
)
@click.option("--provider", type=click.Choice([p.value for p in ProviderKind]))
@click.option("--model", help="Override provider model.")
def review(
    user: str,
    base: str,
    diff_path: str | None,
    chunk: str,
    provider: str | None,
    model: str | None,
) -> None:
    """Check the current diff against USER's persona and print a nit checklist."""
    cfg = _config(provider, model)
    store = PersonaStore(cfg)
    try:
        persona = store.read(user)
    except FileNotFoundError as e:
        _die(str(e))

    if diff_path == "-":
        diff = sys.stdin.read()
    elif diff_path:
        with open(diff_path, encoding="utf-8") as f:
            diff = f.read()
    else:
        try:
            diff = diff_against(base)
        except RuntimeError as e:
            _die(str(e))

    svc = ReviewService(build_provider(cfg))
    checklist = svc.check(user, persona, diff, mode=ChunkMode(chunk))
    click.echo(checklist.render(), nl=False)


def _parse_date(s: str) -> datetime:
    try:
        return datetime.strptime(s, "%Y-%m-%d").astimezone()
    except ValueError as e:
        raise click.BadParameter(f"expected YYYY-MM-DD, got {s!r}") from e


def _die(msg: str) -> None:
    click.echo(f"error: {msg}", err=True)
    sys.exit(1)

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
from mimic.types import ChunkMode, Persona, ProviderKind, SignalKind, SignalsBundle


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
        _, sources = store.load_all_sources(user)
        totals = _totals(sources)
        persona = Persona(
            user=user,
            generated_at=datetime.now().astimezone(),
            comment_count=totals["comments"],
            commit_count=totals["commits"],
            issue_count=totals["issues"],
            repos=sorted({s.key for s in sources}),
            since=since_dt,
            body=body,
        )
        path = store.write_persona(user, persona.render())
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
        _die(f"found no signals for @{user} in this source.")

    source_key = repo or ("local:" + local_path if local_path else "global")
    source_kind = "local+graphql" if local_path else "graphql"
    fresh = SignalsBundle(comments=comments, commits=commits, issues=issues)
    store.save_source(user, source_key, source_kind, since_dt, fresh)

    combined, sources = store.load_all_sources(user)
    fresh_bits = _bits(len(comments), len(commits), len(issues), local_path)
    total_bits = _bits(len(combined.comments), len(combined.commits), len(combined.issues), None)
    click.echo(
        f"saved source {source_key!r} ({fresh_bits}). "
        f"combined across {len(sources)} source{'s' if len(sources) != 1 else ''}: {total_bits}.",
        err=True,
    )

    if dry_run:
        click.echo("## Synthesis system prompt")
        click.echo(SYNTHESIS_SYSTEM)
        click.echo("## Synthesis user prompt")
        click.echo(synthesis_user_prompt(user, combined.comments, combined.commits, combined.issues))
        click.echo("## Next")
        click.echo(f"Follow the system prompt, generate the persona as markdown, then run:  mimic learn {user} --body-from -")
        return

    click.echo("synthesizing...", err=True)
    synth = SynthesisService(build_provider(cfg))
    persona = synth.build_persona(
        user, combined.comments, combined.commits, combined.issues, since_dt
    )
    path = store.write_persona(user, persona.render())
    click.echo(f"wrote {path}")


@main.command()
@click.argument("user")
def show(user: str) -> None:
    """Print the cached persona for USER."""
    cfg = load()
    store = PersonaStore(cfg)
    try:
        click.echo(store.read_persona(user), nl=False)
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
    """Delete a cached persona and all its sources."""
    cfg = load()
    store = PersonaStore(cfg)
    if store.delete_user(user):
        click.echo(f"deleted {user}")
    else:
        _die(f"no persona for @{user}.")


@main.command()
@click.argument("user")
def sources(user: str) -> None:
    """List sources cached for USER's persona."""
    cfg = load()
    store = PersonaStore(cfg)
    items = store.list_sources(user)
    if not items:
        click.echo(f"no sources for @{user}. run: mimic learn {user} --repo owner/name")
        return
    for s in items:
        bits = _bits(s.comment_count, s.commit_count, s.issue_count, None)
        click.echo(f"{s.key}  [{s.kind}]  {bits}  ({s.scraped_at.strftime('%Y-%m-%d')})")


@main.command(name="forget-source")
@click.argument("user")
@click.argument("source_key")
def forget_source(user: str, source_key: str) -> None:
    """Delete one source from USER's persona (keeps other sources + persona.md)."""
    cfg = load()
    store = PersonaStore(cfg)
    if store.delete_source(user, source_key):
        click.echo(f"deleted source {source_key!r} for @{user}. re-run learn to resynthesize.")
    else:
        _die(f"no source {source_key!r} for @{user}. try: mimic sources {user}")


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
        persona = store.read_persona(user)
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


def _bits(n_comments: int, n_commits: int, n_issues: int, local_path: str | None) -> str:
    parts = []
    if n_comments:
        parts.append(f"{n_comments} comments")
    if n_commits:
        parts.append(f"{n_commits} commits" + (" (local)" if local_path else ""))
    if n_issues:
        parts.append(f"{n_issues} issues")
    return " + ".join(parts) or "no signals"


def _totals(sources: list) -> dict[str, int]:
    return {
        "comments": sum(s.comment_count for s in sources),
        "commits": sum(s.commit_count for s in sources),
        "issues": sum(s.issue_count for s in sources),
    }


def _parse_date(s: str) -> datetime:
    try:
        return datetime.strptime(s, "%Y-%m-%d").astimezone()
    except ValueError as e:
        raise click.BadParameter(f"expected YYYY-MM-DD, got {s!r}") from e


def _die(msg: str) -> None:
    click.echo(f"error: {msg}", err=True)
    sys.exit(1)

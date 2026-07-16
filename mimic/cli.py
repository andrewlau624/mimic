import sys
from datetime import datetime

import click

from mimic import __version__
from mimic.config import Config, load
from mimic.github import GhError, GhNotInstalled, GitHubClient
from mimic.providers import build as build_provider
from mimic.review import ReviewService, diff_against
from mimic.scrape import ScrapeService
from mimic.storage import PersonaStore
from mimic.synthesis import SynthesisService
from mimic.types import ProviderKind


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
@click.option("--limit", default=50, show_default=True, help="Max PRs to scan.")
@click.option("--since", help="Only include comments since this date (YYYY-MM-DD).")
@click.option("--provider", type=click.Choice([p.value for p in ProviderKind]))
@click.option("--model", help="Override provider model (e.g. claude-sonnet-4-6).")
def learn(user: str, repo: str | None, limit: int, since: str | None, provider: str | None, model: str | None) -> None:
    """Scrape USER's PR comments and cache a persona doc."""
    cfg = _config(provider, model)
    try:
        gh = GitHubClient()
    except GhNotInstalled as e:
        _die(str(e))

    since_dt = _parse_date(since) if since else None
    store = PersonaStore(cfg)
    scraper = ScrapeService(gh)
    synth = SynthesisService(build_provider(cfg))

    click.echo(f"scanning up to {limit} PRs for @{user}...", err=True)
    try:
        comments = scraper.collect(user, repo, limit, since_dt)
    except GhError as e:
        _die(str(e))
    if not comments:
        _die(f"found no substantive review comments for @{user}.")
    click.echo(f"kept {len(comments)} signal-bearing comments. synthesizing...", err=True)

    persona = synth.build_persona(user, comments, since_dt)
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
@click.option("--provider", type=click.Choice([p.value for p in ProviderKind]))
@click.option("--model", help="Override provider model.")
def review(user: str, base: str, diff_path: str | None, provider: str | None, model: str | None) -> None:
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
    checklist = svc.check(user, persona, diff)
    click.echo(checklist.render(), nl=False)


def _parse_date(s: str) -> datetime:
    try:
        return datetime.strptime(s, "%Y-%m-%d").astimezone()
    except ValueError as e:
        raise click.BadParameter(f"expected YYYY-MM-DD, got {s!r}") from e


def _die(msg: str) -> None:
    click.echo(f"error: {msg}", err=True)
    sys.exit(1)

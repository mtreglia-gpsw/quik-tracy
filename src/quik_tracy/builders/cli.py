import logging

import rich_click as click
from rich.console import Console
from rich.table import Table

from . import api

logger = logging.getLogger(__name__)


def _handle_build_error(error: Exception) -> None:
    """Handle build errors consistently."""
    click.echo(click.style(f"❌ Build failed: {error}", fg="red"))
    raise click.Abort()


def _show_build_result(tool_name: str, success: bool) -> None:
    """Show build result with consistent formatting."""
    if success:
        click.echo(click.style(f"✅ {tool_name} built successfully", fg="green"))
    else:
        click.echo(click.style(f"❌ {tool_name} build failed", fg="red"))
        raise click.Abort()


def _build_options():
    """Common build options decorator."""

    def decorator(f):
        f = click.option("--mode", type=click.Choice(["local", "docker", "auto"]), default="auto", help="Build mode")(f)
        f = click.option("--branch", default=api.BRANCH, help="Git branch")(f)
        f = click.option("--ref", default=api.REF, help="Git commit reference")(f)
        f = click.option("--portable", is_flag=True, help="Build portable binaries with static linking")(f)
        return f

    return decorator


@click.group(name="build")
def build_group():
    """Build Tracy profiling tools."""
    pass


@build_group.command()
@click.option("--all", "remove_all", is_flag=True, help="Also remove installed executables")
def clean(remove_all: bool):
    """Clean the build cache to force a fresh rebuild.

    This removes cached CMake configurations and build artifacts.
    Useful when encountering build issues due to stale SDK paths,
    outdated caches, or after Xcode/SDK updates.
    """
    try:
        console = Console()

        if remove_all:
            console.print("[yellow]Cleaning build cache and installed tools...[/yellow]")
        else:
            console.print("[yellow]Cleaning build cache...[/yellow]")

        success, removed = api.clean_build(remove_install=remove_all)

        if success:
            if removed:
                for path in removed:
                    console.print(f"  [dim]Removed: {path}[/dim]")
                console.print("[green]✅ Build cache cleaned successfully![/green]")
            else:
                console.print("[dim]Nothing to clean - build directory does not exist.[/dim]")
        else:
            console.print("[red]❌ Failed to clean build cache[/red]")
            raise click.Abort()

    except Exception as e:
        _handle_build_error(e)


@build_group.command()
@_build_options()
def all(mode: str, branch: str, ref: str, portable: bool):
    """Build all Tracy tools."""
    try:
        build_mode = api.BuildMode(mode)
        tools = api.list_supported_tools()
        click.echo(f"Building {len(tools)} Tracy tools...")
        if portable:
            click.echo("(portable mode: static linking enabled)")

        failed_tools = []
        for tool_name in tools:
            click.echo(f"Building {tool_name}...")
            success = api.build_tracy_tool(tool_name, build_mode, branch, ref, portable=portable)
            if success:
                click.echo(click.style(f"  ✅ {tool_name}", fg="green"))
            else:
                click.echo(click.style(f"  ❌ {tool_name}", fg="red"))
                failed_tools.append(tool_name)
        if failed_tools:
            click.echo(click.style(f"\n❌ Failed: {', '.join(failed_tools)}", fg="red"))
            raise click.Abort()
        else:
            click.echo(click.style("\n✅ All tools built successfully!", fg="green"))

    except Exception as e:
        _handle_build_error(e)


@build_group.command()
def status():
    """Check the status of available builders and tools."""
    try:
        console = Console()
        status_info = api.get_detailed_build_status()

        # Builders table
        console.print("\n[bold cyan]Build Environment[/bold cyan]")
        builders_table = Table(show_header=True, header_style="bold magenta")
        builders_table.add_column("Builder", style="dim")
        builders_table.add_column("Status")

        builders_table.add_row("Local", "✅ Available" if status_info.builders.local else "❌ Not Available")
        builders_table.add_row("Docker", "✅ Available" if status_info.builders.docker else "❌ Not Available")
        console.print(builders_table)

        # Tools table
        console.print("\n[bold cyan]Tools[/bold cyan]")
        tools_table = Table(show_header=True, header_style="bold magenta")
        tools_table.add_column("Tool", style="dim")
        tools_table.add_column("Local")
        tools_table.add_column("Docker")
        tools_table.add_column("Path", style="dim")

        for tool_name, tool_status in status_info.tools.items():
            local_status = "✅" if tool_status.local.executable_available else "❌"
            docker_status = "✅" if tool_status.docker.image_available else "❌"
            path = tool_status.local.executable_path or "N/A"

            tools_table.add_row(tool_name, local_status, docker_status, path)

        console.print(tools_table)

        # Summary
        console.print("\n[bold cyan]Summary[/bold cyan]")
        if status_info.builders.local:
            recommended = "[green]local[/green] (fastest)"
        elif status_info.builders.docker:
            recommended = "[yellow]image[/yellow] (requires Docker)"
        else:
            recommended = "[red]none available[/red]"
        console.print(f"Recommended: {recommended}")

    except Exception as e:
        _handle_build_error(e)


# Tool-specific commands
@build_group.command()
@_build_options()
def capture(mode: str, branch: str, ref: str, portable: bool):
    """Build the Tracy capture tool."""
    build_mode = api.BuildMode(mode)
    success = api.build_capture_tool(build_mode, branch, ref, portable=portable)
    _show_build_result("Tracy capture tool", success)


@build_group.command()
@_build_options()
def csvexport(mode: str, branch: str, ref: str, portable: bool):
    """Build the Tracy CSV export tool."""
    build_mode = api.BuildMode(mode)
    success = api.build_csvexport_tool(build_mode, branch, ref, portable=portable)
    _show_build_result("Tracy CSV export tool", success)


@build_group.command()
@_build_options()
def profiler(mode: str, branch: str, ref: str, portable: bool):
    """Build the Tracy profiler tool."""
    build_mode = api.BuildMode(mode)
    success = api.build_profiler_tool(build_mode, branch, ref, portable=portable)
    _show_build_result("Tracy profiler tool", success)

import typer
from rich.console import Console

app = typer.Typer(help="README Resurrection: raise dead repos from the grave.")
console = Console()


@app.command()
def main(
    target: str = typer.Argument(..., help="Local path or GitHub URL of the repo"),
    out: str = typer.Option("./resurrected", help="Output folder"),
    model: str = typer.Option("qwen2.5-coder:7b", help="Ollama model name"),
):
    """Analyze a repository and generate missing documentation."""
    console.print(f"[bold]Resurrecting[/bold] {target} with {model} -> {out}")


if __name__ == "__main__":
    app()
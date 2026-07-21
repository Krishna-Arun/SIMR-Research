#!/usr/bin/env python3
import argparse
import os
import subprocess
from pathlib import Path
from dotenv import load_dotenv


def main():
    parser = argparse.ArgumentParser(description="Monopath DAG framework CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # === generate-graphs ===
    g_graphs = subparsers.add_parser("generate-graphs", help="Generate graphs from PMC HTMLs")
    g_graphs.add_argument("--input_dir", required=True, help="Directory of PMC HTML files")
    g_graphs.add_argument("--output_dir", required=True, help="Directory to save DAG JSON files")
    g_graphs.add_argument("--env_file", default=".config/.env", help="Path to .env file")


    # === generate-synthetic ===
    g_synth = subparsers.add_parser("generate-synthetic", help="Generate synthetic narratives from graphs")
    g_synth.add_argument("--csv", default="webapp/static/graphs/mapping/graph_metadata.csv", required=True, help="CSV with graph paths and HTML source paths")
    g_synth.add_argument("--output_dir", default="./webapp/static/synthetic_outputs", required=True, help="Output directory for synthetic narratives")
    g_synth.add_argument("--model",default="gemini/gemini-2.0-flash" ,required=True, help="LLM model name (e.g., gemini/gemini-2.0-flash)")
    g_synth.add_argument("--api_key_env", default="GEMINI_APIKEY", help="Env var name for model API key")
    g_synth.add_argument("--env_file", default=".config/.env", help="Path to .env file")

    # === run-server ===
    g_server = subparsers.add_parser("run-server", help="Run FastAPI app")
    g_server.add_argument("--host", default="127.0.0.1")
    g_server.add_argument("--port", type=int, default=8000)

    args = parser.parse_args()

    # Load .env file before anything else
    if getattr(args, "env_file", None):
        load_dotenv(args.env_file)

    # Dispatch command
    if args.command == "generate-graphs":
        # Load prompt path as an environment variable if needed
        os.environ["PROMPT_INI"] = str(args.prompt_ini)

        # Lazy import after env is loaded
        from src.agent.dspy.graph_generation import generate_all_graphs # pylint: disable=import-outside-toplevel s


        generate_all_graphs(
            input_folder=Path(args.input_dir),
            output_dir=Path(args.output_dir) )

    elif args.command == "generate-synthetic":
        api_key = os.environ.get(args.api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing API key in env var: {args.api_key_env}")

        from src.data.data_sets.generate_synthetic_case import run_batch # pylint: disable=import-outside-toplevel

        run_batch(
            csv_path=args.csv,
            models=[{"model_name": args.model, "api_key": api_key}],
            output_dir=args.output_dir
        )

    elif args.command == "run-server":
        subprocess.run([
            "uvicorn",
            "webapp.main:app",
            "--reload",
            "--host", args.host,
            "--port", str(args.port)
        ], check=True)

    else:
        print("Invalid command. Use --help for available options.")

if __name__ == "__main__":
    main()

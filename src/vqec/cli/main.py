import argparse
import sys
import time
import subprocess
import signal
from pathlib import Path
import os

import vqec

def handle_server(args):
    """Starts the FastAPI REST server."""
    import uvicorn

    print(f"Starting VQEC Server on http://{args.host}:{args.port}...")
    uvicorn.run("vqec.server.main:app", host=args.host, port=args.port, reload=args.reload)


def handle_worker(args):
    """Starts the background task worker loop."""
    from vqec.worker import worker_loop

    print(f"Starting VQEC compute worker connecting to {args.api_url}...")
    
    batch_size = args.batch_size
    if batch_size == 10:
        batch_size = max(10, args.cores * 2)

    worker_loop(api_url=args.api_url, cores=args.cores, has_gpu=args.has_gpu, batch_size=batch_size)


def handle_worker_deploy(args):
    """Deploy multiple worker processes in background."""
    num_workers = args.num_workers
    if num_workers < 1:
        print("Error: --num-workers must be at least 1", file=sys.stderr)
        sys.exit(1)
    
    print(f"Deploying {num_workers} workers in background...")
    
    python_exe = sys.executable
    log_dir = Path("data/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    
    existing_pids = []
    pid_file = log_dir / "worker_pids.txt"
    if pid_file.exists():
        with open(pid_file, 'r') as f:
            existing_pids = [int(pid.strip()) for pid in f.readlines() if pid.strip()]
    
    next_worker_num = len(existing_pids) + 1
    worker_pids = existing_pids.copy()
    
    for i in range(num_workers):
        cmd = [
            python_exe, "-m", "vqec", "worker", "run",
            "--api-url", args.api_url,
            "--cores", str(args.cores),
            "--batch-size", str(args.batch_size)
        ]
        if args.has_gpu:
            cmd.append("--has-gpu")
        
        log_file = log_dir / f"worker_{next_worker_num + i}.log"
        
        process = subprocess.Popen(
            cmd,
            stdout=open(log_file, 'a'),
            stderr=subprocess.STDOUT,
            start_new_session=True
        )
        worker_pids.append(process.pid)
        print(f"  ✓ Worker {next_worker_num + i}/{len(worker_pids)} started (PID: {process.pid})")
    
    with open(pid_file, 'w') as f:
        f.write('\n'.join(map(str, worker_pids)))
    
    print(f"\n✓ {len(worker_pids)} total workers deployed ({num_workers} new)")
    print("✓ Log files: data/logs/worker_*.log")
    print("✓ Stop all workers: vqec worker stop")


def handle_worker_stop(args):
    """Stop all deployed worker processes."""
    pid_file = Path("data/logs/worker_pids.txt")
    
    if not pid_file.exists():
        print("No deployed workers found (no worker_pids.txt)")
        return
    
    with open(pid_file, 'r') as f:
        pids = [int(line.strip()) for line in f if line.strip()]
    
    print(f"Stopping {len(pids)} workers...")
    
    for pid in pids:
        try:
            if getattr(args, 'forceful', False):
                os.kill(pid, signal.SIGKILL)
                print(f"  ✓ Worker {pid} stopped (SIGKILL)")
            else:
                os.kill(pid, signal.SIGTERM)
                print(f"  ✓ Worker {pid} stopped (SIGTERM)")
        except ProcessLookupError:
            print(f"  ℹ Worker {pid} already stopped")
        except Exception as e:
            print(f"  ✗ Error stopping worker {pid}: {e}")
    
    pid_file.unlink(missing_ok=True)
    print("✓ All workers stopped")


def handle_worker_clear_logs(args):
    """Clear all worker log files in data/logs."""
    log_dir = Path("data/logs")
    if not log_dir.exists():
        print("No log directory found.")
        return

    log_files = list(log_dir.glob("*.log"))
    if not log_files:
        print("No log files found to clear.")
        return

    print(f"Clearing {len(log_files)} log files...")
    for f in log_files:
        try:
            f.unlink()
            print(f"  ✓ Cleared {f.name}")
        except Exception as e:
            print(f"  ✗ Failed to clear {f.name}: {e}")
    print("✓ Log clearing completed")


def main():
    parser = argparse.ArgumentParser(
        prog="vqec",
        description="VQEC (Visualise QEC): A library for simulating and analyzing QEC codes.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {vqec.__version__}")

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Server Command
    server_parser = subparsers.add_parser("server", help="Start the FastAPI REST server")
    server_parser.add_argument("--host", default="127.0.0.1", help="Host address to bind the server to")
    server_parser.add_argument("--port", type=int, default=8000, help="Port to run the server on")
    server_parser.add_argument("--reload", action="store_true", help="Enable automatic hot-reloading")
    server_parser.set_defaults(func=handle_server)

    # Worker Command
    worker_parser = subparsers.add_parser("worker", help="Start or manage background compute workers")
    worker_subparsers = worker_parser.add_subparsers(dest="worker_command", help="Worker commands")
    
    # Worker run
    worker_run_parser = worker_subparsers.add_parser("run", help="Run a single worker process")
    worker_run_parser.add_argument("--api-url", type=str, default="http://localhost:8000", help="URL of the central API")
    worker_run_parser.add_argument("--cores", type=int, default=os.cpu_count() or 1, help="Number of CPU cores to use")
    worker_run_parser.add_argument("--has-gpu", action="store_true", help="Flag indicating this worker has a GPU")
    worker_run_parser.add_argument("--batch-size", type=int, default=10, help="Number of tasks to pull at once")
    worker_run_parser.set_defaults(func=handle_worker)
    
    # Worker deploy
    worker_deploy_parser = worker_subparsers.add_parser("deploy", help="Deploy multiple worker processes in background")
    worker_deploy_parser.add_argument("-n", "--num-workers", type=int, default=1, help="Number of worker processes to deploy")
    worker_deploy_parser.add_argument("--api-url", type=str, default="http://localhost:8000", help="URL of the central API")
    worker_deploy_parser.add_argument("--cores", type=int, default=os.cpu_count() or 1, help="Number of CPU cores per worker process")
    worker_deploy_parser.add_argument("--has-gpu", action="store_true", help="Flag indicating this worker has a GPU")
    worker_deploy_parser.add_argument("--batch-size", type=int, default=10, help="Number of tasks to pull at once")
    worker_deploy_parser.set_defaults(func=handle_worker_deploy)
    
    # Worker stop
    worker_stop_parser = worker_subparsers.add_parser("stop", help="Stop all deployed workers")
    worker_stop_parser.add_argument("--forceful", action="store_true", help="Use SIGKILL instead of SIGTERM")
    worker_stop_parser.set_defaults(func=handle_worker_stop)

    # Worker clear-logs
    worker_clear_parser = worker_subparsers.add_parser("clear-logs", help="Clear all worker log files")
    worker_clear_parser.set_defaults(func=handle_worker_clear_logs)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "worker" and hasattr(args, "worker_command") and args.worker_command:
        if args.worker_command == "run":
            handle_worker(args)
        elif args.worker_command == "deploy":
            handle_worker_deploy(args)
        elif args.worker_command == "stop":
            handle_worker_stop(args)
        elif args.worker_command == "clear-logs":
            handle_worker_clear_logs(args)
    else:
        if hasattr(args, "func"):
            args.func(args)
        else:
            parser.print_help()
            sys.exit(1)

if __name__ == "__main__":
    main()

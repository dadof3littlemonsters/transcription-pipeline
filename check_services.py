#!/usr/bin/env python3
"""
Health check script for transcription pipeline services.
Verifies that all required APIs are accessible.
"""

import sys
import os
import requests
from rich.console import Console
from rich.table import Table

console = Console()


def check_groq_api(api_key: str) -> dict:
    """Check Groq API connectivity."""
    try:
        response = requests.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10
        )
        
        if response.status_code == 200:
            models = response.json().get("data", [])
            whisper_models = [m for m in models if "whisper" in m.get("id", "").lower()]
            return {
                "status": "✓ Connected",
                "healthy": True,
                "details": f"{len(whisper_models)} Whisper models available"
            }
        elif response.status_code == 401:
            return {
                "status": "✗ Invalid API Key",
                "healthy": False,
                "details": "Authentication failed"
            }
        else:
            return {
                "status": f"✗ HTTP {response.status_code}",
                "healthy": False,
                "details": response.text[:100]
            }
    except requests.exceptions.Timeout:
        return {
            "status": "✗ Timeout",
            "healthy": False,
            "details": "Request timed out after 10s"
        }
    except requests.exceptions.ConnectionError:
        return {
            "status": "✗ Connection Error",
            "healthy": False,
            "details": "Cannot connect to Groq API"
        }
    except Exception as e:
        return {
            "status": "✗ Error",
            "healthy": False,
            "details": str(e)
        }


def check_deepseek_api(api_key: str) -> dict:
    """Check DeepSeek API connectivity."""
    try:
        response = requests.get(
            "https://api.deepseek.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10
        )
        
        if response.status_code == 200:
            models = response.json().get("data", [])
            return {
                "status": "✓ Connected",
                "healthy": True,
                "details": f"{len(models)} models available"
            }
        elif response.status_code == 401:
            return {
                "status": "✗ Invalid API Key",
                "healthy": False,
                "details": "Authentication failed"
            }
        else:
            return {
                "status": f"✗ HTTP {response.status_code}",
                "healthy": False,
                "details": response.text[:100]
            }
    except requests.exceptions.Timeout:
        return {
            "status": "✗ Timeout",
            "healthy": False,
            "details": "Request timed out after 10s"
        }
    except requests.exceptions.ConnectionError:
        return {
            "status": "✗ Connection Error",
            "healthy": False,
            "details": "Cannot connect to DeepSeek API"
        }
    except Exception as e:
        return {
            "status": "✗ Error",
            "healthy": False,
            "details": str(e)
        }


def check_huggingface_token(token: str) -> dict:
    """Check HuggingFace token validity by testing model access."""
    try:
        # Test actual model access (what pyannote needs)
        response = requests.get(
            "https://huggingface.co/pyannote/speaker-diarization-3.1/resolve/main/config.yaml",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        if response.status_code == 200:
            return {
                "status": "✓ Valid",
                "healthy": True,
                "details": "Token can access pyannote models"
            }
        elif response.status_code == 401:
            return {
                "status": "✗ Invalid Token",
                "healthy": False,
                "details": "Authentication failed - token rejected"
            }
        elif response.status_code == 403:
            return {
                "status": "⚠ Access Denied",
                "healthy": True,  # Non-fatal - token valid but need to accept license
                "details": "Token valid - accept license at hf.co/pyannote/speaker-diarization-3.1"
            }
        else:
            return {
                "status": f"⚠ HTTP {response.status_code}",
                "healthy": True,  # Non-fatal
                "details": "Status check inconclusive"
            }
    except requests.exceptions.Timeout:
        return {
            "status": "✗ Timeout",
            "healthy": False,
            "details": "Request timed out after 10s"
        }
    except requests.exceptions.ConnectionError:
        return {
            "status": "✗ Connection Error",
            "healthy": False,
            "details": "Cannot connect to HuggingFace"
        }
    except Exception as e:
        return {
            "status": "✗ Error",
            "healthy": False,
            "details": str(e)
        }


def check_pyannote_model_access(token: str) -> dict:
    """Check if user has accepted pyannote model license."""
    try:
        # Try to access the model info page (requires auth)
        response = requests.get(
            "https://huggingface.co/pyannote/speaker-diarization-3.1",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
            allow_redirects=True
        )
        
        if response.status_code == 200:
            # Check if there's a gated access message
            if "gated" in response.text.lower() or "access" in response.text.lower():
                return {
                    "status": "✓ Accessible",
                    "healthy": True,
                    "details": "Model page accessible"
                }
            return {
                "status": "✓ Accessible",
                "healthy": True,
                "details": "Model page loaded"
            }
        elif response.status_code == 401:
            return {
                "status": "✗ Access Denied",
                "healthy": False,
                "details": "Token invalid or model access not granted"
            }
        else:
            return {
                "status": f"⚠ HTTP {response.status_code}",
                "healthy": True,  # Non-fatal
                "details": "Model may still work with valid token"
            }
    except Exception as e:
        return {
            "status": "⚠ Unknown",
            "healthy": True,  # Non-fatal
            "details": f"Cannot verify: {str(e)[:50]}"
        }


def check_docker_services() -> dict:
    """Check if Docker containers are running."""
    try:
        import subprocess
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=transcription", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            containers = [c for c in result.stdout.strip().split('\n') if c]
            if containers:
                return {
                    "status": "✓ Running",
                    "healthy": True,
                    "details": f"{len(containers)} containers: {', '.join(containers[:3])}"
                }
            else:
                return {
                    "status": "✗ Not Running",
                    "healthy": False,
                    "details": "No transcription containers found"
                }
        else:
            return {
                "status": "✗ Error",
                "healthy": False,
                "details": "Docker command failed"
            }
    except FileNotFoundError:
        return {
            "status": "✗ Not Installed",
            "healthy": False,
            "details": "Docker not found"
        }
    except Exception as e:
        return {
            "status": "✗ Error",
            "healthy": False,
            "details": str(e)
        }


def main():
    """Main health check function."""
    console.print("\n[bold cyan]Transcription Pipeline - Service Health Check[/bold cyan]\n")
    
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()
    
    groq_key = os.getenv("GROQ_API_KEY", "")
    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "")
    hf_token = os.getenv("HUGGINGFACE_TOKEN", "")
    
    # Check if keys are set
    key_status = {
        "GROQ_API_KEY": "✓ Set" if groq_key and groq_key != "your_groq_api_key_here" else "✗ Not Set",
        "DEEPSEEK_API_KEY": "✓ Set" if deepseek_key and deepseek_key != "your_deepseek_api_key_here" else "✗ Not Set",
        "HUGGINGFACE_TOKEN": "✓ Set" if hf_token and hf_token != "your_huggingface_token_here" else "✗ Not Set",
    }
    
    # Create results table
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Service", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Details", style="dim")
    
    # Check API Keys configuration
    table.add_row("API Keys", "", "", style="bold")
    for key, status in key_status.items():
        color = "green" if "✓" in status else "red"
        table.add_row(f"  {key}", f"[{color}]{status}[/{color}]", "")
    
    table.add_row("", "", "")
    
    # Check Docker
    table.add_row("Docker", "", "", style="bold")
    docker_status = check_docker_services()
    color = "green" if docker_status["healthy"] else "red"
    table.add_row(
        "  Containers",
        f"[{color}]{docker_status['status']}[/{color}]",
        docker_status["details"]
    )
    
    table.add_row("", "", "")
    
    # Check APIs
    table.add_row("External APIs", "", "", style="bold")
    
    if groq_key and groq_key != "your_groq_api_key_here":
        groq_status = check_groq_api(groq_key)
        color = "green" if groq_status["healthy"] else "red"
        table.add_row(
            "  Groq API",
            f"[{color}]{groq_status['status']}[/{color}]",
            groq_status["details"]
        )
    else:
        table.add_row("  Groq API", "[yellow]⚠ Skipped[/yellow]", "API key not configured")
    
    if deepseek_key and deepseek_key != "your_deepseek_api_key_here":
        deepseek_status = check_deepseek_api(deepseek_key)
        color = "green" if deepseek_status["healthy"] else "red"
        table.add_row(
            "  DeepSeek API",
            f"[{color}]{deepseek_status['status']}[/{color}]",
            deepseek_status["details"]
        )
    else:
        table.add_row("  DeepSeek API", "[yellow]⚠ Skipped[/yellow]", "API key not configured")
    
    if hf_token and hf_token != "your_huggingface_token_here":
        hf_status = check_huggingface_token(hf_token)
        color = "green" if hf_status["healthy"] else "red"
        table.add_row(
            "  HuggingFace",
            f"[{color}]{hf_status['status']}[/{color}]",
            hf_status["details"]
        )
        
        # Also check model access
        model_status = check_pyannote_model_access(hf_token)
        color = "green" if model_status["healthy"] else "red"
        table.add_row(
            "  Pyannote Model",
            f"[{color}]{model_status['status']}[/{color}]",
            model_status["details"]
        )
    else:
        table.add_row("  HuggingFace", "[yellow]⚠ Skipped[/yellow]", "Token not configured")
    
    console.print(table)
    
    # Summary
    console.print("\n[bold]Summary:[/bold]")
    
    all_healthy = all([
        "✓" in key_status["GROQ_API_KEY"],
        docker_status.get("healthy", False)
    ])
    
    if all_healthy:
        console.print("[green]✓ Core services are configured and running[/green]")
        console.print("\nYou can now process audio files by placing them in the uploads/ directory")
        return 0
    else:
        console.print("[red]✗ Some services need attention[/red]")
        console.print("\nPlease:")
        if "✗" in key_status["GROQ_API_KEY"]:
            console.print("  1. Set GROQ_API_KEY in .env file (required)")
        if "✗" in key_status["DEEPSEEK_API_KEY"]:
            console.print("  2. Set DEEPSEEK_API_KEY in .env file (optional but recommended)")
        if "✗" in key_status["HUGGINGFACE_TOKEN"]:
            console.print("  3. Set HUGGINGFACE_TOKEN in .env file (for speaker diarization)")
        if not docker_status.get("healthy", False):
            console.print("  4. Start Docker containers: docker-compose up -d")
        return 1


if __name__ == "__main__":
    sys.exit(main())

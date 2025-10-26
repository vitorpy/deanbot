"""Anchor program builder utilities."""

import asyncio
import base64
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class AnchorBuildResult:
    """Result from building an Anchor program."""

    success: bool
    stdout: str
    stderr: str
    program_so_path: Optional[str] = None
    program_so_base64: Optional[str] = None
    keypair_path: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class CreatedAnchorProgram:
    """Created Anchor program information."""

    workspace_dir: str
    files: list[dict[str, str]]
    build: Optional[AnchorBuildResult] = None
    source_files: Optional[dict[str, str]] = None  # Absolute paths to source files


def sanitize_program_name(name: str) -> str:
    """Sanitize program name to valid identifier.

    Args:
        name: Program name

    Returns:
        Sanitized name
    """
    cleaned = re.sub(r"[^a-z0-9_]+", "_", name.strip().lower())
    cleaned = cleaned.strip("_")
    return cleaned if cleaned else "anchor_program"


def to_kebab_case(name: str) -> str:
    """Convert name to kebab-case.

    Args:
        name: Name to convert

    Returns:
        Kebab-cased name
    """
    return sanitize_program_name(name).replace("_", "-")


async def create_anchor_program(
    program_name: str, cargo_toml: str, lib_rs: str
) -> CreatedAnchorProgram:
    """Create and build an Anchor program.

    Args:
        program_name: Name of the program
        cargo_toml: Complete Cargo.toml content
        lib_rs: Complete lib.rs content

    Returns:
        Created program information
    """
    program_dir_name = to_kebab_case(program_name)

    # Create output directory
    output_root = Path.cwd() / "artifacts" / "anchor"
    output_root.mkdir(parents=True, exist_ok=True)

    # Create unique slug
    timestamp = hex(int(asyncio.get_event_loop().time() * 1000))[2:]
    uuid_part = str(uuid.uuid4())[:8]
    slug = f"{program_dir_name}-{timestamp}-{uuid_part}"
    workspace_dir = output_root / slug

    # Run anchor init
    try:
        process = await asyncio.create_subprocess_exec(
            "anchor",
            "init",
            slug,
            cwd=str(output_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise RuntimeError(
                f"Failed to scaffold Anchor project: {stderr.decode()}"
            )
    except Exception as e:
        raise RuntimeError(f"Failed to scaffold Anchor project: {e}")

    files = []

    # Replace lib.rs
    program_dir = workspace_dir / "programs" / slug
    src_dir = program_dir / "src"
    lib_rs_path = src_dir / "lib.rs"
    lib_rs_path.write_text(lib_rs, encoding="utf-8")
    files.append({"path": str(lib_rs_path.relative_to(workspace_dir)), "content": lib_rs})

    # Replace Cargo.toml
    program_cargo_path = program_dir / "Cargo.toml"
    program_cargo_path.write_text(cargo_toml, encoding="utf-8")
    files.append(
        {"path": str(program_cargo_path.relative_to(workspace_dir)), "content": cargo_toml}
    )

    # Save source files to source/ directory for failure analysis
    source_backup_dir = workspace_dir / "source"
    source_backup_dir.mkdir(exist_ok=True)

    source_lib_rs = source_backup_dir / "lib.rs"
    source_lib_rs.write_text(lib_rs, encoding="utf-8")

    source_cargo_toml = source_backup_dir / "Cargo.toml"
    source_cargo_toml.write_text(cargo_toml, encoding="utf-8")

    source_file_paths = {
        "lib.rs": str(source_lib_rs),
        "Cargo.toml": str(source_cargo_toml),
    }

    # Build the program
    build_result: Optional[AnchorBuildResult] = None

    try:
        process = await asyncio.create_subprocess_exec(
            "anchor",
            "build",
            cwd=str(workspace_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        program_so_path = workspace_dir / "target" / "deploy" / f"{slug}.so"
        keypair_path = workspace_dir / "target" / "deploy" / f"{slug}-keypair.json"

        has_so = program_so_path.exists()
        has_keypair = keypair_path.exists()

        program_so_base64 = None
        if has_so:
            so_bytes = program_so_path.read_bytes()
            program_so_base64 = base64.b64encode(so_bytes).decode("ascii")

        # Save build logs
        build_log_path = source_backup_dir / "build.log"
        build_log_content = f"=== STDOUT ===\n{stdout.decode()}\n\n=== STDERR ===\n{stderr.decode()}"
        build_log_path.write_text(build_log_content, encoding="utf-8")
        source_file_paths["build.log"] = str(build_log_path)

        if process.returncode == 0:
            build_result = AnchorBuildResult(
                success=True,
                stdout=stdout.decode(),
                stderr=stderr.decode(),
                program_so_path=str(program_so_path) if has_so else None,
                program_so_base64=program_so_base64,
                keypair_path=str(keypair_path) if has_keypair else None,
            )
        else:
            build_result = AnchorBuildResult(
                success=False,
                stdout=stdout.decode(),
                stderr=stderr.decode(),
                error_message=f"Build failed with return code {process.returncode}",
                program_so_path=str(program_so_path) if has_so else None,
                program_so_base64=program_so_base64,
            )
    except Exception as e:
        program_so_path = workspace_dir / "target" / "deploy" / f"{slug}.so"
        has_so = program_so_path.exists()

        program_so_base64 = None
        if has_so:
            so_bytes = program_so_path.read_bytes()
            program_so_base64 = base64.b64encode(so_bytes).decode("ascii")

        build_result = AnchorBuildResult(
            success=False,
            stdout="",
            stderr="",
            error_message=str(e),
            program_so_path=str(program_so_path) if has_so else None,
            program_so_base64=program_so_base64,
        )

    return CreatedAnchorProgram(
        workspace_dir=str(workspace_dir),
        files=files,
        build=build_result,
        source_files=source_file_paths,
    )


async def run_anchor_build(workspace_dir: str) -> dict:
    """Run anchor build in a workspace.

    Args:
        workspace_dir: Path to workspace directory

    Returns:
        Build result dictionary
    """
    try:
        process = await asyncio.create_subprocess_exec(
            "anchor",
            "build",
            cwd=workspace_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        # Find .so file
        target_deploy_dir = Path(workspace_dir) / "target" / "deploy"
        so_files = list(target_deploy_dir.glob("*.so")) if target_deploy_dir.exists() else []

        if so_files:
            so_path = str(so_files[0])
            return {
                "success": True,
                "stdout": stdout.decode(),
                "stderr": stderr.decode(),
                "soPath": so_path,
            }

        return {
            "success": True,
            "stdout": stdout.decode(),
            "stderr": stderr.decode(),
            "message": "Build completed but .so file not found",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(e),
            "error": str(e),
        }

from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess


def _trim_text(value: str, max_len: int = 320) -> str:
    if len(value) <= max_len:
        return value
    return value[: max_len - 3] + "..."


def _resolve_command() -> str:
    configured = os.getenv("PDFMATH_COMMAND")
    if configured:
        return configured

    project_root = Path(__file__).resolve().parents[1]
    candidates = [
        project_root / ".venv-pdfmath" / "Scripts" / "pdf2zh.exe",
        project_root / ".venv-pdfmath" / "bin" / "pdf2zh",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    return "pdf2zh"


def _command_available(command: str) -> bool:
    as_path = Path(command)
    if as_path.is_file():
        return True
    return shutil.which(command) is not None


def _candidate_commands(source_path: Path, source_lang: str, target_lang: str) -> list[list[str]]:
    base = _resolve_command()
    src = str(source_path.resolve())
    return [
        [base, src, "--lang-in", source_lang, "--lang-out", target_lang],
        [base, src],
    ]


def _find_generated_pdf(search_dirs: list[Path], source_path: Path) -> Path | None:
    stem = source_path.stem
    preferred_names = [f"{stem}-zh.pdf", f"{stem}-dual.pdf"]

    for directory in search_dirs:
        for name in preferred_names:
            candidate = directory / name
            if candidate.exists():
                return candidate

    for directory in search_dirs:
        candidates = sorted(directory.rglob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
        for candidate in candidates:
            if candidate.resolve() == source_path.resolve():
                continue
            return candidate
    return None


def translate_pdf_with_pdfmathtranslate(
    source_path: Path,
    target_path: Path,
    source_lang: str,
    target_lang: str,
) -> bool:
    ok, _ = translate_pdf_with_pdfmathtranslate_diagnostic(source_path, target_path, source_lang, target_lang)
    return ok


def translate_pdf_with_pdfmathtranslate_diagnostic(
    source_path: Path,
    target_path: Path,
    source_lang: str,
    target_lang: str,
) -> tuple[bool, str | None]:
    source_path = source_path.resolve()
    command = _resolve_command()
    if not _command_available(command):
        return False, f"Comando PDFMathTranslate non trovato: {command}"

    if not source_path.exists():
        return False, f"File PDF non trovato: {source_path}"

    work_dir = target_path.parent
    work_dir.mkdir(parents=True, exist_ok=True)

    last_error: str | None = None

    for cmd in _candidate_commands(source_path, source_lang, target_lang):
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, cwd=str(work_dir))
        except subprocess.CalledProcessError as exc:
            raw = (exc.stderr or exc.stdout or str(exc)).strip()
            last_error = f"pdf2zh exit code {exc.returncode}: {_trim_text(raw)}"
            continue
        except Exception as exc:  # noqa: BLE001
            last_error = _trim_text(str(exc))
            continue

        generated = _find_generated_pdf([work_dir, source_path.parent], source_path)
        if generated and generated.exists():
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(generated, target_path)

            # Keep only user-facing translated files, remove intermediate pdf2zh artifacts.
            for name in (f"{source_path.stem}-zh.pdf", f"{source_path.stem}-dual.pdf"):
                candidate = work_dir / name
                if candidate.exists() and candidate.resolve() != target_path.resolve():
                    try:
                        candidate.unlink()
                    except OSError:
                        pass
            return True, None

        last_error = "pdf2zh completato ma nessun PDF di output trovato."

    return False, last_error

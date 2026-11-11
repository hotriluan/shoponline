"""Tests for the project-root lookup in extract-writing-styles.py."""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / 'extract-writing-styles.py'
spec = importlib.util.spec_from_file_location('extract_writing_styles', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def make_styles(root: Path) -> Path:
    styles = root / 'assets' / 'writing-styles'
    styles.mkdir(parents=True)
    (styles / 'default.md').write_text('# Default\n')
    return root


def test_prefers_project_in_cwd_over_user_scoped_install(tmp_path):
    home = tmp_path / 'home'
    script_dir = home / '.claude' / 'skills' / 'ak-copywriting' / 'scripts'
    script_dir.mkdir(parents=True)
    project = make_styles(tmp_path / 'project')

    assert module.resolve_project_root(project, script_dir) == project


def test_finds_project_from_a_subdirectory(tmp_path):
    project = make_styles(tmp_path / 'project')
    subdir = project / 'assets' / 'posts'
    subdir.mkdir(parents=True)

    assert module.resolve_project_root(subdir, tmp_path / 'elsewhere') == project


def test_falls_back_to_project_scoped_install(tmp_path):
    project = make_styles(tmp_path / 'project')
    script_dir = project / '.claude' / 'skills' / 'ak-copywriting' / 'scripts'
    script_dir.mkdir(parents=True)
    unrelated = tmp_path / 'unrelated'
    unrelated.mkdir()

    assert module.resolve_project_root(unrelated, script_dir) == project

"""Render kube/secret.yaml without touching real secrets."""
import pathlib
import subprocess

import yaml

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "kube" / "make_secret.sh"


def run_script(env: pathlib.Path, example: pathlib.Path, dest: pathlib.Path):
    return subprocess.run(
        [
            "bash",
            str(SCRIPT),
            "--env",
            str(env),
            "--example",
            str(example),
            "--out",
            str(dest),
        ],
        capture_output=True,
        text=True,
    )


def test_make_secret_fills_example_keys(tmp_path):
    example = tmp_path / ".env.example"
    env = tmp_path / ".env"
    dest = tmp_path / "secret.yaml"
    example.write_text("ANTHROPIC_API_KEY=XXX-XXX-XXX\n")
    env.write_text("ANTHROPIC_API_KEY=sk-live\nIGNORE=nope\n")
    result = run_script(env, example, dest)
    assert result.returncode == 0, result.stderr
    doc = yaml.safe_load(dest.read_text())
    assert doc["kind"] == "Secret"
    assert doc["metadata"]["name"] == "inthegods"
    assert doc["stringData"] == {"ANTHROPIC_API_KEY": "sk-live"}
    assert "IGNORE" not in doc["stringData"]


def test_make_secret_strips_matching_quotes_and_skips_comments(tmp_path):
    example = tmp_path / ".env.example"
    env = tmp_path / ".env"
    dest = tmp_path / "secret.yaml"
    example.write_text("# required\nANTHROPIC_API_KEY=placeholder\n")
    env.write_text('# local\nANTHROPIC_API_KEY="sk-test=value"\n')
    result = run_script(env, example, dest)
    assert result.returncode == 0, result.stderr
    assert yaml.safe_load(dest.read_text())["stringData"] == {
        "ANTHROPIC_API_KEY": "sk-test=value"
    }


def test_make_secret_requires_example_keys(tmp_path):
    example = tmp_path / ".env.example"
    env = tmp_path / ".env"
    dest = tmp_path / "secret.yaml"
    example.write_text("ANTHROPIC_API_KEY=XXX-XXX-XXX\n")
    env.write_text("OTHER=1\n")
    result = run_script(env, example, dest)
    assert result.returncode != 0
    assert "ANTHROPIC_API_KEY" in result.stderr
    assert not dest.exists()

#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
env_file="$ROOT/.env"
example_file="$ROOT/.env.example"
out_file="$ROOT/kube/secret.yaml"
secret_name="inthegods"

usage() {
  cat <<'EOF'
Usage: kube/make_secret.sh [options]

Write a Kubernetes Secret from the keys in .env.example and values in .env.

Options:
  --env PATH       Source env file (default: .env)
  --example PATH   File listing required keys (default: .env.example)
  --out PATH       Destination manifest (default: kube/secret.yaml)
  --name NAME      Kubernetes Secret name (default: inthegods)
  -h, --help       Show this help
EOF
}

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

while (($#)); do
  case "$1" in
    --env|--example|--out|--name)
      (($# >= 2)) || die "$1 requires a value"
      case "$1" in
        --env) env_file="$2" ;;
        --example) example_file="$2" ;;
        --out) out_file="$2" ;;
        --name) secret_name="$2" ;;
      esac
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown option: $1"
      ;;
  esac
done

[[ -f "$example_file" ]] || die "missing $example_file"
[[ -f "$env_file" ]] || die "missing $env_file"
[[ "$secret_name" =~ ^[a-z0-9]([-a-z0-9.]*[a-z0-9])?$ ]] ||
  die "invalid Kubernetes Secret name: $secret_name"

read_keys() {
  awk '
    function trim(s) {
      sub(/^[[:space:]]+/, "", s)
      sub(/[[:space:]]+$/, "", s)
      return s
    }
    /^[[:space:]]*($|#)/ { next }
    index($0, "=") {
      key = trim(substr($0, 1, index($0, "=") - 1))
      if (key != "" && !seen[key]++) print key
    }
  ' "$example_file"
}

read_value() {
  local key="$1"
  awk -v wanted="$key" '
    function trim(s) {
      sub(/^[[:space:]]+/, "", s)
      sub(/[[:space:]]+$/, "", s)
      return s
    }
    /^[[:space:]]*($|#)/ { next }
    index($0, "=") {
      key = trim(substr($0, 1, index($0, "=") - 1))
      if (key == wanted) {
        value = trim(substr($0, index($0, "=") + 1))
        quote = substr(value, 1, 1)
        if (length(value) >= 2 &&
            (quote == "\"" || quote == sprintf("%c", 39)) &&
            substr(value, length(value), 1) == quote) {
          value = substr(value, 2, length(value) - 2)
        }
        found = 1
      }
    }
    END { if (found) printf "%s", value }
  ' "$env_file"
}

keys=()
while IFS= read -r key; do
  [[ "$key" =~ ^[A-Za-z0-9._-]+$ ]] ||
    die "$example_file contains invalid Secret key: $key"
  keys[${#keys[@]}]="$key"
done < <(read_keys)

((${#keys[@]})) || die "$example_file has no KEY=VALUE lines"

values=()
missing=()
for key in "${keys[@]}"; do
  value="$(read_value "$key")"
  if [[ -z "${value//[[:space:]]/}" ]]; then
    missing[${#missing[@]}]="$key"
  else
    values[${#values[@]}]="$value"
  fi
done

if ((${#missing[@]})); then
  missing_list="$(IFS=', '; printf '%s' "${missing[*]}")"
  die "$env_file missing $missing_list"
fi

mkdir -p "$(dirname "$out_file")"
umask 077
tmp_file="${out_file}.tmp.$$"
trap 'rm -f "$tmp_file"' EXIT

{
  printf '%s\n' \
    'apiVersion: v1' \
    'kind: Secret' \
    'metadata:' \
    "  name: $secret_name" \
    '  namespace: default' \
    'type: Opaque' \
    'stringData:'
  for i in "${!keys[@]}"; do
    printf '  %s: |-\n    %s\n' "${keys[$i]}" "${values[$i]}"
  done
} > "$tmp_file"

mv "$tmp_file" "$out_file"
trap - EXIT
printf 'wrote %s (%d keys)\n' "$out_file" "${#keys[@]}" >&2

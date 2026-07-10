#!/usr/bin/env bash
set -euo pipefail

FIRMWARE_ROOT="/opt/firmware-repo/dell"
NGINX_BASE_URL="http://10.107.0.167:8090/firmware/dell"
BUCKET="breqwatr-firmware-repo"
WASABI_ENDPOINT="https://s3.ca-central-1.wasabisys.com"
AWS_PROFILE="wasabi"
OUTPUT_JSON="/tmp/idrac_update_items_generated.json"

ALLOWED_COMPONENTS=" idrac diagnostics lifecycle_controller bios nic perc "

usage() {
  echo "Usage: $0 <firmware_packages.csv>" >&2
  exit 1
}

trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

json_escape() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

require_command() {
  local command_name="$1"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "ERROR: Required command not found: $command_name" >&2
    exit 1
  fi
}

validate_component() {
  local component="$1"
  if [[ "$ALLOWED_COMPONENTS" != *" $component "* ]]; then
    echo "ERROR: Unsupported component '$component'. Allowed: idrac diagnostics lifecycle_controller bios nic perc" >&2
    exit 1
  fi
}

require_command aws
require_command basename
require_command chown
require_command chmod
require_command cp
require_command curl
require_command dirname
require_command find
require_command sed

if [[ $# -ne 1 ]]; then
  usage
fi

CSV_FILE="$1"
if [[ ! -f "$CSV_FILE" ]]; then
  echo "ERROR: CSV file not found: $CSV_FILE" >&2
  exit 1
fi

TMP_JSON_ITEMS="$(mktemp)"
trap 'rm -f "$TMP_JSON_ITEMS"' EXIT
: > "$TMP_JSON_ITEMS"

processed_count=0
line_number=0

declare -a uploaded_objects=()

while IFS=, read -r component version source_file target_version name transfer_protocol extra_field || [[ -n "${component:-}" ]]; do
  line_number=$((line_number + 1))

  if [[ $line_number -eq 1 ]]; then
    header="$(trim "$component"),$(trim "$version"),$(trim "$source_file"),$(trim "$target_version"),$(trim "$name"),$(trim "$transfer_protocol")"
    if [[ "$header" == "component,version,source_file,target_version,name,transfer_protocol" ]]; then
      continue
    fi
  fi

  component="$(trim "${component:-}")"
  version="$(trim "${version:-}")"
  source_file="$(trim "${source_file:-}")"
  target_version="$(trim "${target_version:-}")"
  name="$(trim "${name:-}")"
  transfer_protocol="$(trim "${transfer_protocol:-HTTP}")"

  if [[ -z "$component" && -z "$version" && -z "$source_file" && -z "$target_version" && -z "$name" ]]; then
    continue
  fi

  if [[ -n "${extra_field:-}" ]]; then
    echo "ERROR: Line $line_number has more than 6 CSV fields. Quoted commas are not supported." >&2
    exit 1
  fi

  component="$(printf '%s' "$component" | tr '[:upper:]' '[:lower:]')"
  transfer_protocol="$(printf '%s' "$transfer_protocol" | tr '[:lower:]' '[:upper:]')"

  validate_component "$component"

  if [[ -z "$version" || -z "$source_file" || -z "$target_version" || -z "$name" ]]; then
    echo "ERROR: Line $line_number is missing required fields." >&2
    exit 1
  fi

  if [[ ! -f "$source_file" ]]; then
    echo "ERROR: Source package not found on line $line_number: $source_file" >&2
    exit 1
  fi

  filename="$(basename "$source_file")"
  destination_dir="$FIRMWARE_ROOT/$component/$version"
  destination_file="$destination_dir/$filename"
  firmware_url="$NGINX_BASE_URL/$component/$version/$filename"
  wasabi_object="s3://$BUCKET/firmware/dell/$component/$version/$filename"

  mkdir -p "$destination_dir"
  cp "$source_file" "$destination_file"
  chown -R cloudadm:cloudadm "$destination_dir"
  find "$FIRMWARE_ROOT/$component" -type d -exec chmod 755 {} +
  chmod 644 "$destination_file"

  echo "Package copied: $destination_file"

  curl -fsSI "$firmware_url" >/dev/null
  echo "Nginx URL tested: $firmware_url"

  if [[ $processed_count -gt 0 ]]; then
    printf ',\n' >> "$TMP_JSON_ITEMS"
  fi

  cat >> "$TMP_JSON_ITEMS" <<JSON
    {
      "name": "$(json_escape "$name")",
      "target_version": "$(json_escape "$target_version")",
      "firmware_image_uri": "$(json_escape "$firmware_url")",
      "transfer_protocol": "$(json_escape "$transfer_protocol")"
    }
JSON

  uploaded_objects+=("$wasabi_object")
  processed_count=$((processed_count + 1))
done < "$CSV_FILE"

if [[ $processed_count -eq 0 ]]; then
  echo "ERROR: No firmware package rows were processed from $CSV_FILE" >&2
  exit 1
fi

aws s3 sync "$FIRMWARE_ROOT" "s3://$BUCKET/firmware/dell" \
  --profile "$AWS_PROFILE" \
  --endpoint-url "$WASABI_ENDPOINT"
echo "Wasabi sync completed: s3://$BUCKET/firmware/dell"

for wasabi_object in "${uploaded_objects[@]}"; do
  aws s3 ls "$wasabi_object" \
    --profile "$AWS_PROFILE" \
    --endpoint-url "$WASABI_ENDPOINT" >/dev/null
  echo "Wasabi object verified: $wasabi_object"
done

cat > "$OUTPUT_JSON" <<JSON
{
  "idrac_update_items": [
$(cat "$TMP_JSON_ITEMS")
  ]
}
JSON

chmod 600 "$OUTPUT_JSON"
echo "JSON generated: $OUTPUT_JSON"
cat "$OUTPUT_JSON"

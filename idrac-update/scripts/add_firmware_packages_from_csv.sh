#!/usr/bin/env bash
set -euo pipefail

FIRMWARE_ROOT="/opt/firmware-repo/dell"
NGINX_BASE_URL="http://10.107.0.167:8090/firmware/dell"
BUCKET="breqwatr-firmware-repo"
WASABI_ENDPOINT="https://s3.ca-central-1.wasabisys.com"
AWS_PROFILE="wasabi"
OUTPUT_JSON="/tmp/idrac_update_items_generated.json"

ALLOWED_COMPONENTS=" idrac idrac_lifecycle_controller lifecycle_controller uefi_diagnostics os_driver_pack "

TMP_JSON_ITEMS=""
declare -a uploaded_objects=()
declare -a copied_new_files=()

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
    echo "ERROR: Unsupported component '$component'. Allowed: idrac idrac_lifecycle_controller lifecycle_controller uefi_diagnostics os_driver_pack" >&2
    exit 1
  fi
}

cleanup() {
  local exit_code=$?

  if [[ -n "${TMP_JSON_ITEMS:-}" ]]; then
    rm -f "$TMP_JSON_ITEMS"
  fi

  if [[ $exit_code -ne 0 && ${#copied_new_files[@]} -gt 0 ]]; then
    echo "WARNING: The script failed after copying new local package files." >&2
    echo "WARNING: Newly added files were left in place and were not automatically deleted:" >&2
    printf '  %s\n' "${copied_new_files[@]}" >&2
  fi
}

run_aws() {
  AWS_CONFIG_FILE="$AWS_CONFIG_FILE_PATH" \
  AWS_SHARED_CREDENTIALS_FILE="$AWS_CREDENTIALS_FILE_PATH" \
  aws "$@"
}

validate_aws_profile() {
  local profile_found=false
  local profile

  while IFS= read -r profile; do
    if [[ "$profile" == "$AWS_PROFILE" ]]; then
      profile_found=true
      break
    fi
  done < <(run_aws configure list-profiles)

  if [[ "$profile_found" != true ]]; then
    cat >&2 <<ERROR
ERROR: AWS profile '$AWS_PROFILE' was not found using:
  config: $AWS_CONFIG_FILE_PATH
  credentials: $AWS_CREDENTIALS_FILE_PATH
ERROR
    exit 1
  fi
}

trap cleanup EXIT

require_command aws
require_command basename
require_command chown
require_command chmod
require_command cut
require_command cp
require_command curl
require_command find
require_command getent
require_command id
require_command sed

RUN_USER="${SUDO_USER:-$(id -un)}"
if [[ -z "$RUN_USER" ]]; then
  echo "ERROR: Unable to determine invoking user." >&2
  exit 1
fi

user_entry=""
if ! user_entry="$(getent passwd "$RUN_USER")"; then
  echo "ERROR: Unable to determine system account for invoking user '$RUN_USER'." >&2
  exit 1
fi

RUN_USER_HOME="$(printf '%s' "$user_entry" | cut -d: -f6)"
if [[ -z "$RUN_USER_HOME" || ! -d "$RUN_USER_HOME" ]]; then
  echo "ERROR: Unable to determine home directory for user '$RUN_USER'." >&2
  exit 1
fi

AWS_CONFIG_FILE_PATH="${AWS_CONFIG_FILE_PATH:-${RUN_USER_HOME}/.aws/config}"
AWS_CREDENTIALS_FILE_PATH="${AWS_CREDENTIALS_FILE_PATH:-${RUN_USER_HOME}/.aws/credentials}"

if [[ $# -ne 1 ]]; then
  usage
fi

CSV_FILE="$1"
if [[ ! -f "$CSV_FILE" ]]; then
  echo "ERROR: CSV file not found: $CSV_FILE" >&2
  exit 1
fi

if [[ ! -f "$AWS_CONFIG_FILE_PATH" ]]; then
  echo "ERROR: AWS config file not found: $AWS_CONFIG_FILE_PATH" >&2
  exit 1
fi

if [[ ! -f "$AWS_CREDENTIALS_FILE_PATH" ]]; then
  echo "ERROR: AWS credentials file not found: $AWS_CREDENTIALS_FILE_PATH" >&2
  exit 1
fi

validate_aws_profile
if ! run_aws s3 ls "s3://$BUCKET" \
  --profile "$AWS_PROFILE" \
  --endpoint-url "$WASABI_ENDPOINT" >/dev/null; then
  echo "ERROR: Unable to reach Wasabi bucket s3://$BUCKET using profile '$AWS_PROFILE'." >&2
  echo "ERROR: AWS files used:" >&2
  echo "  config: $AWS_CONFIG_FILE_PATH" >&2
  echo "  credentials: $AWS_CREDENTIALS_FILE_PATH" >&2
  exit 1
fi
echo "AWS pre-flight passed: profile=$AWS_PROFILE bucket=s3://$BUCKET user=$RUN_USER"

TMP_JSON_ITEMS="$(mktemp)"
: > "$TMP_JSON_ITEMS"

processed_count=0
line_number=0

while IFS=, read -r component version source_file target_version installed_version name transfer_protocol allow_downgrade extra_field || [[ -n "${component:-}" ]]; do
  line_number=$((line_number + 1))

  component="${component#$'\xef\xbb\xbf'}"

  if [[ $line_number -eq 1 ]]; then
    header="$(trim "$component"),$(trim "$version"),$(trim "$source_file"),$(trim "$target_version"),$(trim "$installed_version"),$(trim "$name"),$(trim "$transfer_protocol"),$(trim "$allow_downgrade")"
    if [[ "$header" == "component,version,source_file,target_version,installed_version,name,transfer_protocol,allow_downgrade" ]]; then
      continue
    fi
  fi

  component="$(trim "${component:-}")"
  version="$(trim "${version:-}")"
  source_file="$(trim "${source_file:-}")"
  target_version="$(trim "${target_version:-}")"
  installed_version="$(trim "${installed_version:-}")"
  name="$(trim "${name:-}")"
  transfer_protocol="$(trim "${transfer_protocol:-HTTP}")"
  allow_downgrade="$(trim "${allow_downgrade:-}")"

  if [[ -z "$component" && -z "$version" && -z "$source_file" && -z "$target_version" && -z "$installed_version" && -z "$name" ]]; then
    continue
  fi

  if [[ -n "${extra_field:-}" ]]; then
    echo "ERROR: Line $line_number has more than 8 CSV fields. Quoted commas are not supported." >&2
    exit 1
  fi

  component="$(printf '%s' "$component" | tr '[:upper:]' '[:lower:]')"
  transfer_protocol="$(printf '%s' "$transfer_protocol" | tr '[:lower:]' '[:upper:]')"
  allow_downgrade="$(printf '%s' "$allow_downgrade" | tr '[:upper:]' '[:lower:]')"

  validate_component "$component"

  repository_component="$component"
  if [[ "$component" == "idrac" || "$component" == "idrac_lifecycle_controller" ]]; then
    repository_component="lifecycle_controller"
  fi

  if [[ -n "$allow_downgrade" && "$allow_downgrade" != "true" && "$allow_downgrade" != "false" ]]; then
    echo "ERROR: Line $line_number allow_downgrade must be true or false when supplied." >&2
    exit 1
  fi

  if [[ -z "$version" || -z "$source_file" || -z "$target_version" || -z "$name" ]]; then
    echo "ERROR: Line $line_number is missing required fields." >&2
    exit 1
  fi

  if [[ ! -f "$source_file" ]]; then
    echo "ERROR: Source package not found on line $line_number: $source_file" >&2
    exit 1
  fi

  filename="$(basename "$source_file")"
  destination_dir="$FIRMWARE_ROOT/$repository_component/$version"
  destination_file="$destination_dir/$filename"
  firmware_url="$NGINX_BASE_URL/$repository_component/$version/$filename"
  wasabi_object="s3://$BUCKET/firmware/dell/$repository_component/$version/$filename"
  destination_existed=false

  if [[ -e "$destination_file" ]]; then
    destination_existed=true
  fi

  mkdir -p "$destination_dir"
  cp "$source_file" "$destination_file"

  if [[ "$destination_existed" == false ]]; then
    copied_new_files+=("$destination_file")
  fi

  chown -R cloudadm:cloudadm "$destination_dir"
  find "$FIRMWARE_ROOT/$repository_component" -type d -exec chmod 755 {} +
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
JSON

  if [[ -n "$installed_version" ]]; then
    cat >> "$TMP_JSON_ITEMS" <<JSON
      "installed_version": "$(json_escape "$installed_version")",
JSON
  fi

  cat >> "$TMP_JSON_ITEMS" <<JSON
      "firmware_image_uri": "$(json_escape "$firmware_url")",
      "transfer_protocol": "$(json_escape "$transfer_protocol")"
JSON

  if [[ -n "$allow_downgrade" ]]; then
    cat >> "$TMP_JSON_ITEMS" <<JSON
      ,
      "allow_downgrade": $allow_downgrade
JSON
  fi

  cat >> "$TMP_JSON_ITEMS" <<JSON
    }
JSON

  uploaded_objects+=("$wasabi_object")
  processed_count=$((processed_count + 1))
done < "$CSV_FILE"

if [[ $processed_count -eq 0 ]]; then
  echo "ERROR: No firmware package rows were processed from $CSV_FILE" >&2
  exit 1
fi

run_aws s3 sync "$FIRMWARE_ROOT" "s3://$BUCKET/firmware/dell" \
  --profile "$AWS_PROFILE" \
  --endpoint-url "$WASABI_ENDPOINT"
echo "Wasabi sync completed: s3://$BUCKET/firmware/dell"

for wasabi_object in "${uploaded_objects[@]}"; do
  run_aws s3 ls "$wasabi_object" \
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

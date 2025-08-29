#!/usr/bin/env bash
set -euo pipefail
# downloads latest Fedora CoreOS kernel and initramfs for x86_64 or aarch64 (or all) and writes them into ./boot-artifacts
# also converts butane config butane-k3s.coreos.bu -> ignition.json if butane is installed

REQUEST="${1:-x86_64}"   # Accept first arg: x86_64, aarch64, or all (default: x86_64)
CHANNEL=stable
SUPPORTED_ARCHES=("x86_64" "aarch64")
WORKDIR="$(pwd)/boot-artifacts"
BUFILE="butane-k3s.coreos.bu"
IGNITION_OUT="${WORKDIR}/ignition.json"

mkdir -p "${WORKDIR}"

echo "Fetching latest Fedora CoreOS metadata for channel: ${CHANNEL}..."
METADATA_URL="https://builds.coreos.fedoraproject.org/streams/${CHANNEL}.json"
curl -sSfL "${METADATA_URL}" -o "${WORKDIR}/streams-${CHANNEL}.json"

echo "Parsing artifact locations..."

# Helper to extract artifact URLs for a given arch
get_urls_for_arch() {
  local arch="$1"
  local kernel initramfs image
  # Prefer the PXE-format kernel/initramfs if present (they live under formats.pxe.kernel/.initramfs),
  # otherwise fall back to possible disk.location wrappers used for other formats.
  kernel=$(jq -r --arg arch "${arch}" '(.architectures[$arch].artifacts.metal.formats.pxe.kernel.location // .architectures[$arch].artifacts.metal.formats.pxe.kernel.disk.location // .architectures[$arch].artifacts.metal.formats.kernel.location // .architectures[$arch].artifacts.metal.formats.kernel.disk.location // "")' "${WORKDIR}/streams-${CHANNEL}.json")
  initramfs=$(jq -r --arg arch "${arch}" '(.architectures[$arch].artifacts.metal.formats.pxe.initramfs.location // .architectures[$arch].artifacts.metal.formats.pxe.initramfs.disk.location // .architectures[$arch].artifacts.metal.formats.initramfs.location // .architectures[$arch].artifacts.metal.formats.initramfs.disk.location // "")' "${WORKDIR}/streams-${CHANNEL}.json")
  # Raw image: check "raw.xz" under disk.location, then "raw" (some variants), then any top-level raw location
  image=$(jq -r --arg arch "${arch}" '(.architectures[$arch].artifacts.metal.formats["raw.xz"].disk.location // .architectures[$arch].artifacts.metal.formats["raw.xz"].location // .architectures[$arch].artifacts.metal.formats.raw.disk.location // .architectures[$arch].artifacts.metal.formats.raw.location // "")' "${WORKDIR}/streams-${CHANNEL}.json")
  printf '%s|%s|%s' "${kernel}" "${initramfs}" "${image}"
}

# Decide which architectures to process
if [ "${REQUEST}" = "all" ]; then
  ARCHES=("${SUPPORTED_ARCHES[@]}")
else
  ARCHES=("${REQUEST}")
fi

for ARCH in "${ARCHES[@]}"; do
  echo
  echo "Processing architecture: ${ARCH}"
  IFS='|' read -r KERNEL_URL INITRAMFS_URL IMAGE_URL <<< "$(get_urls_for_arch "${ARCH}")"

  if [ -z "${KERNEL_URL}" ] || [ -z "${INITRAMFS_URL}" ]; then
    echo "Failed to extract kernel/initramfs URLs for arch ${ARCH} from ${METADATA_URL}; skipping."
    continue
  fi

  echo "Kernel: ${KERNEL_URL}"
  echo "Initramfs: ${INITRAMFS_URL}"
  echo "Image (raw.xz): ${IMAGE_URL}"

  KERNEL_FILE="${WORKDIR}/vmlinuz-coreos-${ARCH}"
  INITRAMFS_FILE="${WORKDIR}/initramfs-coreos-${ARCH}.img"
  IMAGE_FILE="${WORKDIR}/coreos-${ARCH}.raw.xz"

  echo "Downloading kernel..."
  curl -sSfL "${KERNEL_URL}" -o "${KERNEL_FILE}"

  echo "Downloading initramfs..."
  curl -sSfL "${INITRAMFS_URL}" -o "${INITRAMFS_FILE}"

  if [ -n "${IMAGE_URL}" ] && [ "${IMAGE_URL}" != "null" ]; then
    echo "Downloading raw image (optional, may be large)..."
    curl -sSfL "${IMAGE_URL}" -o "${IMAGE_FILE}"
  else
    echo "No raw image URL available for ${ARCH} or skipping raw image download."
  fi
done

# Generate ignition JSON from Butane if available (single ignition file used for all arches)
if command -v butane >/dev/null 2>&1; then
  if [ -f "${BUFILE}" ]; then
    echo "Converting ${BUFILE} -> ${IGNITION_OUT} using butane..."
    butane -o "${IGNITION_OUT}" "${BUFILE}"
    echo "Ignition written to ${IGNITION_OUT}"
  else
    echo "Butane is available but ${BUFILE} not found in current directory."
  fi
else
  echo "butane not installed; skipping conversion. If you have butane, run: butane -o ${IGNITION_OUT} ${BUFILE}"
fi

echo
echo "Artifacts placed in ${WORKDIR}:"
ls -lh "${WORKDIR}" || true

echo
echo "Next steps:"
echo "- Serve ${WORKDIR} over HTTP (e.g., python3 -m http.server --directory ${WORKDIR} 8080)"
echo "- Update boot/coreos.ipxe replacing {KERNEL_URL} -> /vmlinuz-coreos-<arch>, {INITRAMFS_URL} -> /initramfs-coreos-<arch>.img, {IMAGE_URL} -> (optional) /coreos-<arch>.raw.xz, and {IGNITION_URL} -> /ignition.json (if generated)"
echo "- Use your iPXE/TFTP infrastructure to point to boot/coreos.ipxe or embed the contents into DHCP/TFTP."

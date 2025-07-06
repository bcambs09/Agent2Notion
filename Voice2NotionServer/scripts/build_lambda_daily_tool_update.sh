#!/usr/bin/env bash
# scripts/build_lambda_daily_tool_update.sh
set -euo pipefail

FUNC_NAME=lambda_daily_tool_update.py            # path to the handler
REQ_FILE=Agent2NotionServer/requirements.txt     # your requirements.txt
OUT_ZIP=Agent2NotionServer/scripts/lambda_daily_tool_update.zip

PY_VERSION=3.11                                  # Lambda runtime
BUILD_DIR=$(mktemp -d)

echo "· Installing deps into $BUILD_DIR"
pip3 install \
  --platform manylinux2014_x86_64 \
  --implementation cp \
  --only-binary=:all: \
  -r "${REQ_FILE}" \
  -t "${BUILD_DIR}"

echo "· Copying function code"
cp Agent2NotionServer/scripts/${FUNC_NAME} "${BUILD_DIR}/"

# include any local packages that the function imports (e.g. notion_tools)
cp -r Agent2NotionServer/notion_tools.py "${BUILD_DIR}/"
mkdir -p "${BUILD_DIR}/scripts"

echo "· Zipping"
pushd "${BUILD_DIR}" >/dev/null
zip -q -r lambda.zip .
popd >/dev/null

mkdir -p "$(dirname "${OUT_ZIP}")"
mv "${BUILD_DIR}/lambda.zip" "${OUT_ZIP}"
rm -rf "${BUILD_DIR}"
echo "Created ${OUT_ZIP}"
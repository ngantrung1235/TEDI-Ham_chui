#!/bin/sh
# Bien dich thu (Mono mcs) toan bo ma C# cua cac add-in MCP tren STUB cua SDK Bentley / Navisworks / Roslyn.
#
# Y NGHIA: bat loi gõ sai ten, thieu `using`, sai namespace/kieu/accessibility TRONG MA CUA TA sau khi
# refactor. KHONG kiem chung chu ky API that cua Bentley / Autodesk: stubs chi la gia dinh cua chung ta.
# Qua duoc buoc nay != build duoc voi DLL that; build that van la buoc quyet dinh.
#
# Yeu cau (Debian/Ubuntu):  apt-get install mono-mcs libnewtonsoft-json5.0-cil \
#     libmono-system-windows-forms4.0-cil libmono-system-drawing4.0-cil
# mcs chi ho tro C# <= 6/7 (khong co `case X when`, local function...) - ma loi tranh cac cu phap do.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../.." && pwd)
STUBS="$HERE/stubs"
NJ=${NEWTONSOFT:-/usr/lib/cli/Newtonsoft.Json-5.0/Newtonsoft.Json.dll}
REFS="-r:$NJ -r:System.Windows.Forms.dll -r:System.Drawing.dll -r:System.Core.dll -r:Microsoft.CSharp.dll"
fail=0

src() { find "$@" -name '*.cs' -not -path '*/obj/*' -not -path '*/bin/*'; }
compile() {
  name=$1; shift
  if out=$(mcs -target:library -out:/dev/null $REFS "$@" 2>&1); then echo "OK   $name"
  else echo "FAIL $name"; echo "$out" | grep -v "warning"; fail=1; fi
}

compile "Mcp_Common (hang tang trung lap)" $(src "$ROOT/Mcp_Common/bridge") "$STUBS/Roslyn.cs" "$STUBS/ProductInfoCommon.cs"
compile "OpenTunnel Designer (Bentley)" $(src "$ROOT/Mcp_Common/bridge" "$ROOT/Bentley_MCP_Core/bridge") \
  "$ROOT/OpenTunnel_MCP/bridge/OTDMcpBridge/ProductInfo.cs" "$STUBS/Roslyn.cs" "$STUBS/BentleyStubs.cs"
compile "OpenBridge Designer (Bentley)" $(src "$ROOT/Mcp_Common/bridge" "$ROOT/Bentley_MCP_Core/bridge") \
  "$ROOT/OpenBridge_MCP/bridge/OBDMcpBridge/ProductInfo.cs" "$STUBS/Roslyn.cs" "$STUBS/BentleyStubs.cs"
compile "Navisworks Manage" $(src "$ROOT/Mcp_Common/bridge" "$ROOT/Navisworks_MCP/bridge") "$STUBS/Roslyn.cs" "$STUBS/NavisworksStubs.cs"
exit $fail

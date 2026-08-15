import urllib.request
import re

print("=== Fetching OSS.go.id HTML ===")
req = urllib.request.Request(
    "https://oss.go.id/id/verifikasi-nib", 
    headers={"User-Agent": "Mozilla/5.0"}
)
html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", errors="ignore")
print(f"Downloaded: {len(html)} bytes")

# Save full HTML
with open("oss_full_html.txt", "w") as f:
    f.write(html)

# Find all URLs that look like API endpoints
patterns = [
    r'["\'](/[^\'"]*(?:api|fetch|!json|_next/data)[^\'"]*)["\']',
    r'["\']([^\'"]*(?:gw\.oss\.go\.id|/api)[^\'"]*)["\']',
]

print("\n=== API URLs found ===")
for pat in patterns:
    matches = re.findall(pat, html, re.IGNORECASE)
    unique = set(matches)
    print(f"Pattern: {pat}")
    for u in sorted(unique, key=lambda x: x)[:20]:
        print(f"  {u}")

# Check for any JavaScript that contains fetch calls
print("\n=== Fetch-related JS patterns ===")
fetch_patterns = [
    r'fetch\(["\']([^"\']+)["\']',
    r'fetch\(["\']([^"\']+?api[^"\']*)["\']',
    r'\bapi[^\s"\']+\.json',
    r'\b\{.*?fetch:.*?"([^"\']+?api[^"\']+).*?\}',
]

for pat in fetch_patterns:
    matches = re.findall(pat, html, re.IGNORECASE | re.DOTALL)
    if matches:
        print(f"\nPattern: {pat}")
        for m in set(matches[:10]):
            print(f"  {m[:200]}")

# Check page metadata for API hints
print("\n=== Page metadata ===")
meta_patterns = [
    r'<meta[^>]+content="([^"]+)"[^>]+name="oss-[^"]*"',
    r'<script[^>]*type="application/json"[^>]*>([^<]+)</script>',
]

for pat in meta_patterns:
    matches = re.findall(pat, html, re.IGNORECASE)
    if matches:
        print(f"\nPattern: {pat}")
        for m in matches[:3]:
            print(f"  {m[:300]}")

# Check for any Next.js data endpoints
print("\n=== Next.js Data Patterns ===")
next_patterns = [
    r'["\'](/_next/data[^\'"]+)["\']',
    r'"slug"[^}]*"([^"]+)"',
]

for pat in next_patterns:
    matches = re.findall(pat, html, re.IGNORECASE)
    if matches:
        print(f"\nPattern: {pat}")
        unique = set(matches[:10])
        print(f"  Found {len(unique)} unique")
        for m in unique:
            print(f"    {m[:200]}")

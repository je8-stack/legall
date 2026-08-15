import time
import re
import json
from playwright.sync_api import sync_playwright

# Fallback configuration
OSS_VERIFICATION_URL = "https://oss.go.id/id/verifikasi-nib"
OSS_API_ENDPOINT = "https://gw.oss.go.id/v2/portal/menu/nologin"


def verify_nib(nib_number: str) -> dict:
    """
    Verify NIB data from OSS.go.id.
    
    Due to Cloudflare Turnstile CAPTCHA and Next.js client router
    blocking automation, this returns a fallback with manual verification link.
    
    Args:
        nib_number: NIB number to verify (13 digits)
        
    Returns:
        Dictionary with verification results or fallback information
    """
    print(f"[SCRAPER] Verifying NIB: {nib_number}")
    
    # Format check
    if not re.match(r'^\d{13}$', nib_number):
        return {
            "error": "NIB format invalid",
            "message": "NIB must be exactly 13 digits",
            "fallback_url": OSS_VERIFICATION_URL,
        }
    
    try:
        result = _try_playwright_verification(nib_number)
        
        if result.get("success"):
            return {
                "success": True,
                "data": result.get("data", {}),
                "source": "OSS.go.id",
                "verified_at": time.strftime("%Y-%m-%d %H:%M:%S WIB"),
            }
        
        # If playwright fails, return fallback
        return _return_fallback(nib_number, result.get("error", "verification failed"))
        
    except Exception as e:
        return _return_fallback(nib_number, str(e))


def _try_playwright_verification(nib_number: str) -> dict:
    """Attempt to verify NIB using Playwright browser automation."""
    
    all_console_logs = []
    api_calls = []
    
    def on_console(msg):
        all_console_logs.append({
            "type": msg.type,
            "text": msg.text[:500],
        })
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                ]
            )
            
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="id-ID",
                viewport={"width": 1280, "height": 900},
            )
            
            page = context.new_page()
            page.on("console", on_console)
            
            # Intercept API calls
            def on_response(response):
                url = response.url
                if any(kw in url for kw in ['/api', 'gw.oss', 'verify', 'nib']):
                    try:
                        api_calls.append({
                            "url": url,
                            "status": response.status,
                            "method": response.request.method,
                        })
                    except:
                        pass
            
            page.on("response", on_response)
            
            # Navigate to verification page
            print("[SCRAPER] Loading oss.go.id/verifikasi-nib...")
            page.goto("https://oss.go.id/id/verifikasi-nib", timeout=30000)
            time.sleep(5)
            
            # Find and fill NIB input
            nib_input = page.query_selector_one('input[placeholder*="NIB"]')
            if not nib_input:
                return {"success": False, "error": "NIB input not found"}
            
            # Fill input using React-compatible method
            page.evaluate("""
                (nib) => {
                    const input = document.querySelector('input[placeholder*="NIB"]');
                    if (input) {
                        const tracker = input._valueTracker;
                        if (tracker) tracker.setValue('');
                        input.value = nib;
                        input.dispatchEvent(new Event('input', {bubbles: true}));
                        input.dispatchEvent(new Event('change', {bubbles: true}));
                    }
                }
            """, nib_number)
            
            time.sleep(2)
            
            # Find and click submit button
            submit_btn = page.query_selector_one('button[type="submit"]')
            if not submit_btn:
                return {"success": False, "error": "Submit button not found"}
            
            submit_btn.click()
            time.sleep(15)
            
            # Check if we got results
            url = page.url
            title = page.title()
            text = ""
            try:
                text = page.evaluate("() => document.body.innerText")
            except:
                pass
            
            # If page didn't change to result page, return fallback
            if len(text) < 1000 or "404" in title or "Tidak Ditemukan" in text:
                browser.close()
                return {
                    "success": False,
                    "error": "Form submission blocked by Next.js router",
                    "url": url,
                    "text_length": len(text),
                }
            
            # If we have results, parse them
            data = _parse_nib_result(text, nib_number)
            browser.close()
            
            return {"success": True, "data": data}
            
    except Exception as e:
        return {"success": False, "error": str(e)}


def _parse_nib_result(text: str, nib_number: str) -> dict:
    """Parse NIB verification result from page text."""
    data = {
        "nib": nib_number,
        "perusahaan": "",
        "status": "",
        "migrasi": "",
        "modal": "",
        "skala": "",
    }
    
    # Extract company name
    match = re.search(r"(?:NAMA|Nama)\s+(?:PERUSAHAAN|Perusahaan)[:\s]+([\w\s\-&.,]+)", text, re.IGNORECASE)
    if match:
        data["perusahaan"] = match.group(1).strip()
    
    # Extract status
    match = re.search(r"STATUS\s+AKTIF[:\s]+([^\n]+)", text, re.IGNORECASE)
    if match:
        data["status"] = match.group(1).strip()
    
    # Extract migration status
    match = re.search(r"STATUS\s+MIGRASI[:\s]+([^\n]+)", text, re.IGNORECASE)
    if match:
        data["migrasi"] = match.group(1).strip()
    
    # Extract investment amount
    match = re.search(r"Penanaman\s+Modal[:\s]+([^\n]+)", text, re.IGNORECASE)
    if match:
        data["modal"] = match.group(1).strip()
    
    # Extract business scale
    match = re.search(r"SKALA\s+USAHA[:\s]+([^\n]+)", text, re.IGNORECASE)
    if match:
        data["skala"] = match.group(1).strip()
    
    return data


def _return_fallback(nib_number: str, error_message: str = "") -> dict:
    """
    Return fallback result when automation fails.
    
    This is the primary solution since OSS.go.id blocks browser automation
    via Cloudflare Turnstile CAPTCHA and Next.js client router.
    """
    return {
        "success": False,
        "error": "Manual verification required",
        "message": "OSS.go.id blocks automated verification due to security measures. Please verify manually.",
        "fallback_url": f"{OSS_VERIFICATION_URL}?nib={nib_number}",
        "manual_guide": _get_manual_guide(),
        "nib": nib_number,
        "error_details": error_message,
        "api_note": "OSS.go.id uses Cloudflare Turnstile CAPTCHA and Next.js SPA which block browser automation tools.",
    }


def _get_manual_guide() -> list:
    """Return step-by-step guide for manual NIB verification."""
    return [
        "1. Buka browser dan kunjungi: https://oss.go.id/id/verifikasi-nib",
        "2. Masukkan NIB 13 digit di kolom pencarian",
        "3. Klik tombol 'Cari NIB'",
        "4. Data perusahaan akan ditampilkan termasuk:",
        "   - Nama Perusahaan",
        "   - Status Aktif/Non-Aktif",
        "   - Status Migrasi",
        "   - Penanaman Modal",
        "   - Skala Usaha",
    ]


def get_oss_api_status() -> dict:
    """Check if OSS gateway API is accessible."""
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://gw.oss.go.id/v2/portal/menu/nologin",
            headers={"User-Agent": "Mozilla/5.0"}
        )
        resp = urllib.request.urlopen(req, timeout=10)
        if resp.getcode() == 200:
            data = json.loads(resp.read().decode())
            return {
                "status": "online",
                "endpoints_available": len(data.get("data", [])),
            }
    except Exception as e:
        return {"status": "offline", "error": str(e)}
    
    return {"status": "unknown"}


if __name__ == "__main__":
    import sys
    
    # Test with sample NIB
    test_nib = sys.argv[1] if len(sys.argv) > 1 else "9120110071054"
    
    print("=" * 70)
    print("OSS.go.id NIB Verification Scraper")
    print("=" * 70)
    
    # Check API status first
    print("\nChecking OSS gateway...")
    api_status = get_oss_api_status()
    print(f"  Status: {api_status.get('status', 'unknown')}")
    
    if api_status.get("status") != "online":
        print("  NOTE: OSS gateway is not responding")
    
    # Verify NIB
    print(f"\nVerifying NIB: {test_nib}")
    result = verify_nib(test_nib)
    
    # Display results
    print("\n" + "=" * 70)
    print("RESULTS:")
    print("=" * 70)
    
    if result.get("success"):
        print(json.dumps(result["data"], indent=2, ensure_ascii=False))
    else:
        print("\n[!] VERIFICATION FAILED")
        print(f"   Error: {result.get('error', 'unknown')}")
        print("\n[+] Manual Verification Guide:")
        for step in result.get("manual_guide", []):
            print(f"   {step}")
        print(f"\n[+] Direct Link: {result.get('fallback_url', OSS_VERIFICATION_URL)}")
        print(f"\n[!] Note: {result.get('api_note', 'OSS.go.id restricts automated access.')}")
    
    print("\n" + "=" * 70)

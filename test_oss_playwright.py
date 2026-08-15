import time
import json
from playwright.sync_api import sync_playwright

def main():
    # Block Next.js client router by overriding event.preventDefault FIRST
    # before any page content loads
    intercept_script = """
        // Override preventDefault for submit events BEFORE page loads
        // This allows the form to actually navigate
        const origPrevent = Event.prototype.preventDefault;
        Event.prototype.preventDefault = function() {
            if (this.type === 'submit' && this.target && this.target.tagName === 'FORM') {
                // Don't prevent form submissions - let them navigate
                console.log('[PREVENT] BLOCKED form preventDefault - letting form navigate');
                return;
            }
            // Allow other preventDefault calls
            return origPrevent.call(this);
        };
        
        // Also block Next.js router intercept
        // Next.js uses fetch to intercept navigation
        window.__nextBypass = true;
    """
    
    def wait_for_nib_result(page, max_wait=30):
        """Wait until NIB data appears or timeout"""
        start = time.time()
        while time.time() - start < max_wait:
            url = page.url
            try:
                text = page.evaluate("""
                    function() {
                        var body = document.body.innerText;
                        if (body.length > 500) {
                            return body.substring(0, 5000);
                        }
                        return "";
                    }
                """)
                if text and len(text) > 500:
                    print(f"  Found NIB result! Text length: {len(text)}")
                    print(f"  URL: {url}")
                    return text, url
            except:
                pass
            time.sleep(0.5)
        return None, None
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        # Create context WITH the interception script
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            locale="id-ID",
            bypass_csp=True,  # Bypass CSP to allow our script
        )
        
        page = context.new_page()
        
        # Add init script BEFORE any page loads
        page.add_init_script(intercept_script)
        
        print("=" * 70)
        print("OSS NIB Verification - Bypassing Next.js Router")
        print("=" * 70)
        
        # Navigate to verification page
        print("\n[1] Loading verification page...")
        page.goto("https://oss.go.id/id/verifikasi-nib", timeout=30000)
        time.sleep(4)
        
        print(f"    URL: {page.url}")
        print(f"    Ready!")
        
        # Fill the NIB input
        print("\n[2] Filling NIB input...")
        result = page.evaluate("""
            () => {
                const input = document.querySelector('input[placeholder*="NIB"]');
                if (input) {
                    const tracker = input._valueTracker;
                    if (tracker) tracker.setValue('');
                    input.value = '9120110071054';
                    input.dispatchEvent(new Event('input', {bubbles: true}));
                    input.dispatchEvent(new Event('change', {bubbles: true}));
                    console.log('[FILL] Done:', input.value);
                    return 'ok';
                }
                return 'no input';
            }
        """)
        print(f"    Result: {result}")
        time.sleep(1)
        
        # Submit the form - THIS TIME preventDefault should be blocked!
        print("\n[3] Submitting form (preventDefault should be blocked)...")
        
        submit_result = page.evaluate("""
            () => {
                const btn = document.querySelector('button[type="submit"]');
                if (btn) {
                    btn.click();
                    return 'clicked';
                }
                return 'no btn';
            }
        """)
        print(f"    Result: {submit_result}")
        
        # Wait for navigation or NIB result
        print("\n[4] Waiting for result...")
        result_text, result_url = wait_for_nib_result(page, 15)
        
        if result_text:
            print("\n    *** SUCCESS! ***")   
            print(f"    URL: {result_url}")
            print(f"    Result preview: {result_text[:300]}")
            
            # Save results
            with open("oss_result.txt", "w", encoding="utf-8") as f:
                f.write(f"URL: {result_url}\n\n")
                f.write(f"Result text ({len(result_text)} chars):\n{result_text[:8000]}")
            
            page.screenshot(path="oss_result.png", full_page=True)
            print(f"    Saved to oss_result.txt and oss_result.png")
            browser.close()
            return
        
        # Check the current page
        print(f"\n    No result found.")
        print(f"    Current URL: {page.url}")
        
        page_text = ""
        try:
            page_text = page.evaluate("() => document.body.innerText")
        except:
            pass
        
        with open("oss_result.txt", "w", encoding="utf-8") as f:
            f.write(f"URL: {page.url}\n\n")
            f.write(f"Page text ({len(page_text)} chars):\n{page_text[:5000]}")
        
        page.screenshot(path="oss_no_result.png", full_page=True)
        browser.close()
        print(f"    Saved to oss_result.txt")
        print("\n    *** FAILED - form still blocked or no NIB data ***")

if __name__ == "__main__":
    main()

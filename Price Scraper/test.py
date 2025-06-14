from xvfbwrapper import Xvfb
import undetected_chromedriver as uc

print("Starting virtual display...")
vdisplay = Xvfb(width=1920, height=1080)
vdisplay.start()

print("Launching Chrome in HEADED mode...")
options = uc.ChromeOptions()
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-gpu")
options.add_argument("--window-size=1920,1080")
options.add_argument("--start-maximized")
options.add_argument("--disable-blink-features=AutomationControlled")

# Correct argument for UCD v3.4.7 is 'executable_path'
driver = uc.Chrome(
    options=options,
    executable_path="/usr/bin/google-chrome"
)

driver.get("https://example.com")
print("Page title:", driver.title)

driver.quit()
vdisplay.stop()
print("✅ Success!")

import streamlit as st
import os
from email.message import EmailMessage
import ssl
import smtplib
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from PIL import Image
import time
import shutil
import subprocess
import sys

# =========================================
# Credenciales desde st.secrets
# =========================================
try:
    redcap_username = st.secrets["redcap_username"]
    redcap_password = st.secrets["redcap_password"]
    email_sender = st.secrets["email_sender"]
    email_password = st.secrets["email_password"]
except Exception as e:
    st.error("❌ Error loading secrets. Please configure your Streamlit secrets.")
    st.stop()

# =========================================
# ChromeDriver Setup for Streamlit Cloud
# =========================================
@st.cache_resource
def setup_chrome_driver():
    """Setup ChromeDriver for Streamlit Cloud environment"""
    try:
        st.info("🔧 Setting up ChromeDriver...")
        
        # Check if we're running on Streamlit Cloud
        if os.path.exists("/usr/bin/chromium"):
            # Use system chromium
            chrome_binary = "/usr/bin/chromium"
        elif os.path.exists("/usr/bin/chromium-browser"):
            chrome_binary = "/usr/bin/chromium-browser"
        else:
            chrome_binary = None
            
        # Try to use webdriver-manager to handle ChromeDriver
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            from webdriver_manager.core.os_manager import ChromeType
            
            # For Streamlit Cloud, try to install ChromeDriver
            driver_path = ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install()
            st.success(f"✅ ChromeDriver installed at: {driver_path}")
            return driver_path, chrome_binary
        except Exception as e:
            st.warning(f"⚠️ WebDriver Manager failed: {e}")
            
        # Fallback: manual ChromeDriver setup
        chromedriver_path = "/usr/bin/chromedriver"
        if os.path.exists(chromedriver_path):
            return chromedriver_path, chrome_binary
            
        st.error("❌ ChromeDriver not found")
        return None, chrome_binary
        
    except Exception as e:
        st.error(f"❌ Error setting up ChromeDriver: {e}")
        return None, None

def get_chrome_options(chrome_binary=None):
    """Get Chrome options optimized for Streamlit Cloud"""
    chrome_options = Options()
    
    # Set Chrome binary if available
    if chrome_binary and os.path.exists(chrome_binary):
        chrome_options.binary_location = chrome_binary
    
    # Essential options for cloud environments
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--disable-background-timer-throttling")
    chrome_options.add_argument("--disable-backgrounding-occluded-windows")
    chrome_options.add_argument("--disable-renderer-backgrounding")
    chrome_options.add_argument("--disable-features=TranslateUI")
    chrome_options.add_argument("--disable-ipc-flooding-protection")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-default-apps")
    chrome_options.add_argument("--disable-sync")
    chrome_options.add_argument("--no-first-run")
    chrome_options.add_argument("--disable-popup-blocking")
    chrome_options.add_argument("--single-process")
    chrome_options.add_argument("--disable-web-security")
    chrome_options.add_argument("--disable-features=VizDisplayCompositor")
    chrome_options.add_argument("--remote-debugging-port=9222")
    
    # Additional Streamlit Cloud specific options
    chrome_options.add_argument("--disable-setuid-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--memory-pressure-off")
    chrome_options.add_argument("--max_old_space_size=4096")
    
    # Logging
    chrome_options.add_experimental_option("excludeSwitches", ["enable-logging"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument("--log-level=3")
    
    return chrome_options

# =========================================
# RedCap Barcode Screenshot Function
# =========================================
def download_barcode_images(record_ids, username, password):
    """Download barcode images for specific Record IDs from RedCap"""
    driver = None
    try:
        st.info("🚀 Starting browser for barcode download...")
        
        # Setup ChromeDriver
        driver_path, chrome_binary = setup_chrome_driver()
        if not driver_path:
            st.error("❌ Cannot setup ChromeDriver")
            return []
        
        chrome_options = get_chrome_options(chrome_binary)
        folder = "codigos_barras"
        os.makedirs(folder, exist_ok=True)
        
        # Initialize WebDriver
        try:
            service = Service(executable_path=driver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            st.success("✅ Chrome driver initialized successfully")
        except Exception as e:
            st.error(f"❌ Failed to initialize Chrome driver: {e}")
            return []
        
        wait = WebDriverWait(driver, 30)

        # Login to RedCap
        st.info("🔐 Logging into RedCap...")
        url = "https://redcap.prisma.org.pe/redcap_v14.5.11/DataEntry/record_status_dashboard.php?pid=19"
        
        try:
            driver.get(url)
            st.info("📄 Page loaded successfully")
        except Exception as e:
            st.error(f"❌ Failed to load RedCap URL: {e}")
            return []

        # Login process
        try:
            username_field = wait.until(EC.presence_of_element_located((By.ID, "username")))
            username_field.clear()
            username_field.send_keys(username)
            
            password_field = wait.until(EC.presence_of_element_located((By.ID, "password")))
            password_field.clear()
            password_field.send_keys(password)
            password_field.send_keys(Keys.ENTER)
            
            wait.until(EC.url_contains("record_status_dashboard.php"))
            st.success("✅ Successfully logged into RedCap!")
        except Exception as e:
            st.error(f"❌ Login failed: {e}")
            return []

        TARGET_URL_TEMPLATE = (
            "https://redcap.prisma.org.pe/redcap_v14.5.11/DataEntry/index.php?pid=19&id={id_val}&event_id=59&page=recepcion_de_muestra"
        )

        downloaded_files = []
        progress_bar = st.progress(0)
        total_ids = len(record_ids)
        
        for idx, id_val in enumerate(record_ids):
            try:
                st.info(f"📸 Processing Record ID: {id_val} ({idx + 1}/{total_ids})")
                
                target_url = TARGET_URL_TEMPLATE.format(id_val=id_val)
                driver.get(target_url)
                time.sleep(2)

                # Wait for loading indicators to disappear
                try:
                    loading_locator = (By.XPATH, "//*[contains(text(),'PIPING DATA')]")
                    WebDriverWait(driver, 10).until(EC.invisibility_of_element_located(loading_locator))
                except TimeoutException:
                    pass

                # Find barcode element
                try:
                    tr_selector = "tr#barcode-tr"
                    tr_el = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, tr_selector)))
                except TimeoutException:
                    st.warning(f"⚠️ Barcode element not found for ID: {id_val}")
                    continue

                # Scroll and screenshot
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", tr_el)
                time.sleep(1.5)

                screenshot_path = os.path.join(folder, f"{id_val}.png")
                tr_el.screenshot(screenshot_path)

                # Process image
                try:
                    img = Image.open(screenshot_path)
                    w, h = img.size
                    new_w = int(w * 2 / 3)
                    img_cropped = img.crop((0, 0, new_w, h))
                    img_cropped.save(screenshot_path)
                    downloaded_files.append(screenshot_path)
                    st.success(f"✅ Downloaded barcode for ID: {id_val}")
                except Exception as e:
                    st.error(f"❌ Error processing image for ID {id_val}: {e}")

            except Exception as e:
                st.error(f"❌ Error processing ID {id_val}: {e}")
            
            progress_bar.progress((idx + 1) / total_ids)

        return downloaded_files

    except Exception as e:
        st.error(f"❌ Error in barcode download: {e}")
        return []
    
    finally:
        if driver:
            try:
                driver.quit()
                st.info("🔄 Chrome driver closed")
            except:
                pass

# =========================================
# Email Function
# =========================================
def send_email_with_attachments(record_ids, attachment_files, email_receiver):
    """Send email with barcode images as attachments."""
    try:
        em = EmailMessage()
        em['From'] = email_sender
        em['To'] = email_receiver
        em['Subject'] = f"Códigos de Barras RedCap - IDs: {', '.join(map(str, record_ids))}"

        html_body = f"""
        <html>
          <body>
            <h2>Códigos de Barras Descargados</h2>
            <p>Se han descargado los códigos de barras para los siguientes Record IDs:</p>
            <ul>
                {"".join([f"<li>Record ID: {rid}</li>" for rid in record_ids])}
            </ul>
            <p>Total de imágenes adjuntas: {len(attachment_files)}</p>
            <br>
            <p><em>Enviado desde la app de Streamlit RedCap 🚀</em></p>
          </body>
        </html>
        """
        em.add_alternative(html_body, subtype="html")

        for file_path in attachment_files:
            if os.path.exists(file_path):
                with open(file_path, "rb") as f:
                    filename = os.path.basename(file_path)
                    em.add_attachment(
                        f.read(),
                        maintype="image",
                        subtype="png",
                        filename=filename
                    )

        context = ssl.create_default_context()
        with smtplib.SMTP_SSL('smtp.gmail.com', 465, context=context, timeout=10) as smtp:
            smtp.login(email_sender, email_password)
            smtp.sendmail(email_sender, email_receiver, em.as_string())

        return True

    except Exception as e:
        st.error(f"❌ Email send failed: {e}")
        return False

# =========================================
# System Check Function
# =========================================
def check_system_status():
    """Check system status and available browsers"""
    st.subheader("🔍 System Status Check")
    
    checks = []
    
    # Check Chromium
    if os.path.exists("/usr/bin/chromium"):
        checks.append(("✅", "Chromium Browser", "/usr/bin/chromium"))
    elif os.path.exists("/usr/bin/chromium-browser"):
        checks.append(("✅", "Chromium Browser", "/usr/bin/chromium-browser"))
    else:
        checks.append(("❌", "Chromium Browser", "Not found"))
    
    # Check ChromeDriver
    driver_path, _ = setup_chrome_driver()
    if driver_path:
        checks.append(("✅", "ChromeDriver", f"Available at {driver_path}"))
    else:
        checks.append(("❌", "ChromeDriver", "Not available"))
    
    # Display results
    for status, component, details in checks:
        st.write(f"{status} **{component}**: {details}")
    
    return all(check[0] == "✅" for check in checks)

# =========================================
# Streamlit UI
# =========================================
st.title("🔬 RedCap Barcode Downloader (Fixed for Cloud)")
st.write("Enter Record IDs to download their barcode images from RedCap and send them via email.")

# System check
with st.expander("🔧 System Check"):
    if st.button("Run System Check"):
        system_ok = check_system_status()
        if system_ok:
            st.success("✅ All system requirements are available!")
        else:
            st.warning("⚠️ Some system requirements are missing.")

# Main inputs
record_ids_input = st.text_input(
    "Enter Record IDs separated by commas", 
    placeholder="e.g., 1,2,3,4,5",
    value="1,2,3"
)

email_receiver_input = st.text_input(
    "Enter Receiver Email",
    placeholder="example@domain.com"
)

# Process button
if st.button("🚀 Download Barcodes & Send Email", type="primary"):
    if not record_ids_input.strip():
        st.error("❌ Please enter at least one Record ID")
    elif not email_receiver_input.strip():
        st.error("❌ Please enter a receiver email")
    else:
        try:
            # Parse Record IDs
            record_ids = []
            for rid in record_ids_input.split(","):
                rid = rid.strip()
                if rid:
                    try:
                        record_ids.append(int(rid))
                    except ValueError:
                        record_ids.append(rid)

            if not record_ids:
                st.error("❌ No valid Record IDs found")
            else:
                st.info(f"🎯 Processing {len(record_ids)} Record IDs: {record_ids}")
                
                # Download images
                with st.spinner("📥 Downloading barcode images..."):
                    downloaded_files = download_barcode_images(record_ids, redcap_username, redcap_password)

                if downloaded_files:
                    st.success(f"✅ Successfully downloaded {len(downloaded_files)} barcode images!")

                    # Display images
                    st.subheader("📸 Downloaded Barcode Images:")
                    cols = st.columns(min(3, len(downloaded_files)))
                    for i, file_path in enumerate(downloaded_files):
                        col_idx = i % len(cols)
                        with cols[col_idx]:
                            if os.path.exists(file_path):
                                st.image(file_path, caption=f"ID: {os.path.basename(file_path).split('.')[0]}")

                    # Send email
                    with st.spinner("📧 Sending email..."):
                        if send_email_with_attachments(record_ids, downloaded_files, email_receiver_input):
                            st.success("✅ Email sent successfully!")
                            
                            # Cleanup
                            try:
                                shutil.rmtree("codigos_barras")
                                st.info("🧹 Temporary files cleaned up")
                            except:
                                pass
                        else:
                            st.error("❌ Failed to send email")
                else:
                    st.error("❌ No barcode images were downloaded successfully")

        except Exception as e:
            st.error(f"❌ Processing error: {e}")
            st.exception(e)

# Configuration info
with st.expander("🔧 Current Configuration"):
    st.code(f"""
RedCap URL: https://redcap.prisma.org.pe/redcap_v14.5.11/
Project ID: 19
Event ID: 59
Page: recepcion_de_muestra
Email From: {email_sender}
Environment: Streamlit Cloud (Debian-based)
    """)

# Troubleshooting guide
with st.expander("🚨 Troubleshooting"):
    st.markdown("""
    **Current Status:** Fixed package names for Debian/Streamlit Cloud
    
    **If you still get errors:**
    
    1. **Make sure these files exist in your repo:**
       - `packages.txt` with: chromium, wget, unzip, xvfb
       - `requirements.txt` with: streamlit, selenium, pillow, webdriver-manager
    
    2. **Redeploy after adding the files**
    
    3. **Alternative: Use different platform:**
       - Railway.app (better browser support)
       - Heroku (full Linux environment)  
       - Local development environment
    
    **Package names tested for Streamlit Cloud (Debian 11 Bullseye)**
    """)
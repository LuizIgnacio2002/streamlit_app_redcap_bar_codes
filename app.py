import streamlit as st
import os
from email.message import EmailMessage
import ssl
import smtplib
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from PIL import Image
import time
import shutil

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
# Chrome Options for Cloud Environment
# =========================================
def get_chrome_options():
    """Get Chrome options optimized for cloud environments"""
    chrome_options = Options()
    
    # Essential options for cloud/headless environments
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
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-default-apps")
    chrome_options.add_argument("--disable-sync")
    chrome_options.add_argument("--no-first-run")
    chrome_options.add_argument("--disable-popup-blocking")
    chrome_options.add_argument("--single-process")
    chrome_options.add_argument("--disable-web-security")
    chrome_options.add_argument("--disable-features=VizDisplayCompositor")
    
    # Memory optimizations
    chrome_options.add_argument("--memory-pressure-off")
    chrome_options.add_argument("--max_old_space_size=4096")
    
    # Disable logging
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
        st.info("Starting Chrome for barcode download...")
        
        chrome_options = get_chrome_options()
        
        # Create temp directory for downloads
        folder = "codigos_barras"
        os.makedirs(folder, exist_ok=True)
        
        # Try to initialize the driver
        try:
            driver = webdriver.Chrome(options=chrome_options)
            st.success("✅ Chrome driver initialized successfully")
        except Exception as e:
            st.error(f"❌ Failed to initialize Chrome driver: {e}")
            st.info("💡 This might be due to missing Chrome browser in the cloud environment.")
            return []
        
        wait = WebDriverWait(driver, 30)  # Increased timeout

        # Login to RedCap
        st.info("🔐 Logging into RedCap...")
        url = "https://redcap.prisma.org.pe/redcap_v14.5.11/DataEntry/record_status_dashboard.php?pid=19"
        
        try:
            driver.get(url)
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
                
                # Wait for page to load
                time.sleep(2)

                # Wait for any loading indicators to disappear
                try:
                    loading_locator = (By.XPATH, "//*[contains(text(),'PIPING DATA')]")
                    WebDriverWait(driver, 5).until(EC.invisibility_of_element_located(loading_locator))
                except TimeoutException:
                    pass  # No loading indicator found or it disappeared

                # Find the barcode element
                try:
                    tr_selector = "tr#barcode-tr"
                    tr_el = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, tr_selector)))
                except TimeoutException:
                    st.warning(f"⚠️ Barcode element not found for ID: {id_val}")
                    continue

                # Scroll to element and wait
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", tr_el)
                time.sleep(1.5)

                # Take screenshot
                screenshot_path = os.path.join(folder, f"{id_val}.png")
                tr_el.screenshot(screenshot_path)

                # Process and crop image
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

            except TimeoutException:
                st.error(f"⏰ Timeout for Record ID: {id_val}")
            except Exception as e:
                st.error(f"❌ Error processing ID {id_val}: {e}")
            
            # Update progress bar
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
# Email Function with Multiple Attachments
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
def check_system_requirements():
    """Check if required system components are available"""
    st.subheader("🔍 System Requirements Check")
    
    checks = []
    
    # Check Chrome availability
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        driver = webdriver.Chrome(options=chrome_options)
        driver.quit()
        checks.append(("✅", "Chrome Browser", "Available"))
    except Exception as e:
        checks.append(("❌", "Chrome Browser", f"Not available: {str(e)[:50]}..."))
    
    # Display checks
    for status, component, message in checks:
        st.write(f"{status} **{component}**: {message}")
    
    return all(check[0] == "✅" for check in checks)

# =========================================
# Streamlit UI
# =========================================
st.title("🔬 RedCap Barcode Downloader & Email Sender")
st.write("Enter Record IDs to download their barcode images from RedCap and send them via email.")

# System check section
with st.expander("🔧 System Check"):
    if st.button("Run System Check"):
        system_ok = check_system_requirements()
        if not system_ok:
            st.warning("⚠️ Some system requirements are missing. The app may not work properly.")

# Main input form
record_ids_input = st.text_input(
    "Enter Record IDs separated by commas", 
    placeholder="e.g., 1,2,3,4,5",
    value="1,2,3"
)

email_receiver_input = st.text_input(
    "Enter Receiver Email",
    placeholder="example@domain.com"
)

# Processing section
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
                
                # Download barcode images
                with st.spinner("📥 Downloading barcode images..."):
                    downloaded_files = download_barcode_images(record_ids, redcap_username, redcap_password)

                if downloaded_files:
                    st.success(f"✅ Successfully downloaded {len(downloaded_files)} barcode images!")

                    # Display downloaded images
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
                            st.success("✅ Email sent successfully with barcode images attached!")
                            
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
                    st.info("💡 Try running the system check to identify potential issues.")

        except Exception as e:
            st.error(f"❌ Processing error: {e}")
            st.exception(e)

# Information sections
with st.expander("ℹ️ Troubleshooting"):
    st.markdown("""
    **Common Issues & Solutions:**
    
    1. **Chrome Driver Error (Status code 127)**:
       - This usually means Chrome is not installed in the environment
       - Try running the system check first
       - Consider using a different deployment platform that supports Chrome
    
    2. **Memory Issues**:
       - Reduce the number of Record IDs processed at once
       - Try processing 3-5 IDs at a time instead of large batches
    
    3. **Timeout Errors**:
       - Check your internet connection
       - Verify RedCap credentials are correct
       - The RedCap server might be slow or unavailable
    
    **For Streamlit Cloud deployment**, you may need to:
    - Use the `packages.txt` file to install Chrome
    - Add these lines to `packages.txt`:
      ```
      chromium-browser
      chromium-chromedriver
      ```
    """)

with st.expander("🔧 Current Configuration"):
    st.code(f"""
RedCap URL: https://redcap.prisma.org.pe/redcap_v14.5.11/
Project ID: 19
Event ID: 59
Page: recepcion_de_muestra
Email From: {email_sender}
Email To: (defined in UI)
Chrome Options: Headless mode optimized for cloud environments
    """)

# Deployment instructions
with st.expander("🚀 Deployment Instructions"):
    st.markdown("""
    **For Streamlit Cloud deployment:**
    
    1. **Create a `packages.txt` file** in your repository root:
    ```
    chromium-browser
    chromium-chromedriver
    ```
    
    2. **Create a `requirements.txt` file**:
    ```
    streamlit
    selenium
    pillow
    ```
    
    3. **Configure secrets** in Streamlit Cloud:
    - `redcap_username`: Your RedCap username
    - `redcap_password`: Your RedCap password  
    - `email_sender`: Sender email address
    - `email_password`: App password for sender email
    
    4. **Alternative**: Consider using **Playwright** instead of Selenium for better cloud compatibility.
    """)
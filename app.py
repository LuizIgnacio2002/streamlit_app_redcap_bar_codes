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
redcap_username = st.secrets["redcap_username"]
redcap_password = st.secrets["redcap_password"]
email_sender = st.secrets["email_sender"]
email_password = st.secrets["email_password"]

# =========================================
# RedCap Barcode Screenshot Function
# =========================================
def download_barcode_images(record_ids, username, password):
    """Download barcode images for specific Record IDs from RedCap"""
    try:
        st.info("Starting Chrome for barcode download...")

        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")

        folder = "codigos_barras"
        os.makedirs(folder, exist_ok=True)

        driver = webdriver.Chrome(options=chrome_options)
        wait = WebDriverWait(driver, 20)

        # Login to RedCap
        url = "https://redcap.prisma.org.pe/redcap_v14.5.11/DataEntry/record_status_dashboard.php?pid=19"
        driver.get(url)

        wait.until(EC.presence_of_element_located((By.ID, "username"))).send_keys(username)
        pass_el = wait.until(EC.presence_of_element_located((By.ID, "password")))
        pass_el.send_keys(password)
        pass_el.send_keys(Keys.ENTER)

        wait.until(EC.url_contains("record_status_dashboard.php"))
        st.success("Successfully logged into RedCap!")

        TARGET_URL_TEMPLATE = (
            "https://redcap.prisma.org.pe/redcap_v14.5.11/DataEntry/index.php?pid=19&id={id_val}&event_id=59&page=recepcion_de_muestra"
        )

        downloaded_files = []

        for id_val in record_ids:
            try:
                st.info(f"Processing Record ID: {id_val}")
                target_url = TARGET_URL_TEMPLATE.format(id_val=id_val)
                driver.get(target_url)

                try:
                    loading_locator = (By.XPATH, "//*[contains(text(),'PIPING DATA')]")
                    wait.until(EC.invisibility_of_element_located(loading_locator))
                except TimeoutException:
                    pass

                tr_selector = "tr#barcode-tr"
                tr_el = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, tr_selector)))

                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", tr_el)
                time.sleep(1.2)

                screenshot_path = os.path.join(folder, f"{id_val}.png")
                tr_el.screenshot(screenshot_path)

                try:
                    img = Image.open(screenshot_path)
                    w, h = img.size
                    new_w = int(w * 2 / 3)
                    img_cropped = img.crop((0, 0, new_w, h))
                    img_cropped.save(screenshot_path)
                    downloaded_files.append(screenshot_path)
                    st.success(f"✅ Downloaded barcode for ID: {id_val}")
                except Exception as e:
                    st.error(f"Error cropping image for ID {id_val}: {e}")

            except TimeoutException:
                st.error(f"❌ Timeout for Record ID: {id_val}")
            except Exception as e:
                st.error(f"❌ Error processing ID {id_val}: {e}")

        driver.quit()
        return downloaded_files

    except Exception as e:
        st.error(f"Error in barcode download: {e}")
        return []

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
        st.error(f"Email send failed: {e}")
        return False

# =========================================
# Streamlit UI
# =========================================
st.title("🔬 RedCap Barcode Downloader & Email Sender")
st.write("Enter Record IDs to download their barcode images from RedCap and send them via email.")

record_ids_input = st.text_input(
    "Enter Record IDs separated by commas", 
    placeholder="e.g., 1,2,3,4,5",
    value="1,2,3"
)

email_receiver_input = st.text_input(
    "Enter Receiver Email",
    placeholder="example@domain.com"
)

if st.button("🚀 Download Barcodes & Send Email", type="primary"):
    if not record_ids_input.strip():
        st.error("❌ Please enter at least one Record ID")
    elif not email_receiver_input.strip():
        st.error("❌ Please enter a receiver email")
    else:
        try:
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
                st.info(f"Processing {len(record_ids)} Record IDs: {record_ids}")
                
                with st.spinner("Downloading barcode images..."):
                    downloaded_files = download_barcode_images(record_ids, redcap_username, redcap_password)

                if downloaded_files:
                    st.success(f"✅ Successfully downloaded {len(downloaded_files)} barcode images!")

                    st.subheader("Downloaded Barcode Images:")
                    cols = st.columns(min(3, len(downloaded_files)))
                    for i, file_path in enumerate(downloaded_files):
                        col_idx = i % len(cols)
                        with cols[col_idx]:
                            if os.path.exists(file_path):
                                st.image(file_path, caption=f"ID: {os.path.basename(file_path).split('.')[0]}")

                    with st.spinner("Sending email..."):
                        if send_email_with_attachments(record_ids, downloaded_files, email_receiver_input):
                            st.success("✅ Email sent successfully with barcode images attached!")
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

with st.expander("🔧 Current Configuration"):
    st.code(f"""
RedCap URL: https://redcap.prisma.org.pe/redcap_v14.5.11/
Project ID: 19
Event ID: 59
Page: recepcion_de_muestra
Email From: {email_sender}
Email To: (defined in UI)
    """)

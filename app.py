import streamlit as st
import pandas as pd
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
import zipfile  # ← IMPORTACIÓN FALTANTE

# =========================================
# Credenciales desde st.secrets
# =========================================
try:
    redcap_username = st.secrets["redcap_username"]
    redcap_password = st.secrets["redcap_password"]
    email_sender = st.secrets["email_sender"]
    email_password = st.secrets["email_password"]
except Exception as e:
    st.error("❌ Error al cargar los secretos. Por favor configura tus secretos de Streamlit.")
    st.stop()

# =========================================
# Opciones de Chrome para Entorno en la Nube
# =========================================
def get_chrome_options():
    """Obtener opciones de Chrome optimizadas para entornos en la nube"""
    chrome_options = Options()
    
    # Opciones esenciales para entornos en la nube/sin cabeza
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
    
    # Optimizaciones de memoria
    chrome_options.add_argument("--memory-pressure-off")
    chrome_options.add_argument("--max_old_space_size=4096")
    
    # Deshabilitar logs
    chrome_options.add_experimental_option("excludeSwitches", ["enable-logging"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument("--log-level=3")
    
    return chrome_options

# =========================================
# Función de Captura de Pantalla de Códigos de Barras de RedCap
# =========================================
def download_barcode_images(record_ids, username, password):
    """Descargar imágenes de códigos de barras para Record IDs específicos desde RedCap"""
    driver = None
    try:
        st.info("Iniciando Chrome para descarga de códigos de barras...")
        
        chrome_options = get_chrome_options()
        
        # Crear directorio temporal para descargas
        folder = "codigos_barras"
        os.makedirs(folder, exist_ok=True)
        
        # Intentar inicializar el driver
        try:
            driver = webdriver.Chrome(options=chrome_options)
            st.success("✅ Driver de Chrome inicializado exitosamente")
        except Exception as e:
            st.error(f"❌ Fallo al inicializar el driver de Chrome: {e}")
            st.info("💡 Esto podría deberse a la falta del navegador Chrome en el entorno de la nube.")
            return []
        
        wait = WebDriverWait(driver, 30)  # Tiempo de espera aumentado

        # Iniciar sesión en RedCap
        st.info("🔐 Iniciando sesión en RedCap...")
        url = "https://redcap.prisma.org.pe/redcap_v14.5.11/DataEntry/record_status_dashboard.php?pid=19"
        
        try:
            driver.get(url)
        except Exception as e:
            st.error(f"❌ Fallo al cargar la URL de RedCap: {e}")
            return []

        # Proceso de inicio de sesión
        try:
            username_field = wait.until(EC.presence_of_element_located((By.ID, "username")))
            username_field.clear()
            username_field.send_keys(username)
            
            password_field = wait.until(EC.presence_of_element_located((By.ID, "password")))
            password_field.clear()
            password_field.send_keys(password)
            password_field.send_keys(Keys.ENTER)
            
            wait.until(EC.url_contains("record_status_dashboard.php"))
            st.success("✅ ¡Inicio de sesión exitoso en RedCap!")
        except Exception as e:
            st.error(f"❌ Fallo en el inicio de sesión: {e}")
            return []

        TARGET_URL_TEMPLATE = (
            "https://redcap.prisma.org.pe/redcap_v14.5.11/DataEntry/index.php?pid=19&id={id_val}&event_id=59&page=recepcion_de_muestra"
        )

        downloaded_files = []
        progress_bar = st.progress(0)
        
        total_ids = len(record_ids)

        status_message = st.empty()
        
        for idx, id_val in enumerate(record_ids):
            try:
                status_message.info(f"📸 Procesando Record ID: {id_val} ({idx + 1}/{total_ids})")
                
                target_url = TARGET_URL_TEMPLATE.format(id_val=id_val)
                driver.get(target_url)
                
                # Esperar a que la página se cargue
                WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, "table tbody")))

                # Esperar a que desaparezcan los indicadores de carga
                try:
                    loading_locator = (By.XPATH, "//*[contains(text(),'PIPING DATA')]")
                    WebDriverWait(driver, 5).until(EC.invisibility_of_element_located(loading_locator))
                except TimeoutException:
                    pass  # No se encontró indicador de carga o desapareció

                # Encontrar el elemento del código de barras
                try:
                    tr_selector = "tr#barcode-tr"
                    tr_el = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, tr_selector)))
                except TimeoutException:
                    st.warning(f"⚠️ Elemento de código de barras no encontrado para ID: {id_val}")
                    continue

                # Hacer scroll al elemento y esperar
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", tr_el)
                time.sleep(1.4)

                # Tomar captura de pantalla
                screenshot_path = os.path.join(folder, f"{id_val}.png")
                tr_el.screenshot(screenshot_path)

                # Procesar y recortar imagen
                try:
                    img = Image.open(screenshot_path)
                    w, h = img.size
                    new_w = int(w * 2 / 3)
                    img_cropped = img.crop((0, 0, new_w, h))
                    img_cropped.save(screenshot_path)
                    downloaded_files.append(screenshot_path)
                    status_message.success(f"✅ Código de barras descargado para ID: {id_val}")
                except Exception as e:
                    st.error(f"❌ Error al procesar imagen para ID {id_val}: {e}")

            except TimeoutException:
                st.error(f"⏰ Tiempo de espera agotado para Record ID: {id_val}")
            except Exception as e:
                st.error(f"❌ Error al procesar ID {id_val}: {e}")
            
            # Actualizar barra de progreso
            progress_bar.progress((idx + 1) / total_ids)

        return downloaded_files

    except Exception as e:
        st.error(f"❌ Error en la descarga de códigos de barras: {e}")
        return []
    
    finally:
        if driver:
            try:
                driver.quit()
                st.info("🔄 Driver de Chrome cerrado")
            except:
                pass

# =========================================
# Función de Creación de ZIP - FUNCIÓN FALTANTE
# =========================================
def create_zip_file(attachment_files, record_ids):
    """Crear un archivo ZIP que contenga todas las imágenes de códigos de barras."""
    try:
        # Crear nombre del archivo ZIP con marca de tiempo
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_filename = f"codigos_barras_redcap_{timestamp}.zip"
        zip_path = os.path.join("codigos_barras", zip_filename)
        
        st.info(f"📦 Creando archivo ZIP: {zip_filename}")
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in attachment_files:
                if os.path.exists(file_path):
                    # Agregar archivo al ZIP con solo el nombre del archivo (no la ruta completa)
                    filename = os.path.basename(file_path)
                    zipf.write(file_path, filename)
                    
        # Verificar que el ZIP se haya creado exitosamente
        if os.path.exists(zip_path):
            zip_size = os.path.getsize(zip_path) / (1024 * 1024)  # Tamaño en MB
            st.success(f"✅ Archivo ZIP creado exitosamente: {zip_filename} ({zip_size:.2f} MB)")
            return zip_path
        else:
            st.error("❌ Fallo al crear el archivo ZIP")
            return None
            
    except Exception as e:
        st.error(f"❌ Error al crear el archivo ZIP: {e}")
        return None

# =========================================
# Función de Email con Adjunto ZIP - FUNCIÓN FALTANTE
# =========================================
def send_email_with_zip(record_ids, attachment_files, email_receiver):
    """Enviar email con imágenes de códigos de barras como archivo ZIP adjunto."""
    try:
        # Primero crear el archivo ZIP
        zip_path = create_zip_file(attachment_files, record_ids)
        
        if not zip_path or not os.path.exists(zip_path):
            st.error("❌ No se pudo crear el archivo ZIP para el email")
            return False
        
        # Crear email
        em = EmailMessage()
        em['From'] = email_sender
        em['To'] = email_receiver
        em['Subject'] = f"Códigos de Barras RedCap - IDs: {', '.join(map(str, record_ids))}"

        html_body = f"""
        <html>
          <body>
            <h2>Códigos de Barras Descargados</h2>
            <p><strong>Total de imágenes procesadas:</strong> {len(attachment_files)}</p>
            <p><strong>Archivo adjunto:</strong> {os.path.basename(zip_path)} (formato ZIP)</p>
            <br>
            <p><em>💡 Para ver las imágenes, descarga y descomprime el archivo ZIP adjunto.</em></p>
            <br>
            <p>Nota: La imagen 5.png corresponde al record_id 5 del proyecto PRESIENTE LAB MUESTRAS HUMANAS y así con cada imagen dentro del zip<p>
            <p><em>Enviado desde la aplicación de Streamlit</em></p>
          </body>
        </html>
        """
        em.add_alternative(html_body, subtype="html")

        # Agregar archivo ZIP como adjunto
        with open(zip_path, "rb") as f:
            zip_filename = os.path.basename(zip_path)
            em.add_attachment(
                f.read(),
                maintype="application",
                subtype="zip",
                filename=zip_filename
            )

        # Enviar email
        st.info("📧 Enviando email con archivo ZIP adjunto...")
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL('smtp.gmail.com', 465, context=context, timeout=30) as smtp:
            smtp.login(email_sender, email_password)
            smtp.sendmail(email_sender, email_receiver, em.as_string())

        return True

    except Exception as e:
        st.error(f"❌ Fallo en el envío del email: {e}")
        return False

# =========================================
# Función de Procesamiento de CSV
# =========================================
def process_csv_upload():
    """Manejar la carga y validación de CSV para record IDs"""
    st.subheader("📁 Cargar CSV con Record IDs")
    
    # Mostrar formato de ejemplo
    with st.expander("📄 Ejemplo de Formato CSV"):
        example_data = pd.DataFrame({
            "record_id": ["1", "1048", "1049", "1055"]
        })
        st.dataframe(example_data, use_container_width=True, hide_index=True)
        
        # Botón de descarga para tabla de ejemplo
        example_csv = example_data.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Descargar tabla de muestra",
            data=example_csv,
            file_name="tabla_muestra.csv",
            mime="text/csv",
        )
    
    # Cargador de archivos
    uploaded_file = st.file_uploader("Cargar tu archivo CSV", type=["csv"])
    
    if uploaded_file is not None:
        try:
            # Leer CSV
            df = pd.read_csv(uploaded_file)
            
            # Verificar si existe la columna 'record_id'
            if "record_id" not in df.columns:
                st.error("❌ El CSV no contiene una columna llamada 'record_id'.")
                return None
            
            # Mostrar vista previa de datos cargados
            st.subheader("📊 Vista Previa de Datos Cargados")
            st.dataframe(df.head(10), use_container_width=True, hide_index=True)
            st.info(f"Total de filas en CSV: {len(df)}")
            
            # Convertir a numérico y validar
            df["record_id_numeric"] = pd.to_numeric(df["record_id"], errors="coerce")
            
            # Detectar valores no numéricos
            invalid_values = df.loc[df["record_id_numeric"].isnull(), "record_id"]
            
            if not invalid_values.empty:
                st.warning("⚠️ Se encontraron valores no numéricos en 'record_id':")
                st.write(invalid_values.tolist())
                st.info("Solo se procesarán los valores numéricos válidos.")
            
            # Procesar solo valores numéricos válidos
            valid_df = df.dropna(subset=["record_id_numeric"]).copy()
            
            if len(valid_df) == 0:
                st.error("❌ No se encontraron record IDs numéricos válidos en el CSV.")
                return None
            
            # Convertir a enteros
            valid_df["record_id_int"] = valid_df["record_id_numeric"].astype(int)
            record_ids = valid_df["record_id_int"].tolist()
            
            # Mostrar resultados de validación
            st.success(f"✅ Se encontraron {len(record_ids)} record IDs válidos")
            
            # Mostrar IDs válidos
            with st.expander(f"📋 Record IDs Válidos ({len(record_ids)} elementos)"):
                st.write(record_ids)
            
            return record_ids
            
        except Exception as e:
            st.error(f"❌ Error al procesar el archivo CSV: {e}")
            return None
    
    return None

# =========================================
# Función de Verificación del Sistema
# =========================================
def check_system_requirements():
    """Verificar si los componentes del sistema requeridos están disponibles"""
    st.subheader("🔍 Verificación de Requisitos del Sistema")
    
    checks = []
    
    # Verificar disponibilidad de Chrome
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        driver = webdriver.Chrome(options=chrome_options)
        driver.quit()
        checks.append(("✅", "Navegador Chrome", "Disponible"))
    except Exception as e:
        checks.append(("❌", "Navegador Chrome", f"No disponible: {str(e)[:50]}..."))
    
    # Mostrar verificaciones
    for status, component, message in checks:
        st.write(f"{status} **{component}**: {message}")
    
    return all(check[0] == "✅" for check in checks)

# =========================================
# Interfaz de Usuario de Streamlit
# =========================================
st.markdown("<h1 style='font-size: 20px;'>Descargar códigos de barras de RedCap (PRESIENTE LAB MUESTRAS HUMANAS) y enviar por Email</h1>", unsafe_allow_html=True)
st.write("Ingresa Record IDs manualmente o carga un archivo CSV para descargar imágenes de códigos de barras desde RedCap y enviarlas por email.")

# Sección de verificación del sistema
with st.expander("🔧 Verificación del Sistema"):
    if st.button("Ejecutar Verificación del Sistema"):
        system_ok = check_system_requirements()
        if not system_ok:
            st.warning("⚠️ Algunos requisitos del sistema están faltando. La aplicación podría no funcionar correctamente.")

# =========================================
# Selección de Método de Entrada
# =========================================
st.subheader("🎯 Elegir Método de Entrada")
input_method = st.radio(
    "¿Cómo te gustaría proporcionar los Record IDs?",
    ["Entrada Manual", "Carga de CSV"],
    horizontal=True
)

record_ids = []

# Método de entrada manual
if input_method == "Entrada Manual":
    st.subheader("✍️ Entrada Manual")
    record_ids_input = st.text_input(
        "Ingresa Record IDs separados por comas", 
        placeholder="ej., 1,2,3,4,5",
        value="1,2,3"
    )
    
    if record_ids_input.strip():
        try:
            # Parsear Record IDs
            for rid in record_ids_input.split(","):
                rid = rid.strip()
                if rid:
                    try:
                        record_ids.append(int(rid))
                    except ValueError:
                        st.warning(f"⚠️ '{rid}' no es un número válido, omitiendo.")
        except Exception as e:
            st.error(f"❌ Error al parsear Record IDs: {e}")

# Método de carga de CSV
elif input_method == "Carga de CSV":
    csv_record_ids = process_csv_upload()
    if csv_record_ids:
        record_ids = csv_record_ids

# =========================================
# Entrada de Email y Procesamiento
# =========================================
if record_ids:
    st.subheader("📧 Configuración de Email")
    st.success(f"✅ Listo para procesar {len(record_ids)} Record IDs: {record_ids[:10]}{'...' if len(record_ids) > 10 else ''}")
    
    email_receiver_input = st.text_input(
        "Ingresa Email del Destinatario",
        placeholder="ejemplo@dominio.com"
    )
    
    # Sección de procesamiento
    if st.button("🚀 Descargar Códigos de Barras y Enviar Email", type="primary"):
        if not email_receiver_input.strip():
            st.error("❌ Por favor ingresa un email del destinatario")
        else:
            try:
                st.info(f"🎯 Procesando {len(record_ids)} Record IDs...")
                
                # Descargar imágenes de códigos de barras
                with st.spinner("📥 Descargando imágenes de códigos de barras..."):
                    downloaded_files = download_barcode_images(record_ids, redcap_username, redcap_password)

                if downloaded_files:
                    st.success(f"✅ ¡Se descargaron exitosamente {len(downloaded_files)} imágenes de códigos de barras!")

                    # Mostrar imágenes descargadas
                    st.subheader("📸 Imágenes de Códigos de Barras Descargadas:")
                    cols = st.columns(min(3, len(downloaded_files)))
                    for i, file_path in enumerate(downloaded_files):
                        col_idx = i % len(cols)
                        with cols[col_idx]:
                            if os.path.exists(file_path):
                                st.image(file_path, caption=f"ID: {os.path.basename(file_path).split('.')[0]}")

                    # Enviar email con ZIP - LLAMADA ACTUALIZADA
                    with st.spinner("📧 Creando archivo ZIP y enviando email..."):
                        if send_email_with_zip(record_ids, downloaded_files, email_receiver_input):
                            st.success("✅ ¡Email enviado exitosamente con archivo ZIP de códigos de barras adjunto!")
                            
                            # Mostrar información del ZIP
                            zip_files = [f for f in os.listdir("codigos_barras") if f.endswith('.zip')]
                            if zip_files:
                                zip_file = zip_files[0]
                                zip_path = os.path.join("codigos_barras", zip_file)
                                if os.path.exists(zip_path):
                                    zip_size = os.path.getsize(zip_path) / (1024 * 1024)
                                    st.info(f"📦 Detalles del archivo ZIP: {zip_file} ({zip_size:.2f} MB)")
                            
                            # Limpieza
                            try:
                                shutil.rmtree("codigos_barras")
                                st.info("🧹 Archivos temporales limpiados")
                            except:
                                pass
                        else:
                            st.error("❌ Fallo al enviar el email")
                else:
                    st.error("❌ No se descargaron exitosamente imágenes de códigos de barras")
                    st.info("💡 Intenta ejecutar la verificación del sistema para identificar problemas potenciales.")

            except Exception as e:
                st.error(f"❌ Error de procesamiento: {e}")
                st.exception(e)
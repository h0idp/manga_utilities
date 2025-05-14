import zipfile
import shutil
from PIL import Image
import os
import tempfile
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from ttkthemes import ThemedTk
# --- Volver a la importación original ---
from super_image import ImageLoader, MsrnModel, MsrnConfig
# --- Fin del cambio ---
import torch
import threading
import queue

# --- Función para verificar correctamente la disponibilidad de CUDA ---
def check_cuda_availability():
    """Verifica si CUDA está disponible y devuelve información de diagnóstico."""
    cuda_available = torch.cuda.is_available()
    cuda_info = ""
    if cuda_available:
        try:
            cuda_info = f"CUDA disponible - Dispositivo: {torch.cuda.get_device_name(0)}"
        except Exception as e:
            cuda_info = f"CUDA disponible pero error al obtener información: {e}"
    else:
        cuda_info = "CUDA no disponible - Usando CPU"
    
    print(cuda_info)
    return cuda_available, cuda_info

# --- Configuración del Modelo ---
try:
    # Esta línea usa el nombre importado
    model = MsrnModel.from_pretrained("eugenesiow/msrn", scale=2)
    model_loaded = True
except Exception as e:
    print(f"Error al cargar el modelo de superresolución: {e}")
    messagebox.showerror("Error de Modelo", f"No se pudo cargar el modelo 'msrn': {e}\nLa función de superresolución no estará disponible.")
    model = None
    model_loaded = False

# --- Funciones Auxiliares ---
def is_image(filename):
    """Verifica si un archivo es una imagen válida."""
    try:
        with Image.open(filename) as img:
            img.verify() # Verifica la cabecera, no decodifica toda la imagen
        return True
    except Exception:
        return False

# ... (resto del código sin cambios) ...

def autorename_images_in_subfolders(folder_path):
    """Renombra imágenes en subcarpetas a un formato secuencial (01.ext, 02.ext...)."""
    if not os.path.isdir(folder_path):
        messagebox.showerror("Error", "La ruta proporcionada no es una carpeta válida.")
        return

    renamed_count = 0
    subfolder_count = 0
    try:
        # Recorre solo el primer nivel de subcarpetas
        for item in os.listdir(folder_path):
            subfolder_path = os.path.join(folder_path, item)
            if os.path.isdir(subfolder_path):
                subfolder_count += 1
                image_files = []
                try:
                    # Lista y filtra archivos de imagen en la subcarpeta actual
                    for filename in os.listdir(subfolder_path):
                        full_path = os.path.join(subfolder_path, filename)
                        if os.path.isfile(full_path) and is_image(full_path):
                            image_files.append(filename)
                except Exception as e:
                    print(f"Error listando archivos en {subfolder_path}: {e}")
                    continue # Saltar esta subcarpeta si hay error

                # Ordena los archivos encontrados (importante para la secuencia)
                sorted_files = sorted(image_files)

                # Renombra cada archivo de imagen
                for index, filename in enumerate(sorted_files, start=1):
                    try:
                        file_extension = os.path.splitext(filename)[1]
                        new_filename = f"{index:02d}{file_extension}"
                        source_path = os.path.join(subfolder_path, filename)
                        target_path = os.path.join(subfolder_path, new_filename)

                        # Evita renombrar si el nombre ya es correcto
                        if source_path != target_path:
                            os.rename(source_path, target_path)
                            renamed_count += 1
                    except OSError as e:
                        print(f"Error al renombrar {filename} en {subfolder_path}: {e}")
                        messagebox.showwarning("Error al renombrar", f"No se pudo renombrar {filename} en {item}:\n{e}")
                    except Exception as e:
                         print(f"Error inesperado al procesar {filename} en {subfolder_path}: {e}")

        if subfolder_count == 0:
             messagebox.showinfo("SnapTitle", "No se encontraron subcarpetas en la ruta seleccionada.")
        elif renamed_count == 0 and subfolder_count > 0:
             messagebox.showinfo("SnapTitle", "No se renombró ninguna imagen (posiblemente ya estaban nombradas correctamente o no había imágenes).")
        else:
            messagebox.showinfo("Éxito", f"Se renombraron {renamed_count} imágenes en {subfolder_count} subcarpetas.")

    except Exception as e:
        messagebox.showerror("Error Inesperado", f"Ocurrió un error durante el proceso de renombrado:\n{e}")


def aplicar_superresolucion(imagen_path, model_sr, device):
    """Aplica superresolución a una imagen usando el modelo y dispositivo dados."""
    if model_sr is None: # Si el modelo no se cargó, retorna la original
        return imagen_path
    try:
        image = Image.open(imagen_path).convert('RGB')
        inputs = ImageLoader.load_image(image)
        inputs = inputs.to(device) # Mueve los datos de entrada al dispositivo correcto

        with torch.no_grad(): # Desactiva el cálculo de gradientes para inferencia
            preds = model_sr(inputs)

        # Crear un archivo temporal para guardar la imagen procesada
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg", mode='wb')
        
        # CORRECCIÓN: Guardar la imagen procesada usando ImageLoader con el archivo temporal
        # Método 1: Si ImageLoader.save_image requiere un archivo como argumento
        ImageLoader.save_image(preds, temp_file.name)
        temp_file.close()
        
        # Método alternativo si el anterior no funciona:
        # output_image = ImageLoader.save_image(preds, return_pil=True)  # Asumiendo que hay un parámetro return_pil
        # temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg", mode='wb')
        # output_image.save(temp_file.name, format="JPEG", quality=95)
        # temp_file.close()
        
        return temp_file.name

    except Exception as e:
        print(f"Error al aplicar superresolución a {os.path.basename(imagen_path)}: {e}")
        # Si falla la superresolución, devolver la imagen original
        return imagen_path
    finally:
        # Limpiar memoria de GPU si es posible
        if device and 'cuda' in str(device):
            torch.cuda.empty_cache()


def zip_folders_worker(source_folder, delete_folders, move_to_done, usar_gpu, progress_queue):
    """Función de trabajo para comprimir carpetas (se ejecuta en un hilo separado)."""
    global model # Accede al modelo global

    if not model_loaded and usar_gpu:
        progress_queue.put(('error', "El modelo de superresolución no se cargó. No se puede usar GPU."))
        progress_queue.put(('done', None)) # Indica finalización (con error previo)
        return
    if not model_loaded:
         print("Advertencia: El modelo no está cargado, se omitirá la superresolución.")
         # Continuar sin superresolución si no se marcó usar GPU o si el modelo falló al cargar


    try:
        if not os.path.isdir(source_folder):
            progress_queue.put(('error', "La carpeta de origen no existe."))
            progress_queue.put(('done', None))
            return

        # Obtener lista de subcarpetas directas
        try:
            subfolders = [d for d in os.listdir(source_folder) if os.path.isdir(os.path.join(source_folder, d))]
        except FileNotFoundError:
             progress_queue.put(('error', f"No se pudo acceder a la carpeta de origen: {source_folder}"))
             progress_queue.put(('done', None))
             return
        except Exception as e:
             progress_queue.put(('error', f"Error listando subcarpetas en {source_folder}: {e}"))
             progress_queue.put(('done', None))
             return

        if not subfolders:
            progress_queue.put(('warning', "No hay subcarpetas para comprimir."))
            progress_queue.put(('done', None))
            return

        # --- Preparación del Modelo y Dispositivo (una sola vez) ---
        device = None
        local_model = None # Usar una copia local o referencia para claridad
        if model_loaded:
            local_model = model # Referencia al modelo global
            # CORRECCIÓN: Verificar CUDA y mostrar información diagnóstica
            cuda_available, cuda_info = check_cuda_availability()
            if usar_gpu and cuda_available:
                device = torch.device('cuda')
                print(f"Usando GPU para superresolución: {cuda_info}")
                progress_queue.put(('info', f"GPU: {cuda_info}"))
            else:
                device = torch.device('cpu')
                print(f"Usando CPU para superresolución: {cuda_info}")
                progress_queue.put(('info', f"CPU: {cuda_info}"))
            try:
                local_model.to(device) # Mueve el modelo al dispositivo UNA VEZ
                local_model.eval() # Poner el modelo en modo evaluación
            except Exception as e:
                 progress_queue.put(('error', f"Error al mover el modelo al dispositivo {device}: {e}"))
                 progress_queue.put(('done', None))
                 return
        else:
            print("Modelo no cargado, la superresolución será omitida.")
            device = None

        total_files_processed = 0
        total_subfolders = len(subfolders)

        # --- Procesamiento de cada subcarpeta ---
        for idx, subfolder in enumerate(subfolders):
            folder_path = os.path.join(source_folder, subfolder)
            zip_filename = os.path.join(source_folder, f"{subfolder}.cbz")

            try:
                # Lista archivos de imagen válidos en la subcarpeta
                image_files = [
                    f for f in os.listdir(folder_path)
                    if os.path.isfile(os.path.join(folder_path, f)) and
                       f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
                ]
                # Filtrar de nuevo con is_image por si acaso hay archivos corruptos con extensión correcta
                valid_image_files = []
                for f in image_files:
                    if is_image(os.path.join(folder_path, f)):
                        valid_image_files.append(f)
                    else:
                        print(f"Advertencia: Omitiendo archivo no válido o corrupto: {os.path.join(subfolder, f)}")

                image_files = valid_image_files # Usar la lista filtrada
                num_images_in_folder = len(image_files)

                if num_images_in_folder == 0:
                    print(f"Advertencia: La carpeta '{subfolder}' está vacía o no contiene imágenes válidas. Se omitirá.")
                    continue # Saltar a la siguiente subcarpeta

                # Actualizar progreso general (basado en carpetas)
                progress_queue.put(('progress_folder', idx + 1, total_subfolders, subfolder))

                with zipfile.ZipFile(zip_filename, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zipf:
                    for i, filename in enumerate(image_files):
                        file_path = os.path.join(folder_path, filename)
                        imagen_procesada_path = file_path # Por defecto, usar original

                        # Aplicar superresolución si el modelo está cargado Y el dispositivo está definido
                        if model_loaded and local_model and device:
                            imagen_procesada_path = aplicar_superresolucion(file_path, local_model, device)

                        # Añadir al ZIP
                        # Usar os.path.basename(filename) para asegurar que se guarde solo el nombre del archivo en el ZIP
                        zipf.write(imagen_procesada_path, os.path.basename(filename))

                        # Si se creó un archivo temporal (superresolución), borrarlo
                        if imagen_procesada_path != file_path and os.path.exists(imagen_procesada_path):
                            try:
                                os.remove(imagen_procesada_path)
                            except OSError as e:
                                print(f"Advertencia: No se pudo borrar el archivo temporal {imagen_procesada_path}: {e}")

                        # Actualizar progreso detallado (basado en archivos dentro de la carpeta actual)
                        progress_queue.put(('progress_file', i + 1, num_images_in_folder))
                        total_files_processed += 1

                # Eliminar carpeta original si se marcó la opción
                if delete_folders:
                    try:
                        shutil.rmtree(folder_path)
                        print(f"Carpeta eliminada: {folder_path}")
                    except OSError as e:
                        progress_queue.put(('error', f"Error al eliminar la carpeta {subfolder}: {e}"))
                        # Continuar con las demás carpetas si falla la eliminación

            except FileNotFoundError:
                 progress_queue.put(('error', f"No se encontró la subcarpeta '{subfolder}' durante el procesamiento."))
                 continue # Saltar a la siguiente carpeta
            except Exception as e:
                progress_queue.put(('error', f"Error procesando la carpeta '{subfolder}': {e}"))
                # Considerar si detener todo o continuar con las demás carpetas
                continue # Por ahora, continuar

        # Mover carpeta original a "Done" si se marcó la opción y no se eliminaron las carpetas
        if move_to_done and not delete_folders:
            done_folder = os.path.join(os.path.dirname(source_folder), "Done")
            target_path = os.path.join(done_folder, os.path.basename(source_folder))
            try:
                os.makedirs(done_folder, exist_ok=True)
                 # Verificar si el destino ya existe
                if os.path.exists(target_path):
                    progress_queue.put(('warning', f"La carpeta '{os.path.basename(source_folder)}' ya existe en 'Done'. No se movió."))
                else:
                    shutil.move(source_folder, done_folder)
                    print(f"Carpeta movida a: {done_folder}")
            except Exception as e:
                progress_queue.put(('error', f"Error al mover la carpeta a 'Done': {e}"))
        elif move_to_done and delete_folders:
             print("Nota: Las carpetas originales fueron eliminadas, no se movió nada a 'Done'.")


        # Indicar finalización exitosa
        progress_queue.put(('done', f"Proceso completado. {total_files_processed} archivos procesados en {total_subfolders} carpetas."))

    except Exception as e:
        # Captura errores generales antes de empezar el bucle o errores inesperados
        progress_queue.put(('error', f"Error inesperado en el proceso de compresión: {e}"))
        progress_queue.put(('done', None)) # Asegura que la GUI sepa que terminó (con error)
    finally:
        # Limpieza final si es necesario (ej. liberar modelo de GPU si no se usará más)
        if device and 'cuda' in str(device): # Verificar que device no sea None
             torch.cuda.empty_cache()


# --- Funciones de la GUI ---

def select_folder_compressit():
    """Abre diálogo para seleccionar carpeta para CompressIt."""
    folder_path = filedialog.askdirectory()
    if folder_path:
        selected_folder_compressit.set(folder_path)

def select_folder_snaptile():
    """Abre diálogo para seleccionar carpeta para SnapTitle y ejecuta el renombrado."""
    folder_path = filedialog.askdirectory()
    if folder_path:
        selected_folder_snaptile.set(folder_path)
        # El renombrado es rápido, se puede ejecutar directamente (o en hilo si hay muchísimas carpetas)
        autorename_images_in_subfolders(folder_path)
        # El mensaje de éxito/error se muestra dentro de autorename_images_in_subfolders

def start_compress_thread():
    """Inicia el proceso de compresión en un hilo separado."""
    folder_path = selected_folder_compressit.get()
    if not folder_path:
        messagebox.showwarning("Falta carpeta", "Por favor, selecciona una carpeta de origen.")
        return
    if not os.path.isdir(folder_path):
         messagebox.showerror("Error de ruta", "La ruta seleccionada no es una carpeta válida.")
         return

    # Deshabilitar botón mientras procesa
    compress_button.config(state=tk.DISABLED)
    # Reiniciar barras de progreso
    progress_bar_files["value"] = 0
    progress_bar_folders["value"] = 0
    progress_label_files.config(text="Archivo: 0/0")
    progress_label_folders.config(text="Carpeta: 0/0")
    status_label.config(text="Estado: Iniciando...")
    root.update_idletasks()


    delete_folders = delete_folders_var.get()
    move_to_done = move_to_done_var.get()
    usar_gpu = use_gpu_var.get()

    # Crear cola para comunicación entre hilos
    progress_queue = queue.Queue()

    # Crear y empezar el hilo trabajador
    thread = threading.Thread(target=zip_folders_worker,
                              args=(folder_path, delete_folders, move_to_done, usar_gpu, progress_queue),
                              daemon=True) # Daemon True para que el hilo muera si la ventana principal se cierra
    thread.start()

    # Iniciar el chequeo periódico de la cola en el hilo principal de Tkinter
    root.after(100, check_queue, progress_queue)

def check_queue(progress_queue):
    """Verifica la cola de progreso y actualiza la GUI. Se llama periódicamente."""
    try:
        # Procesar todos los mensajes pendientes en la cola sin bloquear
        while True:
            message = progress_queue.get_nowait()
            msg_type, msg_data = message[0], message[1:]

            if msg_type == 'progress_folder':
                current, total, name = msg_data
                progress_bar_folders["maximum"] = total
                progress_bar_folders["value"] = current
                progress_label_folders.config(text=f"Carpeta: {current}/{total} ({name})")
                status_label.config(text=f"Estado: Procesando carpeta '{name}'...")
                # Reiniciar progreso de archivos para la nueva carpeta
                progress_bar_files["value"] = 0
                progress_label_files.config(text="Archivo: 0/0")

            elif msg_type == 'progress_file':
                current, total = msg_data
                progress_bar_files["maximum"] = total
                progress_bar_files["value"] = current
                progress_label_files.config(text=f"Archivo: {current}/{total}")

            elif msg_type == 'error':
                error_message = msg_data[0]
                messagebox.showerror("Error en Proceso", error_message)
                status_label.config(text=f"Estado: Error - {error_message[:50]}...") # Mostrar parte del error

            elif msg_type == 'warning':
                 warning_message = msg_data[0]
                 messagebox.showwarning("Advertencia", warning_message)
                 status_label.config(text=f"Estado: Advertencia - {warning_message[:50]}...")
                 
            elif msg_type == 'info':
                 info_message = msg_data[0]
                 status_label.config(text=f"Estado: {info_message}")

            elif msg_type == 'done':
                final_message = msg_data[0] if msg_data and msg_data[0] else "Proceso finalizado."
                # Solo mostrar mensaje si no hubo error previo grave que ya mostró uno
                current_status = status_label.cget("text")
                show_completion_msg = not current_status.startswith("Estado: Error")

                status_label.config(text=f"Estado: {final_message}")
                if show_completion_msg:
                    messagebox.showinfo("Completado", final_message)

                # Reactivar botón al finalizar (incluso si hubo errores parciales)
                compress_button.config(state=tk.NORMAL)
                # Reiniciar barras al final
                progress_bar_files["value"] = 0
                progress_bar_folders["value"] = 0
                return # Detener el chequeo periódico

            root.update_idletasks() # Actualizar GUI después de procesar mensaje

    except queue.Empty:
        # Si la cola está vacía, programar la siguiente verificación
        root.after(100, check_queue, progress_queue)
    except Exception as e:
         print(f"Error en check_queue: {e}")
         status_label.config(text="Estado: Error en la interfaz.")
         compress_button.config(state=tk.NORMAL) # Reactivar en caso de error inesperado en GUI


# --- Creación de la GUI ---
root = ThemedTk(theme="clam")
root.title("Manga Utilities v2")
root.geometry("450x400") # Ajustar tamaño para más controles

notebook = ttk.Notebook(root)
notebook.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)

# --- Pestaña CompressIt ---
compressit_tab = ttk.Frame(notebook, padding="10")
notebook.add(compressit_tab, text="CompressIt + SuperRes")

# Selección de carpeta
folder_frame = ttk.Frame(compressit_tab)
folder_frame.pack(fill=tk.X, pady=5)
ttk.Label(folder_frame, text="Carpeta de origen:").pack(side=tk.LEFT, padx=(0, 5))
selected_folder_compressit = tk.StringVar()
folder_entry = ttk.Entry(folder_frame, textvariable=selected_folder_compressit, width=40)
folder_entry.pack(side=tk.LEFT, expand=True, fill=tk.X)
ttk.Button(folder_frame, text="...", width=3, command=select_folder_compressit).pack(side=tk.LEFT, padx=(5, 0))


# Opciones Checkbox
options_frame = ttk.Frame(compressit_tab)
options_frame.pack(fill=tk.X, pady=5)
delete_folders_var = tk.BooleanVar(value=False) # Por defecto no borrar
ttk.Checkbutton(options_frame, text="Eliminar carpetas originales", variable=delete_folders_var).pack(anchor=tk.W)

move_to_done_var = tk.BooleanVar(value=True) # Por defecto mover a Done
ttk.Checkbutton(options_frame, text="Mover carpeta a 'Done' (si no se eliminan)", variable=move_to_done_var).pack(anchor=tk.W)

# CORRECCIÓN: Verificar CUDA al iniciar
cuda_available, cuda_info = check_cuda_availability()
use_gpu_var = tk.BooleanVar(value=cuda_available) # Marcar por defecto si hay GPU
gpu_checkbox = ttk.Checkbutton(options_frame, text=f"Usar GPU para Super Resolución ({cuda_info})", variable=use_gpu_var)
gpu_checkbox.pack(anchor=tk.W)
if not model_loaded: # Deshabilitar si el modelo no cargó
    gpu_checkbox.config(state=tk.DISABLED, text="Usar GPU (Modelo no cargado)")
    use_gpu_var.set(False)
elif not cuda_available: # Deshabilitar si no hay CUDA
     gpu_checkbox.config(state=tk.DISABLED, text=f"Usar GPU ({cuda_info})")
     use_gpu_var.set(False)


# Botón de Compresión
compress_button = ttk.Button(compressit_tab, text="Iniciar Compresión y Super Resolución", command=start_compress_thread)
compress_button.pack(pady=10)

# Barras y Etiquetas de Progreso
progress_label_folders = ttk.Label(compressit_tab, text="Carpeta: 0/0")
progress_label_folders.pack(anchor=tk.W, padx=5)
progress_bar_folders = ttk.Progressbar(compressit_tab, orient="horizontal", length=300, mode="determinate")
progress_bar_folders.pack(fill=tk.X, padx=5, pady=(0, 5))

progress_label_files = ttk.Label(compressit_tab, text="Archivo: 0/0")
progress_label_files.pack(anchor=tk.W, padx=5)
progress_bar_files = ttk.Progressbar(compressit_tab, orient="horizontal", length=300, mode="determinate")
progress_bar_files.pack(fill=tk.X, padx=5, pady=(0, 10))

# Etiqueta de Estado
status_label = ttk.Label(compressit_tab, text="Estado: Listo")
status_label.pack(anchor=tk.W, padx=5, pady=(5, 0))


# --- Pestaña SnapTitle ---
snaptile_tab = ttk.Frame(notebook, padding="10")
notebook.add(snaptile_tab, text="SnapTitle (Renombrar)")

# Selección de carpeta
snap_folder_frame = ttk.Frame(snaptile_tab)
snap_folder_frame.pack(fill=tk.X, pady=5)
ttk.Label(snap_folder_frame, text="Carpeta Padre:").pack(side=tk.LEFT, padx=(0, 5))
selected_folder_snaptile = tk.StringVar()
snap_folder_entry = ttk.Entry(snap_folder_frame, textvariable=selected_folder_snaptile, width=40)
snap_folder_entry.pack(side=tk.LEFT, expand=True, fill=tk.X)
ttk.Button(snap_folder_frame, text="...", width=3, command=select_folder_snaptile).pack(side=tk.LEFT, padx=(5, 0))

ttk.Label(snaptile_tab, text="Selecciona la carpeta que contiene las subcarpetas a renombrar.", wraplength=380).pack(pady=10)
# El botón de selección ahora también ejecuta la acción


# --- Verificación de requisitos al iniciar ---
# Mostrar información sobre CUDA al iniciar
print(f"Información de CUDA al inicio: {cuda_info}")

# --- Iniciar Bucle Principal ---
root.mainloop()